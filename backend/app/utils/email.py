import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ..config import settings

logger = logging.getLogger("uvicorn")

def send_shipping_notification(recipient_email: str, recipient_name: str, order_code: str, customer_phone: str = ""):
    """Send SMTP email informing the customer that their order has shipped."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[SMTP] Shipping mail skipped: SMTP_USER or SMTP_PASSWORD not configured in .env")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Your FreakFits Order {order_code} Has Been Shipped!"

        frontend_url = settings.FRONTEND_URL
        phone_param = f"&phone={customer_phone}" if customer_phone else ""
        
        body = f"""Hello {recipient_name},

Great news! Your FreakFits jersey order {order_code} is on the way.

You will receive a tracking ID from our delivery agency shortly.

You can track your order status live anytime using our tracking portal:
{frontend_url}/track.html?order={order_code}{phone_param}

Thank you for your support,
The FreakFits Team
"""
        msg.attach(MIMEText(body, 'plain'))

        # Standard secure TLS connection on port 587
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, recipient_email, msg.as_string())
            
        logger.info(f"[SMTP] Shipped notification sent to {recipient_email} for {order_code}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Error sending shipping notification to {recipient_email}: {e}")
        return False


def send_access_otp(recipient_email: str, otp_code: str):
    """Send SMTP email with verification OTP to candidate requesting employee access."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[SMTP] OTP mail skipped: SMTP_USER or SMTP_PASSWORD not configured in .env")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"FREAKFITS Access Code: {otp_code}"

        body = f"""Hello,

You have requested access to the FREAKFITS Control Center.

Your verification OTP code is: {otp_code}

Please enter this code in the control center request form to submit your request to the Super Admin.

Thank you,
The FreakFits Security Team
"""
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, recipient_email, msg.as_string())
            
        logger.info(f"[SMTP] Access request OTP sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Error sending access request OTP to {recipient_email}: {e}")
        return False


def send_access_approved(recipient_email: str, recipient_name: str, role: str, password: str):
    """Send SMTP email detailing role, mode of access, and password to approved candidate."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[SMTP] Approval mail skipped: SMTP_USER or SMTP_PASSWORD not configured")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = "FREAKFITS Control Center Access Approved!"

        body = f"""Hello {recipient_name},

Congratulations! Your request for accessing the FREAKFITS Control Center has been APPROVED by the Super Admin.

Here are your account credentials and access privileges:

* Control Center Portal: http://localhost:8000/admin-portal/index.html
* Login Email: {recipient_email}
* Temporary Password: {password}
* Assigned Role: {role.upper()}
* Access Privileges: {"Full Read-Only Access (View Dashboard, Orders, Products, Claims)" if role == "viewer" else "Management Access (Add/Edit Products & Manage Orders. Price edits locked)"}

Please change your password immediately inside the control panel settings.

Welcome to the team,
The FreakFits Super Admin
"""
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, recipient_email, msg.as_string())
            
        logger.info(f"[SMTP] Access approval credentials sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Error sending access approval mail to {recipient_email}: {e}")
        return False

def send_order_confirmation(recipient_email: str, recipient_name: str, order_code: str, total: float, payment_method: str, items: list, shipping_address: str):
    """Send SMTP email confirming order placement."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[SMTP] Order confirmation mail skipped: SMTP_USER or SMTP_PASSWORD not configured")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Order Confirmed: {order_code} - FreakFits"

        items_str = "\n".join([f"- {item.quantity}x {item.product_name} ({item.size}) - ₹{item.line_total:,.2f}" for item in items])
        
        frontend_url = settings.FRONTEND_URL

        body = f"""Hello {recipient_name},

Thank you for your order! Your FreakFits order {order_code} has been confirmed.

Order Summary:
{items_str}

Total: ₹{total:,.2f}
Payment Method: {payment_method}
Shipping Address: 
{shipping_address}

You can view your order status and track your shipment here:
{frontend_url}/orders.html

We will notify you again once your order has shipped.

Thank you,
The FreakFits Team
"""
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, recipient_email, msg.as_string())
            
        logger.info(f"[SMTP] Order confirmation sent to {recipient_email} for {order_code}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Error sending order confirmation mail to {recipient_email}: {e}")
        return False

def send_cancellation_email(recipient_email: str, recipient_name: str, order_code: str, total: float):
    """Send SMTP email confirming order cancellation."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[SMTP] Cancellation mail skipped: SMTP_USER or SMTP_PASSWORD not configured")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Order Cancelled: {order_code} - FreakFits"

        body = f"""Hello {recipient_name},

Your FreakFits order {order_code} has been successfully cancelled as requested.

If you had already paid for this order (Total: ₹{total:,.2f}), the refund has been initiated and will reflect in your account within 5-7 business days.

If you have any questions, please contact our support team.

Thank you,
The FreakFits Team
"""
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, recipient_email, msg.as_string())
            
        logger.info(f"[SMTP] Order cancellation sent to {recipient_email} for {order_code}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Error sending order cancellation mail to {recipient_email}: {e}")
        return False
