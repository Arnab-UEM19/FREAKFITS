import logging
import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .config import settings
from .database import engine, Base, get_db
from .seed import seed_database
from .routers import auth, products, orders, coupons, contact, returns, admin, payments
from .security import require_current_user
from .models import User
from .schemas import OrderResponse, NewsletterSubscribeRequest, NewsletterResponse
from typing import List
from .limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

is_production = os.getenv("ENVIRONMENT", "production") == "production"

app = FastAPI(
    title="FreakFits API",
    description="Backend API for FreakFits football jersey e-commerce platform with MySQL database",
    version="1.0.0",
    docs_url=None if is_production else "/api/docs",
    redoc_url=None if is_production else "/api/redoc",
    openapi_url=None if is_production else "/api/openapi.json"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
import os

# Ensure static directories exist and mount
os.makedirs("static/uploads/reviews", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Startup Event: Create tables & seed data
@app.on_event("startup")
def on_startup():
    logger.info("Starting FreakFits FastAPI backend...")
    try:
        seed_database()
        logger.info("Database initialized and ready.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

# Include API Routers
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(coupons.router, prefix="/api")
app.include_router(contact.router, prefix="/api")
app.include_router(returns.router, prefix="/api")
app.include_router(payments.router, prefix="/api")

@app.get("/api/customer/orders/{customer_email}", response_model=List[OrderResponse], tags=["Orders"])
def get_customer_orders_by_email(
    customer_email: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    from .models import Order
    
    # Restrict access to owner only
    if current_user.email.lower().strip() != customer_email.lower().strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only fetch your own order history."
        )

    email_clean = customer_email.lower().strip()
    orders = db.query(Order).filter(
        Order.customer_email == email_clean
    ).order_by(Order.created_at.desc()).all()
    return orders

@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app": "FreakFits API",
        "version": "1.0.0",
        "database": settings.DB_NAME
    }

@app.post("/api/newsletter/subscribe", response_model=NewsletterResponse, tags=["Newsletter"])
def subscribe_newsletter(data: NewsletterSubscribeRequest, db: Session = Depends(get_db)):
    from .models import NewsletterSubscriber
    email_clean = data.email.lower().strip()
    
    existing = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email_clean).first()
    if existing:
        # Already subscribed
        return {"message": "You are already subscribed to our newsletter!"}
        
    new_sub = NewsletterSubscriber(email=email_clean)
    db.add(new_sub)
    db.commit()
    return {"message": "Successfully subscribed to the newsletter!"}

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to FreakFits API. Visit /api/docs for interactive Swagger documentation."
    }
