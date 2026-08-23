import datetime
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from ..database import get_db
from ..models import Order, OrderItem, Coupon, User, Admin, Product
from ..schemas import OrderCreate, OrderResponse
from ..security import get_current_user, require_current_user, get_current_admin
from ..utils.email import send_order_confirmation

logger = logging.getLogger("uvicorn")

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.post("", response_model=OrderResponse)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item."
        )

    valid_methods = {"credit", "debit", "upi", "netbanking", "cod", "cash on delivery", "razorpay"}
    if payload.payment_method.lower().strip() not in valid_methods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment method. Must be one of: cod, credit, debit, upi, netbanking, razorpay."
        )

    # ===== Stock Validation =====
    stock_updates = []  # list of (product, size, qty) to deduct after validation
    for item in payload.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Product '{item.product_name}' (ID {item.product_id}) not found.")
        stock_dict = product.stock or {}
        available = int(stock_dict.get(item.size, 0))
        if available < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"{item.product_name} in size {item.size} has only {available} unit(s) left. You requested {item.quantity}."
            )
        stock_updates.append((product, item.size, item.quantity))

    # Calculate Subtotal
    subtotal = 0.0
    order_items = []
    for item in payload.items:
        line_total = round(item.unit_price * item.quantity, 2)
        subtotal += line_total
        order_items.append(
            OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                club=item.club,
                size=item.size,
                custom_name=item.custom_name,
                custom_number=item.custom_number,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total
            )
        )

    # Check Coupon
    discount = 0.0
    coupon_code = None
    if payload.coupon_code:
        coupon = db.query(Coupon).filter(
            Coupon.code == payload.coupon_code.upper().strip(),
            Coupon.is_active == True
        ).first()
        if coupon:
            # Per-user coupon usage check
            used_order = db.query(Order).filter(
                Order.user_id == (current_user.id if current_user else None),
                Order.coupon_code == coupon.code,
                Order.payment_status.in_(["PAID", "COMPLETED"]),
                Order.order_status != "Cancelled"
            ).first()
            if used_order:
                raise HTTPException(status_code=400, detail="You have already used this coupon on a previous order.")
            discount = round(subtotal * (coupon.discount_percent / 100.0), 2)
            coupon_code = coupon.code

    # Free shipping on >= 500 (0 when subtotal is 0)
    shipping_fee = 0.0 if (subtotal == 0.0 or (subtotal - discount) >= 500.0) else 99.0
    total = round(max(0.0, (subtotal - discount) + shipping_fee), 2)

    # Verify that the customer has an account in the MySQL database
    user = current_user or db.query(User).filter(User.email == payload.customer_email.lower().strip()).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="An account is required to place an order. Please sign up or log in first."
        )

    # Generate Order Code
    order_code = f"FF-{uuid.uuid4().hex[:8].upper()}"

    order = Order(
        order_code=order_code,
        user_id=user.id,
        customer_name=user.full_name or payload.customer_name.strip(),
        customer_email=user.email,
        customer_phone=user.mobile_number or payload.customer_phone,
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping_fee,
        total=total,
        coupon_code=coupon_code,
        payment_method=payload.payment_method.lower().strip(),
        payment_status="COMPLETED",
        shipping_address=payload.shipping_address,
        items=order_items
    )

    # ===== Deduct Stock =====
    for product, size, qty in stock_updates:
        current_stock = dict(product.stock or {})
        current_stock[size] = max(0, int(current_stock.get(size, 0)) - qty)
        product.stock = current_stock
        flag_modified(product, "stock")

    # Increment coupon usage
    if coupon_code:
        coupon_obj = db.query(Coupon).filter(Coupon.code == coupon_code).first()
        if coupon_obj:
            coupon_obj.usage_count += 1
            if coupon_obj.usage_limit is not None and coupon_obj.usage_count >= coupon_obj.usage_limit:
                coupon_obj.is_active = False

    db.add(order)
    db.commit()
    db.refresh(order)

    # ===== Send Order Confirmation Email =====
    try:
        send_order_confirmation(
            recipient_email=order.customer_email,
            recipient_name=order.customer_name,
            order_code=order.order_code,
            total=order.total,
            payment_method="Cash on Delivery",
            items=order.items,
            shipping_address=order.shipping_address
        )
    except Exception as e:
        logger.warning(f"[Email] Order confirmation email failed for {order.order_code}: {e}")

    return order

@router.get("/my-orders", response_model=List[OrderResponse])
def get_my_orders(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.created_at.desc()).all()
    return orders

@router.get("/track", response_model=OrderResponse)
def track_order_by_code_and_phone(order_code: str, phone: str, db: Session = Depends(get_db)):
    clean_code = order_code.upper().strip()
    clean_phone = phone.strip()
    
    order = db.query(Order).filter(
        Order.order_code == clean_code,
        Order.customer_phone == clean_phone
    ).first()
    
    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found. Please verify your Order ID and Phone Number."
        )
    return order

@router.get("/{order_code}", response_model=OrderResponse)
def get_order_by_code(
    order_code: str, 
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    current_admin: Optional[Admin] = Depends(get_current_admin)
):
    order = db.query(Order).filter(Order.order_code == order_code.upper().strip()).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order `{order_code}` not found."
        )

    # Restrict: Only the owner of the order or an admin can access this details endpoint
    is_owner = current_user and current_user.email.lower().strip() == order.customer_email.lower().strip()
    if not current_admin and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not authorized to view this order details."
        )

    return order

@router.get("/{order_code}/invoice", response_class=HTMLResponse)
def get_order_invoice(
    order_code: str, 
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    current_admin: Optional[Admin] = Depends(get_current_admin)
):
    order = db.query(Order).filter(Order.order_code == order_code.upper().strip()).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order `{order_code}` not found."
        )

    # Restrict: Only the owner of the order or an admin can download the tax invoice
    is_owner = current_user and current_user.email.lower().strip() == order.customer_email.lower().strip()
    if not current_admin and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not authorized to view or download this invoice."
        )

    date_str = order.created_at.strftime('%d-%b-%Y %I:%M %p')

    item_rows = ""
    for item in order.items:
        item_rate = round(item.line_total / item.quantity, 2)

        meta_info = f"Club: {item.club} · Size: {item.size}"
        custom_info = ""
        if item.custom_name or item.custom_number:
            custom_info = f'<div class="item-custom">CUSTOMIZATION: {item.custom_name or "—"} #{item.custom_number or "—"}</div>'

        item_rows += f"""
        <tr>
            <td>
                <div><strong>{item.product_name}</strong></div>
                <div class="item-meta">{meta_info}</div>
                {custom_info}
            </td>
            <td style="text-align: center;">{item.quantity}</td>
            <td style="text-align: right;">₹{item_rate:,.2f}</td>
            <td style="text-align: right;">₹{item.line_total:,.2f}</td>
        </tr>
        """

    discount_row = ""
    if order.discount > 0:
        discount_row = f"""
        <tr>
            <td>Discount ({order.coupon_code or "Coupon"})</td>
            <td style="text-align: right; color: #FF3E7A;">-₹{order.discount:,.2f}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice - {order.order_code}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #111111;
            margin: 0;
            padding: 40px;
            background: #ffffff;
            font-size: 13px;
            line-height: 1.4;
        }}
        .invoice-box {{
            max-width: 800px;
            margin: auto;
            border: 1px solid #e2e8f0;
            padding: 35px;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        }}
        .invoice-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #8CFF3B;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .brand-logo {{
            font-weight: 800;
            font-size: 24px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .brand-logo span {{
            color: #8CFF3B;
            background: #000;
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .company-info {{
            text-align: right;
            font-size: 11px;
            color: #64748b;
            line-height: 1.5;
        }}
        .invoice-details {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .details-block h4 {{
            margin: 0 0 8px 0;
            text-transform: uppercase;
            font-size: 11px;
            color: #94a3b8;
            letter-spacing: 0.05em;
        }}
        .details-block p {{
            margin: 0 0 4px 0;
        }}
        table.invoice-items {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
        }}
        table.invoice-items th {{
            background: #f8fafc;
            border-bottom: 2px solid #e2e8f0;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            color: #475569;
        }}
        table.invoice-items td {{
            border-bottom: 1px solid #e2e8f0;
            padding: 12px;
            vertical-align: top;
        }}
        .item-meta {{
            font-size: 11px;
            color: #64748b;
            margin-top: 4px;
        }}
        .item-custom {{
            font-size: 10px;
            color: #ff3e7a;
            font-weight: 600;
            margin-top: 4px;
            text-transform: uppercase;
        }}
        .summary-table {{
            width: 320px;
            margin-left: auto;
            border-collapse: collapse;
        }}
        .summary-table td {{
            padding: 6px 12px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .summary-table tr.grand-total {{
            font-weight: 700;
            font-size: 15px;
            color: #0f172a;
        }}
        .summary-table tr.grand-total td {{
            border-top: 2px solid #0f172a;
            border-bottom: 2px solid #0f172a;
        }}
        .invoice-footer {{
            margin-top: 50px;
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
            text-align: center;
            font-size: 11px;
            color: #94a3b8;
        }}
        @media print {{
            body {{
                padding: 0;
                background: none;
            }}
            .invoice-box {{
                border: none;
                box-shadow: none;
                padding: 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="invoice-box">
        <div class="invoice-header">
            <div class="brand-logo">FREAK<span>FITS</span></div>
            <div class="company-info">
                <strong>FreakFits Official</strong><br>
                Kolkata, West Bengal, India
            </div>
        </div>

        <div class="invoice-details">
            <div class="details-block">
                <h4>Billed To</h4>
                <p><strong>{order.customer_name}</strong></p>
                <p>Email: {order.customer_email}</p>
                <p>Phone: {order.customer_phone or "N/A"}</p>
                <p>Address:<br><span style="white-space: pre-line; color: #475569;">{order.shipping_address or "India (Fan Deliveries)"}</span></p>
            </div>
            <div class="details-block" style="text-align: right;">
                <h4>Invoice Info</h4>
                <p>Invoice ID: <strong>INV-{order.order_code}</strong></p>
                <p>Order ID: {order.order_code}</p>
                <p>Date: {date_str} (IST)</p>
                <p>Payment: {order.payment_method.upper()} ({order.payment_status})</p>
                <p>Razorpay Ref: {order.razorpay_order_id or "N/A"}</p>
            </div>
        </div>

        <table class="invoice-items">
            <thead>
                <tr>
                    <th>Item Description</th>
                    <th style="text-align: center;">Qty</th>
                    <th style="text-align: right;">Rate</th>
                    <th style="text-align: right;">Total</th>
                </tr>
            </thead>
            <tbody>
                {item_rows}
            </tbody>
        </table>

        <table class="summary-table">
            <tr>
                <td>Subtotal</td>
                <td style="text-align: right;">₹{order.subtotal:,.2f}</td>
            </tr>
            <tr>
                <td>Shipping Fee</td>
                <td style="text-align: right;">₹{order.shipping_fee:,.2f}</td>
            </tr>
            {discount_row}
            <tr class="grand-total">
                <td>Total</td>
                <td style="text-align: right;">₹{order.total:,.2f}</td>
            </tr>
        </table>

        <div class="invoice-footer">
            Thank you for shopping with FreakFits! This is a system-generated invoice.
        </div>
    </div>
    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 500);
        }};
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.post("/{order_code}/cancel")
def cancel_order(
    order_code: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    current_admin: Optional[Admin] = Depends(get_current_admin)
):
    """Cancel an order. Only allowed when status is Pending or Confirmed."""
    order = db.query(Order).filter(Order.order_code == order_code.upper().strip()).first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order `{order_code}` not found.")

    # Authorization: only the owner or an admin can cancel
    is_owner = current_user and current_user.id == order.user_id
    if not current_admin and not is_owner:
        raise HTTPException(status_code=403, detail="You are not authorized to cancel this order.")

    cancellable_statuses = {"Pending", "Confirmed"}
    if order.order_status not in cancellable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be cancelled. Current status is '{order.order_status}'. Only Pending or Confirmed orders can be cancelled."
        )

    # ===== Restore Stock =====
    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            current_stock = dict(product.stock or {})
            current_stock[item.size] = int(current_stock.get(item.size, 0)) + item.quantity
            product.stock = current_stock
            flag_modified(product, "stock")

    # ===== Restore Coupon Usage =====
    if order.coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == order.coupon_code).first()
        if coupon:
            coupon.usage_count = max(0, coupon.usage_count - 1)
            if not coupon.is_active and coupon.usage_limit is not None and coupon.usage_count < coupon.usage_limit:
                coupon.is_active = True

    order.order_status = "Cancelled"
    order.payment_status = "REFUNDED" if order.payment_status in ("PAID", "COMPLETED") else order.payment_status
    db.commit()

    # ===== Send Cancellation Email =====
    try:
        from ..utils.email import send_cancellation_email
        send_cancellation_email(
            recipient_email=order.customer_email,
            recipient_name=order.customer_name,
            order_code=order.order_code,
            total=order.total
        )
    except Exception as e:
        logger.warning(f"[Email] Cancellation email failed for {order.order_code}: {e}")

    logger.info(f"[Order] Cancelled order {order.order_code} — stock restored")
    return {
        "success": True,
        "order_code": order.order_code,
        "message": "Order cancelled successfully. Stock has been restored.",
        "order_status": "Cancelled"
    }

