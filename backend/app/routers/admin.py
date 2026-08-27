from datetime import datetime, date, timedelta
import math
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, Request, Response
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (
    Admin,
    AdminAuditLog,
    ContactMessage,
    FailedOrderRecovery,
    NewsletterSubscriber,
    Order,
    Product,
    ReturnRequest,
    Review,
    Coupon,
)
from ..schemas import (
    AdminLoginRequest,
    AdminProfileUpdateInput,
    AdminResponse,
    AdminStatsResponse,
    AdminTokenResponse,
    ContactMessageResponse,
    OrderResponse,
    OrderStatusUpdate,
    PaginatedResponse,
    ProductCreateAdmin,
    ProductResponse,
    ProductUpdateAdmin,
    ReturnStatusUpdate,
)
from ..security import (
    create_access_token,
    get_password_hash,
    require_current_admin,
    require_role,
    verify_password,
)
from ..utils.email import (
    send_access_approved,
    send_access_otp,
    send_order_status_update,
    send_shipping_notification,
)
from ..utils.sitemap import regenerate_sitemap
from ..utils.audit import log_admin_action
from ..limiter import limiter

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


@router.post("/login", response_model=AdminTokenResponse)
@limiter.limit("5/minute")
def admin_login(request: Request, response: Response, payload: AdminLoginRequest, db: Session = Depends(get_db)):
    """Authenticate administrator and return JWT token."""
    admin = db.query(Admin).filter(Admin.email == payload.email).first()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin email or password."
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is disabled."
        )

    if admin.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access request was rejected by the super admin."
        )
    elif admin.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access request is pending super admin approval."
        )

    token = create_access_token(data={"sub": admin.email, "role": "admin"})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": admin
    }

@router.post("/logout")
def admin_logout(response: Response):
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=True,
        samesite="lax"
    )
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=AdminResponse)
def get_admin_profile(admin: Admin = Depends(require_role("viewer"))):
    """Return profile for the currently logged-in admin."""
    return admin


@router.patch("/profile", response_model=AdminResponse)
def update_admin_profile(
    payload: AdminProfileUpdateInput,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Allow Super Admin to update their name (only once, if current name is 'Super Admin')."""
    if admin.role == "super_admin":
        if admin.full_name != "Super Admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Super Admin name has already been set and cannot be changed again."
            )
        admin.full_name = payload.full_name
        log_admin_action(db, admin.email, "ADMIN_PROFILE_UPDATED", "admin", str(admin.id), payload.dict(exclude_unset=True))
        db.commit()
        db.refresh(admin)
        return admin
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Super Admin can update their profile name."
        )


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(db: Session = Depends(get_db), admin: Admin = Depends(require_role("viewer"))):
    """Compute live dashboard metrics directly in database to save memory."""
    today_start = datetime.combine(date.today(), datetime.min.time())
    
    today_revenue = db.query(func.sum(Order.total)).filter(
        Order.created_at >= today_start
    ).scalar() or 0.0

    yesterday_start = today_start - timedelta(days=1)
    yesterday_revenue = db.query(func.sum(Order.total)).filter(
        Order.created_at >= yesterday_start,
        Order.created_at < today_start
    ).scalar() or 0.0

    if yesterday_revenue == 0:
        revenue_change = 100.0 if today_revenue > 0 else 0.0
    else:
        revenue_change = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100.0

    active_orders = db.query(Order).filter(
        or_(Order.order_status == None, Order.order_status != "Delivered")
    ).count()
    
    total_products = db.query(Product).filter(Product.is_active == True).count()
    
    # Only fetch the JSON stock dictionary rather than complete Product models
    stock_records = db.query(Product.stock).filter(Product.is_active == True).all()
    low_stock_count = 0
    for (stock_dict,) in stock_records:
        stock_dict = stock_dict or {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5}
        if any(int(qty) <= 2 for qty in stock_dict.values()):
            low_stock_count += 1

    pending_returns = db.query(ReturnRequest).filter(ReturnRequest.status == "PENDING_REVIEW").count()

    return {
        "today_revenue": round(today_revenue, 2),
        "revenue_change_percentage": round(revenue_change, 1),
        "active_orders": active_orders,
        "low_stock_count": low_stock_count,
        "total_products": total_products,
        "pending_returns": pending_returns
    }


@router.get("/orders", response_model=PaginatedResponse[OrderResponse])
def list_admin_orders(
    status_filter: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """List all customer orders with fulfillment items."""
    query = db.query(Order).order_by(desc(Order.created_at))
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Order.order_status == status_filter)
    
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


@router.get("/failed-payments")
def list_failed_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """List unresolved failed payments."""
    query = db.query(FailedOrderRecovery).filter(FailedOrderRecovery.is_resolved == False).order_by(desc(FailedOrderRecovery.timestamp))
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


@router.post("/failed-payments/{record_id}/resolve")
def resolve_failed_payment(
    record_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Mark a failed payment as resolved and delete it."""
    record = db.query(FailedOrderRecovery).filter(FailedOrderRecovery.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    log_admin_action(db, admin.email, "FAILED_PAYMENT_RESOLVED", "failed_payment", str(record.payment_id), {"reason": "Manually resolved and deleted"})
    db.delete(record)
    db.commit()
    return {"success": True, "message": "Failed payment log deleted successfully."}


@router.get("/audit-logs")
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """List administrative action audit logs and prune logs older than 7 days."""
    from ..models import get_ist_time
    from datetime import timedelta
    
    # Auto-prune logs older than 7 days
    seven_days_ago = get_ist_time() - timedelta(days=7)
    db.query(AdminAuditLog).filter(AdminAuditLog.timestamp < seven_days_ago).delete()
    db.commit()

    query = db.query(AdminAuditLog).order_by(desc(AdminAuditLog.timestamp))
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


@router.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """Update order fulfillment status (Pending, Shipped, Delivered)."""
    if admin.role == "viewer" and payload.order_status.lower() in ("cancelled", "refunded"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Viewer role cannot cancel or refund orders."
        )
    order = db.query(Order).filter((Order.order_code == order_id) | (Order.id == int(order_id) if order_id.isdigit() else False)).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")

    old_status = order.order_status or "Pending"
    new_status = payload.order_status
    
    # Order Status Guard: Block moving from Delivered backwards
    if old_status.lower() == "delivered":
        earlier_stages = {"pending", "confirmed", "preparing kit", "packing", "shipped"}
        if new_status.lower() in earlier_stages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move a Delivered order back to an earlier status. Use Refunded if this order needs to be reversed."
            )
            
    if new_status.lower() == "refunded":
        from sqlalchemy.orm.attributes import flag_modified
        
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

        log_admin_action(db, admin.email, "ORDER_REFUNDED_DELETED", "order", order_id, payload.dict())
        db.delete(order)
        db.commit()
        return {
            "success": True,
            "order_code": order_id,
            "order_status": "REFUNDED_DELETED",
            "message": f"Order {order_id} was refunded and deleted from the database."
        }

    order.order_status = payload.order_status
    log_admin_action(db, admin.email, "ORDER_STATUS_UPDATED", "order", order_id, payload.dict())
    db.commit()
    db.refresh(order)
    
    # Send email notification if status transitioned
    if payload.order_status.lower() != old_status.lower():
        if payload.order_status.lower() == "shipped":
            from ..utils.email import send_shipping_notification
            background_tasks.add_task(
                send_shipping_notification,
                recipient_email=order.customer_email,
                recipient_name=order.customer_name or "FreakFan",
                order_code=order.order_code,
                customer_phone=order.customer_phone or ""
            )
        else:
            from ..utils.email import send_order_status_update
            background_tasks.add_task(
                send_order_status_update,
                recipient_email=order.customer_email,
                recipient_name=order.customer_name or "FreakFan",
                order_code=order.order_code,
                new_status=order.order_status,
                customer_phone=order.customer_phone or ""
            )

    return {
        "success": True,
        "order_code": order.order_code,
        "order_status": order.order_status,
        "message": f"Order {order.order_code} status updated to {order.order_status}."
    }


@router.get("/products", response_model=PaginatedResponse[ProductResponse])
def list_admin_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """List all products with stock inventory."""
    query = db.query(Product).order_by(desc(Product.id))
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


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_admin_product(
    payload: ProductCreateAdmin,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("manager"))
):
    """Create a new jersey in catalog."""
    if admin.role == "manager":
        if payload.price != 1499.0 or (payload.size_prices and any(v != 1499.0 for v in payload.size_prices.values())):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action denied. Manager role is not permitted to customize product pricing."
            )

    # Compute auto-incremented ID
    max_id = db.query(Product.id).order_by(desc(Product.id)).first()
    new_id = (max_id[0] + 1) if max_id else 1

    stock_data = payload.stock or {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5}
    size_prices_data = payload.size_prices or {
        "S": payload.price,
        "M": payload.price,
        "L": payload.price,
        "XL": payload.price,
        "XXL": payload.price
    }
    default_was = payload.was_price or (payload.price + 400)
    size_was_prices_data = payload.size_was_prices or {
        "S": default_was,
        "M": default_was,
        "L": default_was,
        "XL": default_was,
        "XXL": default_was
    }

    uploaded_images = []
    for img in (payload.images or []):
        if img.startswith("data:image/"):
            try:
                import cloudinary
                import cloudinary.uploader
                cloudinary.config(
                    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                    api_key=settings.CLOUDINARY_API_KEY,
                    api_secret=settings.CLOUDINARY_API_SECRET
                )
                upload_result = cloudinary.uploader.upload(
                    img,
                    folder=settings.CLOUDINARY_FOLDER
                )
                uploaded_images.append(upload_result.get("secure_url"))
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cloudinary upload failed: {e}"
                )
        else:
            uploaded_images.append(img)

    new_prod = Product(
        id=new_id,
        name=payload.name,
        club=payload.club,
        price=payload.price,
        was_price=default_was,
        category=payload.category,
        badge=payload.badge,
        badge_bg="#8CFF3B" if payload.badge == "NEW DROP" else ("#FF3E7A" if payload.badge == "CLEARANCE" else "#29C5F6"),
        images=uploaded_images,
        stock=stock_data,
        size_prices=size_prices_data,
        size_was_prices=size_was_prices_data,
        is_active=True
    )
    db.add(new_prod)
    db.flush()  # Ensure new_prod.id is populated before logging
    log_admin_action(db, admin.email, "PRODUCT_CREATED", "product", str(new_prod.id), payload.dict())
    db.commit()
    db.refresh(new_prod)
    
    background_tasks.add_task(regenerate_sitemap)
    
    return new_prod


from sqlalchemy.orm.attributes import flag_modified


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_admin_product(
    product_id: int,
    payload: ProductUpdateAdmin,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("manager"))
):
    """Update price, stock, size_prices, size_was_prices or status of a jersey."""
    if admin.role == "manager":
        if payload.price is not None or payload.was_price is not None or payload.size_prices is not None or payload.size_was_prices is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action denied. Manager role is not permitted to change product pricing."
            )

    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found.")

    if payload.name is not None:
        prod.name = payload.name
    if payload.club is not None:
        prod.club = payload.club
    if payload.price is not None:
        prod.price = payload.price
        if prod.was_price is None or prod.was_price <= payload.price:
            prod.was_price = payload.price + 400
        # Update S price or fallback size_prices
        current_size_prices = dict(prod.size_prices or {
            "S": prod.price, "M": prod.price, "L": prod.price, "XL": prod.price, "XXL": prod.price
        })
        current_size_prices["S"] = payload.price
        prod.size_prices = current_size_prices
        flag_modified(prod, "size_prices")
    if payload.was_price is not None:
        prod.was_price = payload.was_price
    if payload.size_prices is not None:
        current_size_prices = dict(prod.size_prices or {
            "S": prod.price, "M": prod.price, "L": prod.price, "XL": prod.price, "XXL": prod.price
        })
        current_size_prices.update(payload.size_prices)
        prod.size_prices = current_size_prices
        flag_modified(prod, "size_prices")
        if "S" in payload.size_prices and payload.price is None:
            prod.price = payload.size_prices["S"]
    if payload.size_was_prices is not None:
        default_was = prod.was_price or (prod.price + 400)
        current_size_was_prices = dict(prod.size_was_prices or {
            "S": default_was, "M": default_was, "L": default_was, "XL": default_was, "XXL": default_was
        })
        current_size_was_prices.update(payload.size_was_prices)
        prod.size_was_prices = current_size_was_prices
        flag_modified(prod, "size_was_prices")
        if "S" in payload.size_was_prices:
            prod.was_price = payload.size_was_prices["S"]
    if payload.stock is not None:
        current_stock = dict(prod.stock or {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5})
        current_stock.update(payload.stock)
        prod.stock = current_stock
        flag_modified(prod, "stock")
    if payload.badge is not None:
        prod.badge = payload.badge
    if payload.is_active is not None:
        prod.is_active = payload.is_active

    log_admin_action(db, admin.email, "PRODUCT_UPDATED", "product", str(prod.id), payload.dict(exclude_unset=True))
    db.commit()
    db.refresh(prod)
    
    background_tasks.add_task(regenerate_sitemap)
    
    return prod


def _extract_cloudinary_public_id(url: str) -> str | None:
    """Given a Cloudinary secure_url, extract its public_id (folder/filename, no extension)."""
    if not url or "res.cloudinary.com" not in url:
        return None
    try:
        parts = url.split("/upload/")
        if len(parts) < 2:
            return None
        path_part = parts[1]
        subparts = path_part.split("/")
        if subparts[0].startswith("v") and subparts[0][1:].isdigit():
            subparts = subparts[1:]
        public_id_with_ext = "/".join(subparts)
        public_id, _ = os.path.splitext(public_id_with_ext)
        return public_id
    except Exception:
        return None


def _delete_cloudinary_images(image_urls: list[str]) -> None:
    """Best-effort deletion of one or more product images from Cloudinary.
    Never raises — a Cloudinary hiccup should not block the DB delete."""
    if not image_urls:
        return
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True
        )
    except Exception as e:
        print(f"Cloudinary config error during product image cleanup: {e}")
        return

    for url in image_urls:
        public_id = _extract_cloudinary_public_id(url)
        if not public_id:
            continue
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception as e:
            print(f"Cloudinary product image deletion error ({public_id}): {e}")


@router.delete("/products/{product_id}")
def delete_admin_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Delete a product from the database and its images from Cloudinary."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found.")

    image_urls = list(prod.images or [])

    db.delete(prod)
    log_admin_action(db, admin.email, "PRODUCT_DELETED", "product", str(product_id), {"deleted_images": image_urls})
    db.commit()

    # Clean up Cloudinary assets in the background so the delete stays fast
    background_tasks.add_task(_delete_cloudinary_images, image_urls)
    background_tasks.add_task(regenerate_sitemap)
    
    return {"success": True, "message": f"Product #{product_id} deleted successfully."}


@router.get("/returns")
def list_admin_returns(
    status_filter: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """List all customer return and exchange claim requests."""
    query = db.query(ReturnRequest).order_by(desc(ReturnRequest.created_at))
    if status_filter and status_filter.lower() != "all":
        query = query.filter(ReturnRequest.status == status_filter.upper())
    
    total = query.count()
    returns_list = query.offset(skip).limit(limit).all()
    pages = math.ceil(total / limit) if limit > 0 else 0
    
    items = [
        {
            "id": r.id,
            "return_code": r.return_code,
            "order_code": r.order_code,
            "customer_name": r.customer_name,
            "customer_email": r.customer_email,
            "return_type": r.return_type,
            "current_size": r.current_size,
            "requested_size": r.requested_size,
            "video_proof": r.video_proof,
            "reason_details": r.reason_details,
            "terms_accepted": r.terms_accepted,
            "status": r.status,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for r in returns_list
    ]
    return {
        "items": items,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": pages
    }


@router.patch("/returns/{return_code}/status")
def update_return_status(
    return_code: str,
    payload: ReturnStatusUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("manager"))
):
    """Update claim status (PENDING_REVIEW, APPROVED, REFUNDED, REJECTED)."""
    ret = db.query(ReturnRequest).filter(ReturnRequest.return_code == return_code).first()
    if not ret:
        raise HTTPException(status_code=404, detail=f"Return request '{return_code}' not found.")

    if payload.status in ("REJECTED", "REFUNDED"):
        # Delete video file from static folder if it exists
        if ret.video_proof and ret.video_proof.startswith("/static/uploads/returns/"):
            relative_path = ret.video_proof.lstrip("/")
            if os.path.exists(relative_path):
                try:
                    os.remove(relative_path)
                except Exception as e:
                    print(f"Error removing return video file: {e}")

        # Delete database record
        db.delete(ret)
        log_admin_action(db, admin.email, "RETURN_STATUS_UPDATED", "return", return_code, payload.dict())
        db.commit()
        return {
            "success": True,
            "return_code": return_code,
            "status": f"{payload.status}_DELETED",
            "message": f"Return claim {return_code} was {payload.status} and deleted from database and storage."
        }

    ret.status = payload.status
    log_admin_action(db, admin.email, "RETURN_STATUS_UPDATED", "return", return_code, payload.dict())
    db.commit()
    db.refresh(ret)
    return {
        "success": True,
        "return_code": ret.return_code,
        "status": ret.status,
        "message": f"Return claim {ret.return_code} status updated to {ret.status}."
    }


@router.get("/reviews")
def get_all_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """Retrieve all customer reviews for moderation."""
    query = db.query(Review).order_by(Review.created_at.desc())
    total = query.count()
    reviews = query.offset(skip).limit(limit).all()
    pages = math.ceil(total / limit) if limit > 0 else 0
    result = []
    for r in reviews:
        prod = db.query(Product).filter(Product.id == r.product_id).first()
        result.append({
            "id": r.id,
            "product_id": r.product_id,
            "product_name": prod.name if prod else "Unknown Product",
            "product_club": prod.club if prod else "Unknown",
            "user_name": r.user_name,
            "rating": r.rating,
            "comment": r.comment,
            "image_url": r.image_url,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return {
        "items": result,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": pages
    }

@router.delete("/reviews/{review_id}")
def admin_delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("manager"))
):
    """Admin endpoint to delete a review and its images from Cloudinary."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    product_id = review.product_id

    # Delete image from Cloudinary
    if review.image_url:
        import cloudinary
        import cloudinary.uploader

        from ..config import settings
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True
        )
        
        def extract_id(url: str):
            if not url or "res.cloudinary.com" not in url:
                return None
            try:
                parts = url.split("/upload/")
                if len(parts) < 2:
                    return None
                path_part = parts[1]
                subparts = path_part.split("/")
                if subparts[0].startswith("v") and subparts[0][1:].isdigit():
                    subparts = subparts[1:]
                public_id_with_ext = "/".join(subparts)
                public_id, _ = os.path.splitext(public_id_with_ext)
                return public_id
            except Exception:
                return None

        public_id = extract_id(review.image_url)
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id)
            except Exception as e:
                print(f"Cloudinary review image deletion error: {e}")
        elif review.image_url.startswith("/static/uploads/reviews/"):
            local_path = review.image_url.lstrip("/")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print(f"Error removing local review image: {e}")

    db.delete(review)
    log_admin_action(db, admin.email, "REVIEW_DELETED", "review", str(review_id), {})
    db.commit()

    # Recalculate aggregates
    prod = db.query(Product).filter(Product.id == product_id).first()
    if prod:
        all_reviews = db.query(Review).filter(Review.product_id == product_id).all()
        total_reviews = len(all_reviews)
        avg_rating = sum(r.rating for r in all_reviews) / total_reviews if total_reviews > 0 else 4.8
        
        prod.rating = round(avg_rating, 1)
        prod.reviews = total_reviews
        db.commit()

    return {"success": True, "message": f"Review #{review_id} successfully deleted by admin."}


@router.get("/messages", response_model=PaginatedResponse[ContactMessageResponse])
def get_contact_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """Retrieve list of contact messages submitted by users."""
    query = db.query(ContactMessage).order_by(desc(ContactMessage.created_at))
    total = query.count()
    messages = query.offset(skip).limit(limit).all()
    pages = math.ceil(total / limit) if limit > 0 else 0
    return {
        "items": messages,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": pages
    }


@router.delete("/messages/{message_id}")
def delete_contact_message(
    message_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("manager"))
):
    """Delete a contact/support message by ID."""
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support message with ID {message_id} not found."
        )
    db.delete(msg)
    log_admin_action(db, admin.email, "MESSAGE_DELETED", "message", str(message_id), {})
    db.commit()
    return {"success": True, "message": f"Support message #{message_id} successfully deleted."}


import random

from ..models import OTPVerification
from ..schemas import (
    AdminAccessApprovalInput,
    AdminAccessRequestInput,
    AdminAccessVerifyInput,
    AdminChangePasswordInput,
)
from ..utils.email import send_access_approved, send_access_otp


@router.post("/access-requests/request")
def request_admin_access(
    payload: AdminAccessRequestInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Initiate an employee access request. Generates and mails an OTP."""
    email_clean = payload.email.strip().lower()
    
    if email_clean == "supportfreakfits@gmail.com":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request access for the super admin email address."
        )

    # Check database status
    existing = db.query(Admin).filter(Admin.email == email_clean).first()
    if existing:
        if existing.status == "approved":
            return {"success": True, "message": "Account already active. Please log in.", "approved": True}
        elif existing.status == "pending":
            return {"success": True, "message": "Request already pending. Please wait for super admin approval.", "pending": True}
        elif existing.status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your access request was previously rejected by the super admin."
            )

    # Generate 4-digit OTP
    otp_code = f"{random.randint(1000, 9999)}"
    
    # Save OTP to DB
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    otp_record = OTPVerification(
        email=email_clean,
        otp_code=otp_code,
        is_used=False,
        expires_at=expires_at
    )
    db.add(otp_record)
    db.commit()

    # Send OTP email
    background_tasks.add_task(send_access_otp, email_clean, otp_code)

    return {"success": True, "message": "OTP verification code sent to your email address."}


@router.post("/access-requests/verify")
def verify_admin_access(
    payload: AdminAccessVerifyInput,
    db: Session = Depends(get_db)
):
    """Verifies candidate OTP and creates a pending employee request in database."""
    email_clean = payload.email.strip().lower()
    
    # Fetch active OTP
    now_utc = datetime.utcnow()
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.email == email_clean,
        OTPVerification.otp_code == payload.otp_code,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > now_utc
    ).order_by(desc(OTPVerification.created_at)).first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # Mark OTP as used
    otp_record.is_used = True
    db.commit()

    # Create pending Admin record if not exists. We set full_name initially using the request info
    existing = db.query(Admin).filter(Admin.email == email_clean).first()
    if not existing:
        new_admin = Admin(
            full_name=payload.name.strip(),
            email=email_clean,
            hashed_password="", # Set on approval
            role="viewer",
            status="pending",
            is_active=True
        )
        db.add(new_admin)
        db.commit()
    
    return {
        "success": True,
        "message": "NOTE: your request for accessing FREAKFITS control center has been submitted to the super admin. please wait untill his approval."
    }


@router.get("/employees", response_model=list[AdminResponse])
def get_all_admins(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Get list of approved employees/admins (Super Admin only)."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee management is restricted to Super Admin."
        )
    return db.query(Admin).filter(Admin.status == "approved").order_by(desc(Admin.created_at)).offset(skip).limit(limit).all()


@router.delete("/employees/{admin_id}")
def revoke_employee_access(
    admin_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Revoke access for an approved employee (Super Admin only)."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee management is restricted to Super Admin."
        )
    employee = db.query(Admin).filter(Admin.id == admin_id, Admin.status == "approved").first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved employee not found."
        )
    if employee.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own access."
        )
    
    emp_email = employee.email
    db.delete(employee)
    log_admin_action(db, admin.email, "ADMIN_ACCESS_REVOKED", "admin", str(admin_id), {"email": emp_email})
    db.commit()
    
    return {"success": True, "message": "Employee access revoked."}


@router.get("/access-requests", response_model=list[AdminResponse])
def get_pending_access_requests(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Get list of pending employee access requests (Super Admin only)."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access requests management is restricted to Super Admin."
        )
    pending = db.query(Admin).filter(Admin.status == "pending").order_by(desc(Admin.created_at)).all()
    return pending


@router.post("/access-requests/{admin_id}/approve")
def approve_admin_access(
    admin_id: int,
    payload: AdminAccessApprovalInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Approve candidate, set role & password, and send email (Super Admin only)."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access approvals are restricted to Super Admin."
        )
        
    candidate = db.query(Admin).filter(Admin.id == admin_id, Admin.status == "pending").first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending access request not found."
        )

    # Set approved status, password and role
    candidate.status = "approved"
    candidate.role = payload.role
    candidate.hashed_password = get_password_hash(payload.password)
    log_admin_action(db, admin.email, "ADMIN_ACCESS_APPROVED", "admin", str(admin_id), payload.dict(exclude={"password"}))
    db.commit()

    # Send confirmation credentials email
    background_tasks.add_task(
        send_access_approved,
        recipient_email=candidate.email,
        recipient_name=candidate.full_name or "Employee",
        role=payload.role,
        password=payload.password
    )

    return {"success": True, "message": f"Access request approved successfully. Credentials email sent to {candidate.email}."}


@router.post("/access-requests/{admin_id}/reject")
def reject_admin_access(
    admin_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Reject candidate access request (Super Admin only)."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access rejections are restricted to Super Admin."
        )
        
    candidate = db.query(Admin).filter(Admin.id == admin_id, Admin.status == "pending").first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending access request not found."
        )

    candidate.status = "rejected"
    candidate.is_active = False
    log_admin_action(db, admin.email, "ADMIN_ACCESS_REJECTED", "admin", str(admin_id), {})
    db.commit()

    return {"success": True, "message": "Access request rejected."}


@router.post("/change-password")
def change_admin_password(
    payload: AdminChangePasswordInput,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """Allow any authenticated admin/employee to change their current password."""
    if not verify_password(payload.current_password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password."
        )

    if payload.new_password != payload.confirm_new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation password do not match."
        )

    admin.hashed_password = get_password_hash(payload.new_password)
    log_admin_action(db, admin.email, "ADMIN_PASSWORD_CHANGED", "admin", str(admin.id), {})
    db.commit()

    return {"success": True, "message": "Password changed successfully."}

@router.get("/newsletter")
def list_admin_newsletter(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("viewer"))
):
    """Retrieve all newsletter subscribers."""
    subscribers = db.query(NewsletterSubscriber).order_by(desc(NewsletterSubscriber.created_at)).offset(skip).limit(limit).all()
    return [
        {
            "id": s.id,
            "email": s.email,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in subscribers
    ]

# ==========================================
# API DOCS ACCESS MANAGEMENT
# ==========================================

from ..models import ApiDocsMaster, ApiDocsAccess
from ..schemas import ApiDocsMasterUpdate, ApiDocsAccessCreate, ApiDocsAccessResponse

@router.get("/docs-access/master")
def check_master_docs_credentials(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Check if master API docs credentials are configured in DB."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
    master = db.query(ApiDocsMaster).first()
    return {"configured": master is not None, "username": master.username if master else None}

@router.put("/docs-access/master")
def update_master_docs_credentials(
    payload: ApiDocsMasterUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Update or create master API docs credentials."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
    
    master = db.query(ApiDocsMaster).first()
    hashed_pwd = get_password_hash(payload.password)
    
    if master:
        master.username = payload.username
        master.hashed_password = hashed_pwd
    else:
        master = ApiDocsMaster(username=payload.username, hashed_password=hashed_pwd)
        db.add(master)
        
    log_admin_action(db, admin.email, "MASTER_CREDENTIALS_UPDATED", "docs", "master", {})
    db.commit()
    return {"success": True, "message": "Master credentials updated."}

@router.get("/docs-access/developers", response_model=list[ApiDocsAccessResponse])
def list_developer_access(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """List all third-party developer API access."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
    return db.query(ApiDocsAccess).order_by(desc(ApiDocsAccess.created_at)).all()

@router.post("/docs-access/developers", response_model=ApiDocsAccessResponse)
def grant_developer_access(
    payload: ApiDocsAccessCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Grant API access to a new developer."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
        
    existing = db.query(ApiDocsAccess).filter(ApiDocsAccess.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Access for this email already exists")
        
    dev = ApiDocsAccess(
        email=payload.email,
        hashed_password=get_password_hash(payload.password)
    )
    db.add(dev)
    log_admin_action(db, admin.email, "DEVELOPER_ACCESS_GRANTED", "docs", str(dev.id), payload.dict(exclude={"password"}))
    db.commit()
    db.refresh(dev)
    return dev

@router.delete("/docs-access/developers/{access_id}")
def revoke_developer_access(
    access_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Revoke (delete) developer API access."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
        
    dev = db.query(ApiDocsAccess).filter(ApiDocsAccess.id == access_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Access not found")
        
    db.delete(dev)
    log_admin_action(db, admin.email, "DEVELOPER_ACCESS_REVOKED", "docs", str(access_id), {})
    db.commit()
    return {"success": True, "message": "Access revoked"}

@router.put("/docs-access/developers/{access_id}/reset-ip")
def reset_developer_ip(
    access_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("super_admin"))
):
    """Reset the IP binding for a developer."""
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin only")
        
    dev = db.query(ApiDocsAccess).filter(ApiDocsAccess.id == access_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Access not found")
        
    dev.bound_ip = None
    log_admin_action(db, admin.email, "DEVELOPER_IP_RESET", "docs", str(access_id), {})
    db.commit()
    return {"success": True, "message": "IP binding reset successfully."}