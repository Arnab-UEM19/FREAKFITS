
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..limiter import limiter
from ..models import ContactMessage

router = APIRouter(prefix="/contact", tags=["Contact"])

class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    reason: str
    message: str | None = None

@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
def submit_contact_message(request: Request, payload: ContactCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason for reaching out is required.")

    msg = ContactMessage(
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        reason=payload.reason.strip(),
        message=payload.message.strip() if payload.message else None
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "success": True,
        "message": "Thank you for reaching out! Our support team will get back to you shortly.",
        "id": msg.id
    }
