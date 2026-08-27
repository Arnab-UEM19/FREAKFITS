"""
FreakFits - Razorpay Payment Gateway Router
============================================
POST /api/payments/create  - creates a Razorpay order + pre-creates DB row (status=PENDING)
POST /api/payments/verify  - HMAC-verifies the signature; marks DB row as PAID/Confirmed
"""

import datetime
import logging
import uuid

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from ..limiter import limiter

from ..config import settings
from ..database import get_db
from ..models import Coupon, Order, OrderItem, Product, User, FailedOrderRecovery
from ..schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    VerifyPaymentRequest,
)
from ..security import get_current_user
from ..utils.email import send_order_confirmation

logger = logging.getLogger("uvicorn")
router = APIRouter(prefix="/payments", tags=["Payments"])


def _razorpay_client():
    try:
        import razorpay
    except ImportError:
        raise HTTPException(status_code=503, detail="razorpay package not installed. Run: pip install razorpay")

    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Razorpay is not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env",
        )
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _calculate_totals(items, coupon_code, db):
    """Calculate order totals using server-verified prices from the database.
    Never trusts client-sent unit_price — always looks up product.size_prices."""
    verified_prices = []  # parallel list of DB-verified prices per item
    subtotal = 0.0
    
    product_ids = [item.product_id for item in items]
    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    products_by_id = {p.id: p for p in products}
    
    for item in items:
        product = products_by_id.get(item.product_id)
        if product:
            size_prices = product.size_prices or {}
            price = float(size_prices.get(item.size, product.price))
        else:
            price = float(item.unit_price)  # fallback only if product missing (edge case)
        verified_prices.append(price)
        subtotal += round(price * item.quantity, 2)

    discount = 0.0
    applied_coupon_code = None
    if coupon_code:
        coupon = db.query(Coupon).filter(
            Coupon.code == coupon_code.upper().strip(),
            Coupon.is_active == True,
        ).first()
        if coupon:
            discount = round(subtotal * (coupon.discount_percent / 100.0), 2)
            applied_coupon_code = coupon.code
    shipping_fee = 0.0 if (subtotal == 0.0 or (subtotal - discount) >= 500.0) else 99.0
    total = round(max(0.0, (subtotal - discount) + shipping_fee), 2)
    return subtotal, discount, shipping_fee, total, applied_coupon_code, verified_prices


@router.post("/create", response_model=CreatePaymentResponse)
@limiter.limit("10/minute")
def create_razorpay_payment(
    request: Request,
    payload: CreatePaymentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty.")

    # ===== Stock Validation =====
    product_ids = [item.product_id for item in payload.items]
    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    products_by_id = {p.id: p for p in products}
    
    for item in payload.items:
        product = products_by_id.get(item.product_id)
        if not product:
            raise HTTPException(status_code=400, detail=f"Product '{item.product_name}' not found.")
        stock_dict = product.stock or {}
        available = int(stock_dict.get(item.size, 0))
        if available < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"{item.product_name} in size {item.size} has only {available} unit(s) left."
            )

    # Calculate totals using DB-verified prices (ignores client-sent unit_price)

    client = _razorpay_client()
    subtotal, discount, shipping_fee, total, applied_coupon_code, verified_prices = _calculate_totals(
        payload.items, payload.coupon_code, db
    )
    amount_paisa = int(round(total * 100))

    user = current_user or db.query(User).filter(
        User.email == payload.customer_email.lower().strip()
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="An account is required to place an order. Please sign up or log in.",
        )

    # Re-verify Coupon Usage specifically for this user
    if applied_coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == applied_coupon_code).first()
        if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
            raise HTTPException(status_code=400, detail="The applied coupon has reached its usage limit.")
        
        used_order = db.query(Order).filter(
            Order.user_id == user.id,
            Order.coupon_code == applied_coupon_code,
            Order.payment_status.in_(["PAID", "COMPLETED"])
        ).first()
        if used_order:
            raise HTTPException(status_code=400, detail="You have already used this coupon.")

    order_code = f"FF-{uuid.uuid4().hex[:8].upper()}"

    try:
        rz_order = client.order.create({
            "amount": amount_paisa,
            "currency": "INR",
            "receipt": order_code,
            "notes": {"freakfits_order_code": order_code, "customer_email": user.email},
        })
    except Exception as exc:
        logger.error(f"[Razorpay] Order creation failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {exc!s}")

    razorpay_order_id = rz_order["id"]

    order_items_payload = [
        {
            "product_id": item.product_id,
            "product_name": item.product_name,
            "club": item.club,
            "size": item.size,
            "custom_name": item.custom_name,
            "custom_number": item.custom_number,
            "quantity": item.quantity,
            "unit_price": verified_prices[idx],  # DB-verified price, not client-sent
        }
        for idx, item in enumerate(payload.items)
    ]

    order_data = {
        "order_code": order_code,
        "user_id": user.id,
        "customer_name": user.full_name or payload.customer_name,
        "customer_email": user.email,
        "customer_phone": user.mobile_number or payload.customer_phone,
        "subtotal": subtotal,
        "discount": discount,
        "shipping_fee": shipping_fee,
        "total": total,
        "coupon_code": applied_coupon_code,
        "payment_method": "razorpay",
        "razorpay_order_id": razorpay_order_id,
        "shipping_address": payload.shipping_address,
        "items": order_items_payload,
    }

    # Generate a signed JWT containing order details (valid for 30 minutes)
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    token_payload = {
        "order_data": order_data,
        "exp": expire
    }
    order_token = jwt.encode(token_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    logger.info(f"[Razorpay] Initiated order {order_code} -> Razorpay {razorpay_order_id} (not saved in DB yet)")

    return CreatePaymentResponse(
        razorpay_order_id=razorpay_order_id,
        amount=amount_paisa,
        currency="INR",
        freakfits_order_code=order_code,
        key_id=settings.RAZORPAY_KEY_ID,
        order_token=order_token,
    )


@router.post("/verify")
@limiter.limit("10/minute")
def verify_razorpay_payment(
    request: Request,
    payload: VerifyPaymentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    client = _razorpay_client()

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
    except Exception as exc:
        logger.warning(f"[Razorpay] Signature mismatch for {payload.freakfits_order_code}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Payment verification failed. If you were charged, contact support with Order ID: "
                + payload.freakfits_order_code
            ),
        )

    # Decode and verify the signed order_token
    try:
        decoded = jwt.decode(payload.order_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        order_data = decoded.get("order_data")
        if not order_data:
            raise HTTPException(status_code=400, detail="Invalid order token structure.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Checkout session expired. Please try again.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail=f"Order token validation failed: {exc!s}")

    # Safety checks
    if order_data.get("order_code") != payload.freakfits_order_code:
        raise HTTPException(status_code=400, detail="Order code mismatch.")
    if order_data.get("razorpay_order_id") != payload.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Razorpay order ID mismatch.")

    # Check if order already exists in database (idempotent request)
    db_order = db.query(Order).filter(
        (Order.order_code == payload.freakfits_order_code) | 
        (Order.razorpay_payment_id == payload.razorpay_payment_id)
    ).first()
    if db_order:
        logger.info(f"[Razorpay] Order {payload.freakfits_order_code} already confirmed in DB.")
        return {
            "success": True,
            "order_code": payload.freakfits_order_code,
            "payment_id": payload.razorpay_payment_id,
            "message": "Payment verified and order confirmed.",
        }

    # Recreate the Order and OrderItem models
    order_items = [
        OrderItem(
            product_id=item["product_id"],
            product_name=item["product_name"],
            club=item["club"],
            size=item["size"],
            custom_name=item["custom_name"],
            custom_number=item["custom_number"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            line_total=round(item["unit_price"] * item["quantity"], 2),
        )
        for item in order_data["items"]
    ]

    db_order = Order(
        order_code=order_data["order_code"],
        user_id=order_data["user_id"],
        customer_name=order_data["customer_name"],
        customer_email=order_data["customer_email"],
        customer_phone=order_data["customer_phone"],
        subtotal=order_data["subtotal"],
        discount=order_data["discount"],
        shipping_fee=order_data["shipping_fee"],
        total=order_data["total"],
        coupon_code=order_data["coupon_code"],
        payment_method="razorpay",
        payment_status="PAID",
        order_status="Confirmed",
        razorpay_order_id=order_data["razorpay_order_id"],
        razorpay_payment_id=payload.razorpay_payment_id,
        shipping_address=order_data.get("shipping_address"),
        items=order_items,
    )

    db.add(db_order)

    # Increment Coupon Usage Count if a coupon was used
    if order_data.get("coupon_code"):
        coupon = db.query(Coupon).filter(Coupon.code == order_data["coupon_code"]).with_for_update().first()
        if coupon:
            coupon.usage_count += 1
            if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
                coupon.is_active = False

    try:
        # ===== Deduct Stock =====
        for item in order_data["items"]:
            product = db.query(Product).filter(Product.id == item["product_id"]).with_for_update().first()
            if product:
                current_stock = dict(product.stock or {})
                available = int(current_stock.get(item["size"], 0))
                if available < item["quantity"]:
                    raise Exception(f"oversold - stock unavailable at verification for {product.name} ({item['size']})")
                new_qty = available - item["quantity"]
                current_stock[item["size"]] = new_qty
                product.stock = current_stock
                flag_modified(product, "stock")

                if new_qty <= 2:
                    from ..utils.email import send_low_stock_alert
                    admin_email = settings.ADMIN_ALERT_EMAIL
                    if admin_email:
                        background_tasks.add_task(
                            send_low_stock_alert,
                            product_name=product.name,
                            club=product.club,
                            size=item["size"],
                            remaining_stock=new_qty,
                            admin_email=admin_email
                        )

        db.commit()
        db.refresh(db_order)
    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed during payment verification for {payload.freakfits_order_code}: {e}")
        
        try:
            failed_log = FailedOrderRecovery(
                payment_id=payload.razorpay_payment_id,
                razorpay_order_id=payload.razorpay_order_id,
                amount=order_data["total"],
                currency="INR",
                customer_identifier=order_data.get("customer_email") or str(order_data.get("user_id")),
                error_detail=str(e),
                is_resolved=False
            )
            db.add(failed_log)
            db.commit()
        except Exception as log_e:
            db.rollback()
            logger.critical(f"Failed to write to FailedOrderRecovery: {log_e}")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize order details after payment.")

    logger.info(f"[Razorpay] Payment VERIFIED and Order CREATED - {payload.freakfits_order_code} (payment_id: {payload.razorpay_payment_id})")

    # ===== Send Order Confirmation Email in Background =====
    try:
        background_tasks.add_task(
            send_order_confirmation,
            recipient_email=db_order.customer_email,
            recipient_name=db_order.customer_name,
            order_code=db_order.order_code,
            total=db_order.total,
            payment_method="Razorpay",
            items=db_order.items,
            shipping_address=db_order.shipping_address
        )
    except Exception as e:
        logger.error(f"Failed to queue order confirmation email: {e}")

    return {
        "success": True,
        "order_code": payload.freakfits_order_code,
        "payment_id": payload.razorpay_payment_id,
        "message": "Payment verified and order confirmed.",
    }
