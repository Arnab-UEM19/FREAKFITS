import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, ReturnRequest, User
from ..security import require_current_user

router = APIRouter(prefix="/returns", tags=["Returns"])

# Define directory to save returns videos
UPLOAD_DIR = os.path.join("static", "uploads", "returns")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_return_request(
    order_code: str = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    return_type: str = Form(...),
    current_size: str | None = Form(None),
    requested_size: str | None = Form(None),
    reason_details: str | None = Form(None),
    terms_accepted: bool = Form(...),
    video: UploadFile | None = File(None),
    video_url: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    # Use authenticated user details
    verified_email = current_user.email
    verified_name = current_user.full_name or customer_name
    if not terms_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the terms and conditions to initiate a return request."
        )

    if not order_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order Code / Order ID is required."
        )

    # 10MB limit: 10 * 1024 * 1024 bytes
    MAX_FILE_SIZE = 10 * 1024 * 1024

    video_proof_path = ""

    ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}

    if video and video.filename:
        # Check size by reading
        content = await video.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video file exceeds the 10MB limit (Size: {file_size / (1024 * 1024):.2f} MB)."
            )
        await video.seek(0)

        # Secure filename using uuid extension
        _, ext = os.path.splitext(video.filename)
        if not ext or ext.lower() not in ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only video files are allowed ({', '.join(ALLOWED_VIDEO_EXTENSIONS)})."
            )
        safe_filename = f"{uuid.uuid4().hex}{ext.lower()}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        video_proof_path = f"/static/uploads/returns/{safe_filename}"
    elif video_url and video_url.strip():
        url = video_url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Video URL must start with http:// or https://"
            )
        allowed_domains = ["youtube.com", "youtu.be", "drive.google.com"]
        if not any(domain in url.lower() for domain in allowed_domains):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only YouTube or Google Drive links are accepted for video proof. Otherwise, please upload the file directly."
            )
        video_proof_path = url
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An uncut unboxing video proof is mandatory for all return requests."
        )

    # Verify order exists and belongs to the authenticated user
    clean_order_code = order_code.strip().upper()
    order = db.query(Order).filter(Order.order_code == clean_order_code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    if order.user_id != current_user.id and order.customer_email.lower() != verified_email.lower():
        raise HTTPException(
            status_code=403, 
            detail="You are not authorized to initiate a return for this order."
        )

    return_code = f"RET-{uuid.uuid4().hex[:8].upper()}"

    ret = ReturnRequest(
        return_code=return_code,
        order_code=clean_order_code,
        customer_name=verified_name.strip(),
        customer_email=verified_email.lower().strip(),
        return_type=return_type.strip(),
        current_size=current_size.strip() if current_size else None,
        requested_size=requested_size.strip() if requested_size else None,
        video_proof=video_proof_path,
        reason_details=reason_details.strip() if reason_details else None,
        terms_accepted=terms_accepted,
        status="PENDING_REVIEW"
    )

    db.add(ret)
    db.commit()
    db.refresh(ret)

    return {
        "success": True,
        "return_code": ret.return_code,
        "status": ret.status,
        "message": (
            "Return request initiated successfully! Our quality control team will review your unboxing video. "
            "For size exchanges, your refund for the returned kit will be processed within 48 hours of dispatch."
        )
    }
