import datetime
import os
import random
import smtplib
import logging
from typing import List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..limiter import limiter
from ..models import User, OTPVerification, get_ist_time, Address, Product, Wishlist
from ..schemas import (
    SendOTPRequest, SendOTPResponse,
    VerifyOTPRequest, VerifyOTPResponse,
    RegisterRequest, LoginRequest,
    TokenResponse, UserResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
    AddressCreate, AddressResponse,
    UserUpdate, ChangePasswordRequest,
    WishlistResponse, WishlistCreate
)
from ..security import (
    verify_password, get_password_hash,
    create_access_token, require_current_user
)

logger = logging.getLogger("uvicorn")
router = APIRouter(prefix="/auth", tags=["Authentication"])

def send_email_via_smtp(to_email: str, otp_code: str) -> bool:
    """Send OTP email using SMTP if configured."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(f"[FreakFits OTP] SMTP not configured in .env. OTP for {to_email} is: {otp_code}")
        return False

    try:
        sender_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        sender_name = settings.SMTP_FROM_NAME or "FreakFits Official"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your FreakFits Verification Code: {otp_code}"
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to_email

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d0e12; color: #f4f5f8; padding: 24px;">
          <div style="max-width: 500px; margin: 0 auto; background: #161820; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px; text-align: center;">
            <h1 style="color: #8CFF3B; font-size: 28px; margin-bottom: 8px; font-weight: 800; letter-spacing: -0.5px;">Freak<em>Fits</em></h1>
            <p style="color: #8c8f9f; font-size: 15px; margin-bottom: 24px;">Authentic Matchday Kit Hub</p>
            <p style="font-size: 16px; color: #e2e4ea; margin-bottom: 20px;">Use the verification code below to verify your email address and activate your account:</p>
            <div style="background: rgba(140, 255, 59, 0.08); border: 2px dashed #8CFF3B; border-radius: 12px; padding: 18px; margin: 24px 0;">
              <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #8CFF3B; display: inline-block;">{otp_code}</span>
            </div>
            <p style="color: #8c8f9f; font-size: 13px; line-height: 1.5;">This code is valid for <strong>10 minutes</strong>. If you did not request this code, please ignore this email.</p>
          </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender_email, to_email, msg.as_string())

        logger.info(f"Successfully sent OTP email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


@router.post("/send-otp", response_model=SendOTPResponse)
@limiter.limit("5/minute")
def send_otp(request: Request, payload: SendOTPRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    
    # Generate genuine 4-digit OTP code
    otp_code = f"{random.randint(1000, 9999)}"
    
    # Invalidate previous unverified OTPs for this email
    db.query(OTPVerification).filter(OTPVerification.email == email).delete()
    
    # Save new OTP with 10-minute expiration in MySQL
    expires_at = get_ist_time() + datetime.timedelta(minutes=10)
    otp_record = OTPVerification(
        email=email,
        otp_code=otp_code,
        expires_at=expires_at,
        is_used=False
    )
    db.add(otp_record)
    db.commit()

    # Attempt to dispatch real email via SMTP
    email_sent = send_email_via_smtp(email, otp_code)

    msg = f"OTP verification code sent to {email}" if email_sent else f"OTP generated for {email}"
    
    # Do not return otp_code to the client
    return SendOTPResponse(
        success=True,
        message=msg,
        demo_otp=None
    )


@router.post("/verify-otp", response_model=VerifyOTPResponse)
def verify_otp(payload: VerifyOTPRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    code = payload.otp_code.strip()

    # Find active OTP matching email to count failures
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.email == email,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > get_ist_time()
    ).first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active verification code found for this email. Please request a new one."
        )

    if otp_record.otp_code != code:
        otp_record.failed_attempts += 1
        db.commit()
        if otp_record.failed_attempts >= 3:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed verification attempts. This OTP has been invalidated. Please request a new code."
            )
        
        remaining = 3 - otp_record.failed_attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP code. You have {remaining} attempt(s) remaining."
        )

    # Mark OTP as consumed
    otp_record.is_used = True
    db.commit()

    return VerifyOTPResponse(
        success=True,
        message="Email successfully verified.",
        is_verified=True
    )

@router.post("/register", response_model=TokenResponse)
def register(response: Response, payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    # Create new User
    hashed_pwd = get_password_hash(payload.password)
    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        mobile_number=payload.mobile_number.strip() if payload.mobile_number else None,
        hashed_password=hashed_pwd,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Issue JWT token
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Set HttpOnly Cookie (secure=True ensures HTTPS-only transmission)
    is_production = os.getenv("ENVIRONMENT", "production") == "production"
    response.set_cookie(
        key="freakfits_jwt_token",
        value=access_token,
        httponly=True,
        secure=is_production,
        samesite="lax"
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Set HttpOnly Cookie (secure=True ensures HTTPS-only transmission)
    is_production = os.getenv("ENVIRONMENT", "production") == "production"
    response.set_cookie(
        key="freakfits_jwt_token",
        value=access_token,
        httponly=True,
        secure=is_production,
        samesite="lax"
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(require_current_user)):
    return current_user

@router.put("/me", response_model=UserResponse)
def update_current_user_profile(
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    if update_data.full_name is not None:
        current_user.full_name = update_data.full_name
    if update_data.mobile_number is not None:
        current_user.mobile_number = update_data.mobile_number
        
    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/change-password")
def change_user_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
        
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"success": True, "message": "Password updated successfully"}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email address is not registered."
        )
    
    # Generate 4-digit OTP code
    otp_code = f"{random.randint(1000, 9999)}"
    
    # Invalidate previous unverified OTPs for this email
    db.query(OTPVerification).filter(OTPVerification.email == email).delete()
    
    # Save new OTP with 10-minute expiration
    expires_at = get_ist_time() + datetime.timedelta(minutes=10)
    otp_record = OTPVerification(
        email=email,
        otp_code=otp_code,
        expires_at=expires_at,
        is_used=False
    )
    db.add(otp_record)
    db.commit()

    # Attempt to dispatch real email via SMTP
    email_sent = send_email_via_smtp(email, otp_code)
    
    return {"success": True, "message": "If this email is registered, an OTP verification code has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    password = payload.password
    confirm_password = payload.confirm_password

    if password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters."
        )

    # Check if user exists
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Check recently verified OTP
    from sqlalchemy import desc
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.email == email,
        OTPVerification.is_used == True
    ).order_by(desc(OTPVerification.created_at)).first()

    if not otp_record or otp_record.created_at < get_ist_time() - datetime.timedelta(minutes=15):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification expired or not completed. Please verify again."
        )

    # Update password
    user.hashed_password = get_password_hash(password)
    user.is_verified = True
    db.commit()

    # Clean up OTP record to prevent reuse
    db.delete(otp_record)
    db.commit()

    return {"success": True, "message": "Password reset successfully. Please login again."}


# ============ ADDRESS ENDPOINTS ============

@router.post("/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_address(
    payload: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    address = Address(
        user_id=current_user.id,
        address_type=payload.address_type,
        full_name=payload.full_name,
        phone=payload.phone,
        street_address=payload.street_address,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        country=payload.country
    )
    db.add(address)
    db.commit()
    db.refresh(address)
    return address

@router.get("/addresses", response_model=List[AddressResponse])
def list_addresses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    return db.query(Address).filter(Address.user_id == current_user.id).all()

@router.put("/addresses/{address_id}", response_model=AddressResponse)
def update_address(
    address_id: int,
    payload: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found."
        )
    
    address.address_type = payload.address_type
    address.full_name = payload.full_name
    address.phone = payload.phone
    address.street_address = payload.street_address
    address.city = payload.city
    address.state = payload.state
    address.postal_code = payload.postal_code
    address.country = payload.country
    
    db.commit()
    db.refresh(address)
    return address

@router.delete("/addresses/{address_id}", status_code=status.HTTP_200_OK)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    db.delete(address)
    db.commit()
    
    return {"message": "Address deleted successfully"}

# ============ WISHLIST ENDPOINTS ============

@router.post("/wishlist", response_model=WishlistResponse, status_code=status.HTTP_201_CREATED)
def add_to_wishlist(
    item: WishlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    product = db.query(Product).filter(Product.id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    existing = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.product_id == item.product_id
    ).first()
    if existing:
        return existing
        
    new_item = Wishlist(
        user_id=current_user.id,
        product_id=item.product_id
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@router.get("/wishlist", response_model=List[WishlistResponse])
def get_wishlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    items = db.query(Wishlist).filter(Wishlist.user_id == current_user.id).all()
    return items

@router.delete("/wishlist/{product_id}", status_code=status.HTTP_200_OK)
def remove_from_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    item = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.product_id == product_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not in wishlist")
        
    db.delete(item)
    db.commit()
    return {"message": "Item removed from wishlist"}
