import os
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..config import settings
from ..database import get_db
from ..models import Admin, Order, OrderItem, Product, ReturnRequest, Review, ContactMessage, NewsletterSubscriber
from ..schemas import (
    AdminLoginRequest, AdminResponse, AdminTokenResponse, AdminStatsResponse,
    OrderResponse, OrderStatusUpdate,
    ProductResponse, ProductCreateAdmin, ProductUpdateAdmin, ReturnStatusUpdate,
    ContactMessageResponse
)
from ..security import verify_password, get_password_hash, create_access_token, require_current_admin

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


@router.post("/login", response_model=AdminTokenResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
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
    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": admin
    }


@router.get("/me", response_model=AdminResponse)
def get_admin_profile(admin: Admin = Depends(require_current_admin)):
    """Get profile of current authenticated admin."""
    return admin


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(db: Session = Depends(get_db), admin: Admin = Depends(require_current_admin)):
    """Compute live dashboard metrics."""
    orders = db.query(Order).all()
    today_revenue = sum(o.total for o in orders)
    active_orders = sum(1 for o in orders if (o.order_status or "Pending") != "Delivered")
    
    products = db.query(Product).filter(Product.is_active == True).all()
    low_stock_count = 0
    for p in products:
        stock_dict = p.stock or {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5}
        if any(int(qty) <= 2 for qty in stock_dict.values()):
            low_stock_count += 1

    pending_returns = db.query(ReturnRequest).filter(ReturnRequest.status == "PENDING_REVIEW").count()

    return {
        "today_revenue": round(today_revenue, 2),
        "active_orders": active_orders,
        "low_stock_count": low_stock_count,
        "total_products": len(products),
        "pending_returns": pending_returns
    }


@router.get("/orders", response_model=List[OrderResponse])
def list_admin_orders(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """List all customer orders with fulfillment items."""
    query = db.query(Order).order_by(desc(Order.created_at))
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Order.order_status == status_filter)
    
    orders = query.all()
    return orders


@router.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Update order fulfillment status (Pending, Shipped, Delivered)."""
    if admin.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Viewer role has read-only access."
        )
    order = db.query(Order).filter((Order.order_code == order_id) | (Order.id == int(order_id) if order_id.isdigit() else False)).first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")

    old_status = order.order_status or "Pending"
    
    if payload.order_status.lower() == "refunded":
        db.delete(order)
        db.commit()
        return {
            "success": True,
            "order_code": order_id,
            "order_status": "REFUNDED_DELETED",
            "message": f"Order {order_id} was refunded and deleted from the database."
        }

    order.order_status = payload.order_status
    db.commit()
    db.refresh(order)
    
    # Send shipping email notification if status transitioned to Shipped
    if payload.order_status.lower() == "shipped" and old_status.lower() != "shipped":
        from ..utils.email import send_shipping_notification
        send_shipping_notification(
            recipient_email=order.customer_email,
            recipient_name=order.customer_name or "FreakFan",
            order_code=order.order_code,
            customer_phone=order.customer_phone or ""
        )

    return {
        "success": True,
        "order_code": order.order_code,
        "order_status": order.order_status,
        "message": f"Order {order.order_code} status updated to {order.order_status}."
    }


@router.get("/products", response_model=List[ProductResponse])
def list_admin_products(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """List all products with stock inventory."""
    return db.query(Product).order_by(desc(Product.id)).all()


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_admin_product(
    payload: ProductCreateAdmin,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Create a new jersey in catalog."""
    if admin.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Viewer role has read-only access."
        )
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
    db.commit()
    db.refresh(new_prod)
    return new_prod


from sqlalchemy.orm.attributes import flag_modified

@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_admin_product(
    product_id: int,
    payload: ProductUpdateAdmin,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Update price, stock, size_prices, size_was_prices or status of a jersey."""
    if admin.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Viewer role has read-only access."
        )
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

    db.commit()
    db.refresh(prod)
    return prod


@router.delete("/products/{product_id}")
def delete_admin_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Delete a product from the database."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Delete operations require super admin privileges."
        )
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found.")

    db.delete(prod)
    db.commit()
    return {"success": True, "message": f"Product #{product_id} deleted successfully."}


@router.get("/returns")
def list_admin_returns(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """List all customer return and exchange claim requests."""
    query = db.query(ReturnRequest).order_by(desc(ReturnRequest.created_at))
    if status_filter and status_filter.lower() != "all":
        query = query.filter(ReturnRequest.status == status_filter.upper())
    
    returns_list = query.all()
    return [
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


@router.patch("/returns/{return_code}/status")
def update_return_status(
    return_code: str,
    payload: ReturnStatusUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Update claim status (PENDING_REVIEW, APPROVED, REFUNDED, REJECTED)."""
    if admin.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Viewer role has read-only access."
        )
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
        db.commit()
        return {
            "success": True,
            "return_code": return_code,
            "status": f"{payload.status}_DELETED",
            "message": f"Return claim {return_code} was {payload.status} and deleted from database and storage."
        }

    ret.status = payload.status
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
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Retrieve all customer reviews for moderation."""
    reviews = db.query(Review).order_by(Review.created_at.desc()).all()
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
    return result

@router.delete("/reviews/{review_id}")
def admin_delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Admin endpoint to delete a review and its images from Cloudinary."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Delete operations require super admin privileges."
        )
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


@router.get("/messages", response_model=List[ContactMessageResponse])
def get_contact_messages(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Retrieve list of contact messages submitted by users."""
    messages = db.query(ContactMessage).order_by(desc(ContactMessage.created_at)).all()
    return messages


@router.delete("/messages/{message_id}")
def delete_contact_message(
    message_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Delete a contact/support message by ID."""
    if admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action denied. Delete operations require super admin privileges."
        )
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support message with ID {message_id} not found."
        )
    db.delete(msg)
    db.commit()
    return {"success": True, "message": f"Support message #{message_id} successfully deleted."}


import random
from ..models import OTPVerification
from ..utils.email import send_access_otp, send_access_approved
from ..schemas import (
    AdminAccessRequestInput, AdminAccessVerifyInput, AdminAccessApprovalInput,
    AdminChangePasswordInput
)

@router.post("/access-requests/request")
def request_admin_access(
    payload: AdminAccessRequestInput,
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
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    otp_record = OTPVerification(
        email=email_clean,
        otp_code=otp_code,
        is_used=False,
        expires_at=expires_at
    )
    db.add(otp_record)
    db.commit()

    # Send OTP email
    send_access_otp(email_clean, otp_code)

    return {"success": True, "message": "OTP verification code sent to your email address."}


@router.post("/access-requests/verify")
def verify_admin_access(
    payload: AdminAccessVerifyInput,
    db: Session = Depends(get_db)
):
    """Verifies candidate OTP and creates a pending employee request in database."""
    email_clean = payload.email.strip().lower()
    
    # Fetch active OTP
    now_utc = datetime.datetime.utcnow()
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


@router.get("/access-requests", response_model=List[AdminResponse])
def get_pending_access_requests(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
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
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
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
    db.commit()

    # Send confirmation credentials email
    send_access_approved(
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
    admin: Admin = Depends(require_current_admin)
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
    db.commit()

    return {"success": True, "message": "Access request rejected."}


@router.post("/change-password")
def change_admin_password(
    payload: AdminChangePasswordInput,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
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
    db.commit()

    return {"success": True, "message": "Password changed successfully."}

@router.get("/newsletter")
def list_admin_newsletter(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_current_admin)
):
    """Retrieve all newsletter subscribers."""
    subscribers = db.query(NewsletterSubscriber).order_by(desc(NewsletterSubscriber.created_at)).all()
    return [
        {
            "id": s.id,
            "email": s.email,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in subscribers
    ]

