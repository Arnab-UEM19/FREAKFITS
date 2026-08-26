import datetime

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Admin, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def get_token_from_request(request: Request) -> str | None:
    # 1. Check cookies first
    token = request.cookies.get("access_token")
    if token:
        return token
    # 2. Fallback to Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        password_bytes = plain_password.encode('utf-8')[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: datetime.timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        email: str = payload.get("sub")
        iat: int = payload.get("iat")
        if email is None:
            return None
    except jwt.PyJWTError:
        return None

    user = db.query(User).filter(User.email == email).first()
    if user and user.password_changed_at and iat:
        # If token was issued before the password was last changed, it's invalid
        if datetime.datetime.utcfromtimestamp(iat) < user.password_changed_at:
            return None
    return user

def require_current_user(user: User | None = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials are required or invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Admin | None:
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        iat: int = payload.get("iat")
        if email is None or role not in ["admin", "super_admin"]:
            return None
    except jwt.PyJWTError:
        return None

    admin = db.query(Admin).filter(
        Admin.email == email,
        Admin.is_active == True,
        Admin.status == "approved"
    ).first()
    
    if admin and admin.password_changed_at and iat:
        if datetime.datetime.utcfromtimestamp(iat) < admin.password_changed_at:
            return None
            
    return admin

def require_current_admin(admin: Admin | None = Depends(get_current_admin)) -> Admin:
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required or session expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return admin

def require_role(min_role: str):
    def role_checker(admin: Admin = Depends(require_current_admin)) -> Admin:
        role_hierarchy = {"viewer": 1, "manager": 2, "super_admin": 3}
        admin_level = role_hierarchy.get(admin.role, 0)
        req_level = role_hierarchy.get(min_role, 0)
        
        if admin_level < req_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action denied. This endpoint requires at least '{min_role}' privileges."
            )
        return admin
    return role_checker
