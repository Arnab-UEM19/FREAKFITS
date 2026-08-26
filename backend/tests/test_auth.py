from app.models import OTPVerification
from app.models import get_ist_time

def test_register_user_success(client, db):
    # Inject a verified OTP
    import datetime
    otp = OTPVerification(
        email="freshuser@example.com",
        otp_code="1234",
        otp_purpose="register",
        is_used=True,
        created_at=get_ist_time(),
        expires_at=get_ist_time() + datetime.timedelta(minutes=10)
    )
    db.add(otp)
    db.commit()
    
    from app.models import User
    users = db.query(User).all()
    print(f"USERS BEFORE POST: {[u.email for u in users]}")

    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "New User",
            "email": "freshuser@example.com",
            "mobile_number": "9876543210",
            "password": "strongpassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

def test_register_duplicate_email(client, test_user):
    # Attempt to register with an email that already exists (test_user)
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Another User",
            "email": test_user.email,
            "password": "password123"
        }
    )
    assert response.status_code == 400
    data = response.json()
    assert "An account with this email already exists" in data["detail"]

def test_login_success(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email": test_user.email,
            "password": "password123" # Must match conftest password
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_password(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email": test_user.email,
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]
