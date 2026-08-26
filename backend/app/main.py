import logging
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .limiter import limiter
from .models import User, ApiDocsMaster, ApiDocsAccess
from .routers import (
    admin,
    auth,
    cart,
    contact,
    coupons,
    orders,
    payments,
    products,
    returns,
)
from .schemas import NewsletterResponse, NewsletterSubscribeRequest, OrderResponse
from .security import require_current_user, verify_password
from .seed import seed_database

os.makedirs("logs", exist_ok=True)

class PapertrailHTTPHandler(logging.Handler):
    def __init__(self, url, token):
        super().__init__()
        self.url = url
        self.token = token
        self.executor = ThreadPoolExecutor(max_workers=1)

    def emit(self, record):
        log_entry = self.format(record)
        self.executor.submit(self.send_log, log_entry)
        
    def send_log(self, log_entry):
        try:
            req = urllib.request.Request(self.url, data=log_entry.encode('utf-8'), method='POST')
            req.add_header('Authorization', f'Bearer {self.token}')
            req.add_header('Content-Type', 'text/plain')
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

file_handler = RotatingFileHandler("logs/freakfits.log", maxBytes=5*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

if settings.PAPERTRAIL_URL and settings.PAPERTRAIL_TOKEN:
    pt_handler = PapertrailHTTPHandler(settings.PAPERTRAIL_URL, settings.PAPERTRAIL_TOKEN)
    pt_handler.setFormatter(logging.Formatter("FreakFits-API: %(levelname)s - %(message)s"))
    logger.addHandler(pt_handler)

is_production = os.getenv("ENVIRONMENT", "production") == "production"

app = FastAPI(
    title="FreakFits API",
    description="Backend API for FreakFits football jersey e-commerce platform with MySQL database",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

import secrets
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def get_current_username(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    # 1. Check Master Credentials first
    master = db.query(ApiDocsMaster).first()
    if master:
        correct_username = secrets.compare_digest(credentials.username, master.username)
        if correct_username and verify_password(credentials.password, master.hashed_password):
            return credentials.username
    else:
        # Fallback to .env if master not configured in DB yet
        correct_username = secrets.compare_digest(credentials.username, settings.ADMIN_DOCS_USERNAME)
        correct_password = secrets.compare_digest(credentials.password, settings.ADMIN_DOCS_PASSWORD)
        if correct_username and correct_password:
            return credentials.username

    # 2. Check Third-Party Developer Access
    dev = db.query(ApiDocsAccess).filter(ApiDocsAccess.email == credentials.username).first()
    if not dev or not dev.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    if not verify_password(credentials.password, dev.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # 3. Validate IP Binding
    client_ip = request.client.host
    if request.headers.get("X-Forwarded-For"):
        client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()

    if dev.bound_ip is None:
        # Bind the IP on first successful login
        dev.bound_ip = client_ip
        db.commit()
    elif dev.bound_ip != client_ip:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not authorized. IP address mismatch.",
        )
        
    return credentials.username

@app.get("/api/docs", include_in_schema=False)
async def get_swagger_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="Docs")

@app.get("/api/redoc", include_in_schema=False)
async def get_redoc_documentation(username: str = Depends(get_current_username)):
    return get_redoc_html(openapi_url="/api/openapi.json", title="Redoc")

@app.get("/api/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title=app.title, version=app.version, routes=app.routes)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
origins = [
    origin.strip() 
    for origin in settings.CORS_ORIGINS.split(",") 
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval';"
        return response

app.add_middleware(SecurityHeadersMiddleware)

import traceback

from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled exception: {exc!s}\n{traceback.format_exc()}")
    logger.error(f"Unhandled exception: {exc!s}\n{traceback.format_exc()}")
    
    is_debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    content = {"detail": "An unexpected error occurred. Please try again later."}
    
    if is_debug:
        content["traceback"] = traceback.format_exc()
        
    return JSONResponse(
        status_code=500,
        content=content
    )

import os

from fastapi.staticfiles import StaticFiles

# Ensure static directories exist and mount
os.makedirs("static/uploads/reviews", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Startup Event: Create tables & seed data
@app.on_event("startup")
def on_startup():
    logger.info("Starting FreakFits FastAPI backend...")
    
    # 1. Validate Critical Environment Variables
    required_vars = ["JWT_SECRET_KEY", "DB_PASSWORD"]
    missing = [var for var in required_vars if not getattr(settings, var, None)]
    if missing:
        error_msg = f"CRITICAL STARTUP FAILURE: Missing required environment variables: {', '.join(missing)}"
        logger.critical(error_msg)
        import sys
        sys.exit(1)
        
    try:
        if os.getenv("ENVIRONMENT") != "testing":
            seed_database()
            logger.info("Database initialized and ready.")
        else:
            logger.info("Skipping database seeding in testing environment.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

# Include API Routers
app.include_router(cart.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(coupons.router, prefix="/api")
app.include_router(contact.router, prefix="/api")
app.include_router(returns.router, prefix="/api")
app.include_router(payments.router, prefix="/api")

@app.get("/api/customer/orders/{customer_email}", response_model=list[OrderResponse], tags=["Orders"])
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
