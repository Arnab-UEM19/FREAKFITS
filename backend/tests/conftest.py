import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["ENVIRONMENT"] = "testing"
os.environ["JWT_SECRET_KEY"] = "test_secret_key"
os.environ["DB_PASSWORD"] = "test_password"
os.environ["RAZORPAY_KEY_ID"] = "test"
os.environ["RAZORPAY_KEY_SECRET"] = "test"

from app.main import app
from app.database import Base, get_db
from app.models import User, Product
from app.security import get_password_hash

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    # Create the database schema
    Base.metadata.create_all(bind=engine)
    
    db_session = TestingSessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        # Drop the database schema
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_user(db):
    user = User(
        full_name="Test User",
        email="test@example.com",
        mobile_number="1234567890",
        hashed_password=get_password_hash("password123")
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@pytest.fixture(scope="function")
def test_product(db):
    product = Product(
        id=101,
        name="Test Jersey",
        club="Test Club",
        price=99.99,
        category="Home Version",
        images=["http://example.com/image.jpg"],
        stock={"S": 10, "M": 10, "L": 10, "XL": 10, "XXL": 10}
    )
    product2 = Product(
        id=102,
        name="Test Kit",
        club="Test Club",
        price=199.99,
        category="Complete Kit",
        images=["http://example.com/image2.jpg"],
        stock={"S": 10, "M": 10, "L": 10, "XL": 10, "XXL": 10}
    )
    db.add(product)
    db.add(product2)
    db.commit()
    return product
