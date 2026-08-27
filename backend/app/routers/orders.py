import logging
import math
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
import os
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..database import get_db
from ..models import Admin, Coupon, Order, OrderItem, Product, User
from ..schemas import OrderCreate, OrderResponse, PaginatedResponse
from ..security import get_current_admin, get_current_user, require_current_user
from ..utils.email import send_order_confirmation
from ..utils.audit import log_admin_action
from ..limiter import limiter

logger = logging.getLogger("uvicorn")
# orders.py is at backend/app/routers/orders.py
# dirname(dirname(this file)) = backend/app/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.get("/my-orders", response_model=PaginatedResponse[OrderResponse])
def get_my_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.created_at.desc())
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    pages = math.ceil(total / limit) if limit > 0 else 0
    return {
        "items": items,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": pages
    }

@router.get("/track", response_model=OrderResponse)
@limiter.limit("10/minute")
def track_order_by_code_and_phone(request: Request, order_code: str, phone: str, db: Session = Depends(get_db)):
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
    current_user: User | None = Depends(get_current_user),
    current_admin: Admin | None = Depends(get_current_admin)
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
    request: Request,
    order_code: str, 
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
    current_admin: Admin | None = Depends(get_current_admin)
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

    date_str = order.created_at.strftime('%d-%b-%Y %I:%M %p') if order.created_at else "N/A"

    return templates.TemplateResponse(
        "invoice.html",
        {
            "request": request,
            "order": order,
            "items": order.items,
            "date_str": date_str
        }
    )


@router.post("/{order_code}/cancel")
def cancel_order(
    order_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
    current_admin: Admin | None = Depends(get_current_admin)
):
    """Cancel an order. Only allowed when status is Pending or Confirmed."""
    order = db.query(Order).filter(Order.order_code == order_code.upper().strip()).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order `{order_code}` not found.")

    # Authorization: only the owner or a manager/super_admin can cancel
    is_owner = current_user and current_user.id == order.user_id
    if current_admin:
        role_hierarchy = {"viewer": 1, "manager": 2, "super_admin": 3}
        if role_hierarchy.get(current_admin.role, 0) < 2:
            raise HTTPException(status_code=403, detail="Action denied. This action requires at least manager privileges.")
    elif not is_owner:
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
    if current_admin:
        log_admin_action(db, current_admin.email, "ORDER_CANCELLED", "order", order_code, {"reason": "Manual cancellation from admin portal"})
    db.commit()

    # ===== Send Cancellation Email =====
    try:
        from ..utils.email import send_cancellation_email
        background_tasks.add_task(
            send_cancellation_email,
            recipient_email=order.customer_email,
            recipient_name=order.customer_name,
            order_code=order.order_code,
            total=order.total
        )
    except Exception as e:
        logger.error(f"Failed to queue cancellation email: {e}")

    logger.info(f"[Order] Cancelled order {order.order_code} — stock restored")
    return {
        "success": True,
        "order_code": order.order_code,
        "message": "Order cancelled successfully. Stock has been restored.",
        "order_status": "Cancelled"
    }

