from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Coupon, Order
from ..schemas import (
    CouponAdminResponse,
    CouponCreateAdmin,
    CouponResponse,
    CouponValidateRequest,
)
from ..security import require_role, get_current_admin, get_current_user

router = APIRouter(prefix="/coupons", tags=["Coupons"])

@router.post("/validate", response_model=CouponResponse)
def validate_coupon(
    payload: CouponValidateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    code = payload.code.upper().strip()
    coupon = db.query(Coupon).filter(Coupon.code == code, Coupon.is_active == True).first()
    
    if not coupon:
        return CouponResponse(
            valid=False,
            code=code,
            discount_percent=0.0,
            label="",
            message="Invalid or expired coupon code."
        )

    # Global limit check
    if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
        return CouponResponse(
            valid=False,
            code=code,
            discount_percent=0.0,
            label="",
            message="This coupon has reached its usage limit."
        )

    # Per-account check (if user is authenticated)
    current_user = get_current_user(request, db)
    if current_user:
        used_order = db.query(Order).filter(
            Order.user_id == current_user.id,
            Order.coupon_code == coupon.code,
            Order.payment_status.in_(["PAID", "COMPLETED"])
        ).first()
        if used_order:
            return CouponResponse(
                valid=False,
                code=code,
                discount_percent=0.0,
                label="",
                message="You have already used this coupon."
            )

    return CouponResponse(
        valid=True,
        code=coupon.code,
        discount_percent=coupon.discount_percent,
        label=coupon.label,
        message=f"{coupon.label} applied successfully!"
    )

@router.get("/admin/list", response_model=list[CouponAdminResponse])
def get_all_coupons(db: Session = Depends(get_db), current_admin=Depends(require_role("viewer"))):
    """Fetch all coupons for admin dashboard"""
    return db.query(Coupon).order_by(Coupon.id.desc()).all()

@router.post("/admin/create", response_model=CouponAdminResponse)
def create_coupon(payload: CouponCreateAdmin, db: Session = Depends(get_db), current_admin=Depends(require_role("manager"))):
    """Create a new coupon (Admin only)"""
    code = payload.code.upper().strip()
    existing = db.query(Coupon).filter(Coupon.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists")
    
    new_coupon = Coupon(
        code=code,
        discount_percent=payload.discount_percent,
        label=payload.label,
        is_active=payload.is_active,
        usage_limit=payload.usage_limit
    )
    db.add(new_coupon)
    db.commit()
    db.refresh(new_coupon)
    return new_coupon

@router.patch("/admin/{coupon_id}/toggle", response_model=CouponAdminResponse)
def toggle_coupon(coupon_id: int, db: Session = Depends(get_db), current_admin=Depends(require_role("manager"))):
    """Toggle a coupon's active status"""
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    
    coupon.is_active = not coupon.is_active
    db.commit()
    db.refresh(coupon)
    return coupon

@router.delete("/admin/{coupon_id}")
def delete_coupon(coupon_id: int, db: Session = Depends(get_db), current_admin=Depends(require_role("manager"))):
    """Hard delete a coupon (Admin only)"""
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    
    db.delete(coupon)
    db.commit()
    return {"message": "Coupon deleted successfully"}
