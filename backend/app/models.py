import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def get_ist_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    mobile_number = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_ist_time)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time)
    password_changed_at = Column(DateTime, nullable=True)

    orders = relationship("Order", back_populates="user")
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan")


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(150), index=True, nullable=False)
    otp_code = Column(String(10), nullable=False)
    otp_purpose = Column(String(50), nullable=False, default="register")
    is_used = Column(Boolean, default=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=get_ist_time)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="viewer")
    status = Column(String(50), default="pending")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_ist_time)
    password_changed_at = Column(DateTime, nullable=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    admin_identifier = Column(String(150), index=True, nullable=False)
    action = Column(String(100), index=True, nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=get_ist_time)


class FailedOrderRecovery(Base):
    __tablename__ = "failed_order_recovery"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    payment_id = Column(String(100), index=True, nullable=False)
    razorpay_order_id = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="INR")
    customer_identifier = Column(String(150), nullable=False)
    error_detail = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=get_ist_time)
    is_resolved = Column(Boolean, default=False)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    club = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    was_price = Column(Float, nullable=True)
    category = Column(String(50), index=True, nullable=False)
    color = Column(String(50), default="#8CFF3B")
    rating = Column(Float, default=4.8)
    reviews = Column(Integer, default=120)
    badge = Column(String(50), nullable=True)
    badge_bg = Column(String(50), nullable=True)
    material = Column(String(200), default="100% Recycled Poly-Mesh Dri-FIT")
    fit = Column(String(100), default="Athletic Tailored Match Cut")
    care = Column(Text, default="Machine wash cold inside-out, tumble dry low or hang dry. Do not iron directly on prints.")
    images = Column(JSON, nullable=False)
    stock = Column(JSON, default=lambda: {"S": 10, "M": 10, "L": 10, "XL": 5, "XXL": 5})
    size_prices = Column(JSON, nullable=True)
    size_was_prices = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_ist_time)

    reviews_list = relationship("Review", back_populates="product", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_code = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    customer_name = Column(String(120), nullable=False)
    customer_email = Column(String(150), nullable=False)
    customer_phone = Column(String(20), nullable=True)
    
    subtotal = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    shipping_fee = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
    coupon_code = Column(String(50), nullable=True)
    
    payment_method = Column(String(50), nullable=False) # 'credit', 'debit', 'upi', 'netbanking', 'cod', 'razorpay'
    payment_status = Column(String(50), default="COMPLETED") # PENDING, COMPLETED, PAID, FAILED
    order_status = Column(String(50), default="Pending") # 'Pending', 'Confirmed', 'Shipped', 'Delivered'
    razorpay_order_id = Column(String(100), index=True, nullable=True)  # Razorpay order ID for payment tracking
    razorpay_payment_id = Column(String(100), index=True, nullable=True) # Razorpay payment ID for idempotency checks
    shipping_address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_time)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(150), nullable=False)
    club = Column(String(100), nullable=True)
    size = Column(String(10), nullable=False)
    custom_name = Column(String(50), nullable=True)
    custom_number = Column(String(10), nullable=True)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    discount_percent = Column(Float, nullable=False)
    label = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, nullable=True)  # Global maximum number of times this coupon can be used
    usage_count = Column(Integer, default=0)      # How many times it has been used so far


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    email = Column(String(150), index=True, nullable=False)
    reason = Column(String(100), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_time)


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    return_code = Column(String(50), unique=True, index=True, nullable=False)
    order_code = Column(String(50), index=True, nullable=False)
    customer_name = Column(String(120), nullable=False)
    customer_email = Column(String(150), index=True, nullable=False)
    return_type = Column(String(50), nullable=False)  # 'damaged_company' or 'size_exchange'
    current_size = Column(String(10), nullable=True)
    requested_size = Column(String(10), nullable=True)
    video_proof = Column(String(255), nullable=False)  # unboxing video proof filename or link
    reason_details = Column(Text, nullable=True)
    terms_accepted = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="PENDING_REVIEW")  # PENDING_REVIEW, APPROVED, REFUNDED, REJECTED
    created_at = Column(DateTime, default=get_ist_time)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(120), nullable=False)
    rating = Column(Integer, nullable=False)  # 1 to 5
    comment = Column(Text, nullable=True)
    image_url = Column(String(255), nullable=True)  # user fit photo with product
    created_at = Column(DateTime, default=get_ist_time)

    product = relationship("Product", back_populates="reviews_list")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    address_type = Column(String(50), default="Home")
    full_name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False)
    street_address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=False)
    country = Column(String(100), default="India")
    created_at = Column(DateTime, default=get_ist_time)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time)


    user = relationship("User", back_populates="addresses")

class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_ist_time)

    user = relationship("User", backref="wishlist_items")
    product = relationship("Product")

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=get_ist_time)


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    size = Column(String(10), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    custom_name = Column(String(50), nullable=True)
    custom_number = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=get_ist_time)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time)

    user = relationship("User", backref="cart_items")
    product = relationship("Product")

class ApiDocsMaster(Base):
    __tablename__ = "api_docs_master"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, default="admin")
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=get_ist_time)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time)

class ApiDocsAccess(Base):
    __tablename__ = "api_docs_access"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    bound_ip = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_ist_time)
