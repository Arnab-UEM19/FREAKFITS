import datetime
from typing import List, Optional, Generic, TypeVar
from pydantic import BaseModel, EmailStr, Field, field_validator

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

# ============ AUTH SCHEMAS ============

class SendOTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "register"

class SendOTPResponse(BaseModel):
    success: bool
    message: str
    demo_otp: Optional[str] = None

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=4, max_length=6)
    purpose: str = "register"

class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    is_verified: bool

class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    mobile_number: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(char.isalpha() for char in v) or not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one letter and one number")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    mobile_number: Optional[str] = Field(None, max_length=20)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

class DeleteAccountRequest(BaseModel):
    password: str
    confirmation: str = Field(..., description="Must equal the literal string 'DELETE' to confirm intent")

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, v: str) -> str:
        if v.strip().upper() != "DELETE":
            raise ValueError("You must type DELETE to confirm account deletion")
        return v

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    mobile_number: Optional[str] = None
    is_verified: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ============ PRODUCT SCHEMAS ============

class ProductResponse(BaseModel):
    id: int
    name: str
    club: str
    price: float
    was_price: Optional[float] = None
    category: str
    color: str
    rating: float
    reviews: int
    badge: Optional[str] = None
    badge_bg: Optional[str] = None
    material: str
    fit: str
    care: str
    images: List[str]
    stock: Optional[dict] = None
    size_prices: Optional[dict] = None
    size_was_prices: Optional[dict] = None
    is_active: bool

    class Config:
        from_attributes = True

class ProductCreateAdmin(BaseModel):
    name: str
    club: str
    price: float = Field(..., ge=0)
    was_price: Optional[float] = Field(None, ge=0)
    category: str
    badge: Optional[str] = None
    images: List[str]
    stock: Optional[dict] = Field(default_factory=lambda: {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5})
    size_prices: Optional[dict] = None
    size_was_prices: Optional[dict] = None

class ProductUpdateAdmin(BaseModel):
    name: Optional[str] = None
    club: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    was_price: Optional[float] = Field(None, ge=0)
    stock: Optional[dict] = None
    size_prices: Optional[dict] = None
    size_was_prices: Optional[dict] = None
    badge: Optional[str] = None
    is_active: Optional[bool] = None


# ============ ORDER SCHEMAS ============

class OrderItemCreate(BaseModel):
    product_id: int
    product_name: str
    club: Optional[str] = None
    size: str
    custom_name: Optional[str] = None
    custom_number: Optional[str] = None
    quantity: int = Field(default=1, gt=0)
    unit_price: float

class OrderCreate(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    items: List[OrderItemCreate]
    coupon_code: Optional[str] = None
    payment_method: str
    shipping_address: Optional[str] = None

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    club: Optional[str]
    size: str
    custom_name: Optional[str]
    custom_number: Optional[str]
    quantity: int
    unit_price: float
    line_total: float

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    order_code: str
    customer_name: str
    customer_email: str
    customer_phone: Optional[str]
    subtotal: float
    discount: float
    shipping_fee: float
    total: float
    coupon_code: Optional[str]
    payment_method: str
    payment_status: str
    order_status: Optional[str] = "Pending"
    shipping_address: Optional[str] = None
    created_at: datetime.datetime
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    order_status: str = Field(..., pattern="^(Pending|Preparing Kit|Packing|Shipped|Delivered|Cancelled|Refunded)$")


# ============ ADMIN SCHEMAS ============

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AdminResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminResponse

class AdminStatsResponse(BaseModel):
    today_revenue: float
    revenue_change_percentage: Optional[float] = None
    active_orders: int
    low_stock_count: int
    total_products: int
    pending_returns: Optional[int] = 0

class ReturnStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(PENDING_REVIEW|APPROVED|REFUNDED|REJECTED)$")


# ============ COUPON SCHEMAS ============

class CouponValidateRequest(BaseModel):
    code: str

class CouponResponse(BaseModel):
    valid: bool
    code: str
    discount_percent: float
    label: str
    message: str

class CouponCreateAdmin(BaseModel):
    code: str
    discount_percent: float = Field(..., ge=0, le=100)
    label: str
    is_active: bool = True
    usage_limit: Optional[int] = None

class CouponAdminResponse(BaseModel):
    id: int
    code: str
    discount_percent: float
    label: str
    is_active: bool
    usage_limit: Optional[int]
    usage_count: int

    class Config:
        from_attributes = True

# ============ RAZORPAY PAYMENT SCHEMAS ============

class CreatePaymentRequest(BaseModel):
    """Payload sent by the frontend to initiate a Razorpay-backed payment."""
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    items: List[OrderItemCreate]
    coupon_code: Optional[str] = None
    shipping_address: Optional[str] = None

class CreatePaymentResponse(BaseModel):
    """Returned to the frontend to open the Razorpay popup."""
    razorpay_order_id: str       # e.g. "order_XXXXXXXXXXXXXXXX"
    amount: int                  # total in paisa (₹ × 100)
    currency: str = "INR"
    freakfits_order_code: str    # our internal FF-XXXXXXXX code
    key_id: str                  # RAZORPAY_KEY_ID (public, safe to expose)
    order_token: str             # Signed secure order token payload
    key: Optional[str] = None    # Fallback to key
    order_id: Optional[str] = None # Fallback to order_id

class VerifyPaymentRequest(BaseModel):
    """Razorpay callback data sent back to confirm a payment succeeded."""
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    freakfits_order_code: str    # ties back to our DB row
    order_token: str             # Signed secure order token payload from frontend


# ============ CONTACT SCHEMAS ============

class ContactMessageResponse(BaseModel):
    id: int
    name: str
    email: str
    reason: str
    message: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ============ FORGOT PASSWORD SCHEMAS ============

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str


# ============ ACCESS REQUEST SCHEMAS ============

class AdminAccessRequestInput(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr

class AdminAccessVerifyInput(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=4, max_length=6)
    name: str = Field(..., min_length=2)

class AdminAccessApprovalInput(BaseModel):
    role: str = Field(..., pattern="^(manager|viewer)$")
    password: str = Field(..., min_length=6)

class AdminChangePasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_new_password: str


# ============ ADDRESS SCHEMAS ============

class AddressCreate(BaseModel):
    address_type: str = Field("Home", min_length=1, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=10, max_length=20)
    street_address: str = Field(..., min_length=5)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=5, max_length=20)
    country: str = Field("India", min_length=2, max_length=100)

class AddressResponse(BaseModel):
    id: int
    user_id: int
    address_type: str
    full_name: str
    phone: str
    street_address: str
    city: str
    state: str
    postal_code: str
    country: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

# ============ WISHLIST SCHEMAS ============

class WishlistCreate(BaseModel):
    product_id: int

class WishlistResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    created_at: datetime.datetime
    product: ProductResponse

    class Config:
        from_attributes = True

# ============ NEWSLETTER SCHEMAS ============

class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr

class NewsletterResponse(BaseModel):
    message: str


# ============ CART SCHEMAS ============

class CartItemBase(BaseModel):
    product_id: int
    size: str
    quantity: int = 1
    custom_name: Optional[str] = None
    custom_number: Optional[str] = None

class CartItemCreate(CartItemBase):
    pass

class CartItemUpdate(BaseModel):
    quantity: Optional[int] = None
    custom_name: Optional[str] = None
    custom_number: Optional[str] = None

class CartItemResponse(CartItemBase):
    id: int
    user_id: int
    
    class Config:
        from_attributes = True

# ============ ADMIN EXTRA SCHEMAS ============

class AdminProfileUpdateInput(BaseModel):
    full_name: str

# ============ API DOCS SCHEMAS ============

class ApiDocsMasterUpdate(BaseModel):
    username: str
    password: str

class ApiDocsAccessCreate(BaseModel):
    email: EmailStr
    password: str

class ApiDocsAccessResponse(BaseModel):
    id: int
    email: EmailStr
    bound_ip: Optional[str] = None
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True