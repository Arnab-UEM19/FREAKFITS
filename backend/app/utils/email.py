import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import resend

from ..config import settings

logger = logging.getLogger("uvicorn")
resend.api_key = settings.RESEND_API_KEY

# Resend's sandbox recipient — anything sent here "delivers" successfully
# without reaching a real inbox. Used only when EMAIL_TEST_MODE=true, so
# you can test the whole app before you have a verified sending domain.
_TEST_RECIPIENT = "delivered@resend.dev"


def _resolve_recipient(to_email: str) -> str:
    if getattr(settings, "EMAIL_TEST_MODE", False):
        return _TEST_RECIPIENT
    return to_email


def send_email_with_retry(msg: MIMEMultipart, recipient_email: str, subject_log: str, max_retries: int = 3) -> bool:
    """
    Drop-in replacement for the old SMTP sender. Same signature, so every
    call site (send_shipping_notification, send_order_confirmation, etc.)
    needs zero changes. Extracts subject/plain/html from the MIMEMultipart
    built by the caller and sends it through Resend instead of smtplib.
    Resend's API has its own internal retry/queueing, so we don't need the
    exponential backoff loop anymore — one attempt is enough.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(f"[Email] RESEND_API_KEY not set. {subject_log} mail skipped for {recipient_email}.")
        return False

    subject = msg.get("Subject", subject_log)
    html_body = None
    text_body = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/html":
            try:
                html_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
            except Exception:
                html_body = part.get_payload()
        elif ctype == "text/plain" and text_body is None:
            try:
                text_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
            except Exception:
                text_body = part.get_payload()

    if not html_body and not text_body:
        logger.error(f"[Email] {subject_log}: no text or html payload found in message. Skipped.")
        return False

    recipient = _resolve_recipient(recipient_email)
    payload = {
        "from": settings.EMAIL_FROM,
        "to": [recipient],
        "subject": subject,
    }
    if html_body:
        payload["html"] = html_body
    else:
        payload["text"] = text_body

    try:
        resend.Emails.send(payload)
        logger.info(f"[Email] {subject_log} sent -> {recipient}" + (" (TEST MODE)" if recipient != recipient_email else ""))
        return True
    except Exception as e:
        logger.error(f"[Email] {subject_log} failed for {recipient}: {e}")
        return False


def send_shipping_notification(recipient_email: str, recipient_name: str, order_code: str, customer_phone: str = ""):
    """Notify the customer that their order has shipped."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
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
    return send_email_with_retry(msg, recipient_email, f"Shipping notification {order_code}")


def send_access_otp(recipient_email: str, otp_code: str):
    """Send verification OTP to a candidate requesting employee access."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
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

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d0e12; color: #f4f5f8; padding: 24px;">
      <div style="max-width: 500px; margin: 0 auto; background: #161820; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px; text-align: center;">
        <h1 style="color: #8CFF3B; font-size: 26px; margin-bottom: 20px; font-weight: 800;">Freak<em>Fits</em> Control Center</h1>
        <p style="color: #b4b6c4; font-size: 15px;">Your verification code:</p>
        <div style="background: rgba(140,255,59,0.08); border: 2px dashed #8CFF3B; border-radius: 12px; padding: 18px; margin: 20px 0;">
          <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #8CFF3B;">{otp_code}</span>
        </div>
        <p style="color: #8c8f9f; font-size: 13px;">Enter this code to submit your access request to the Super Admin.</p>
      </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))
    return send_email_with_retry(msg, recipient_email, "Admin Access OTP")


def send_access_approved(recipient_email: str, recipient_name: str, role: str, password: str):
    """Notify an approved candidate of their role, access, and password."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg['To'] = recipient_email
    msg['Subject'] = "FREAKFITS Control Center Access Approved!"

    body = f"""Hello {recipient_name},

Congratulations! Your request for accessing the FREAKFITS Control Center has been APPROVED by the Super Admin.

Here are your account credentials and access privileges:

* Control Center Portal: {settings.FRONTEND_URL}/admin-portal/index.html
* Login Email: {recipient_email}
* Temporary Password: {password}
* Assigned Role: {role.upper()}
* Access Privileges: {"Full Read-Only Access (View Dashboard, Orders, Products, Claims)" if role == "viewer" else "Management Access (Add/Edit Products & Manage Orders. Price edits locked)"}

Please change your password immediately inside the control panel settings.

Welcome to the team,
The FreakFits Super Admin
"""
    msg.attach(MIMEText(body, 'plain'))
    return send_email_with_retry(msg, recipient_email, "Admin Access Approval")


def send_order_confirmation(recipient_email: str, recipient_name: str, order_code: str, total: float, payment_method: str, items: list, shipping_address: str):
    """Confirm order placement to the customer."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
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
    return send_email_with_retry(msg, recipient_email, f"Order confirmation {order_code}")


def send_cancellation_email(recipient_email: str, recipient_name: str, order_code: str, total: float):
    """Confirm order cancellation to the customer."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
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
    return send_email_with_retry(msg, recipient_email, f"Order cancellation {order_code}")


def send_order_status_update(recipient_email: str, recipient_name: str, order_code: str, new_status: str, customer_phone: str = ""):
    """Notify the customer about an order status change."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg['To'] = recipient_email
    msg['Subject'] = f"Update on your FreakFits Order {order_code}"

    frontend_url = settings.FRONTEND_URL
    phone_param = f"&phone={customer_phone}" if customer_phone else ""

    status_message = ""
    if new_status.lower() == "confirmed":
        status_message = "Your order has been confirmed by our team and is now being processed."
    elif new_status.lower() == "preparing kit":
        status_message = "We are currently preparing and customizing your kit."
    elif new_status.lower() == "packing":
        status_message = "Your kit is ready and is currently being packed for dispatch."
    elif new_status.lower() == "delivered":
        status_message = "Your order has been marked as delivered. We hope you love your new kit!"
    elif new_status.lower() == "cancelled":
        status_message = "Your order has been cancelled. If you have any questions, please contact our support."
    else:
        status_message = f"The status of your order is now: {new_status}"

    body = f"""Hello {recipient_name},

{status_message}

You can track your order status here:
{frontend_url}/track-order.html?order={order_code}{phone_param}

Best regards,
The FreakFits Team
"""
    msg.attach(MIMEText(body, 'plain'))

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d0e12; color: #f4f5f8; padding: 24px;">
      <div style="max-width: 600px; margin: 0 auto; background: #161820; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px;">
        <div style="text-align: center; margin-bottom: 24px;">
          <h1 style="color: #8CFF3B; font-size: 28px; margin: 0; font-weight: 800; letter-spacing: -0.5px;">Freak<em>Fits</em></h1>
        </div>
        <div style="background: #1a1c23; border-radius: 12px; padding: 24px; border: 1px solid rgba(255,255,255,0.05);">
          <h2 style="margin-top: 0; color: #f4f5f8; font-size: 20px;">Order Update</h2>
          <p style="font-size: 15px; line-height: 1.6; color: #b4b6c4;">Hello <strong>{recipient_name}</strong>,</p>
          <p style="font-size: 15px; line-height: 1.6; color: #b4b6c4;">{status_message}</p>

          <div style="text-align: center; margin-top: 32px;">
            <a href="{frontend_url}/track-order.html?order={order_code}{phone_param}" style="display: inline-block; background-color: #8CFF3B; color: #000000; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px;">
              View Order Details
            </a>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))
    return send_email_with_retry(msg, recipient_email, f"Order Status Update ({new_status})")


def send_low_stock_alert(product_name: str, club: str, size: str, remaining_stock: int, admin_email: str):
    """Alert the admin about low stock on a product/size."""
    msg = MIMEMultipart()
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg['To'] = admin_email
    msg['Subject'] = f"Low Stock Alert: {product_name} ({size})"

    body = f"""Admin Alert: Low Stock Warning

Product: {product_name}
Club: {club}
Size: {size}
Remaining Stock: {remaining_stock}

Please restock this item soon to prevent missing out on sales.
"""
    msg.attach(MIMEText(body, 'plain'))

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d0e12; color: #f4f5f8; padding: 24px;">
      <div style="max-width: 600px; margin: 0 auto; background: #161820; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px;">
        <div style="text-align: center; margin-bottom: 24px;">
          <h1 style="color: #8CFF3B; font-size: 28px; margin: 0; font-weight: 800; letter-spacing: -0.5px;">Freak<em>Fits</em> Admin</h1>
        </div>
        <div style="background: #2a1618; border-radius: 12px; padding: 24px; border: 1px solid rgba(255,0,0,0.2);">
          <h2 style="margin-top: 0; color: #ff6b6b; font-size: 20px;">Low Stock Alert</h2>
          <p style="font-size: 15px; line-height: 1.6; color: #b4b6c4;">A product's inventory has dropped to critically low levels.</p>
          <ul style="color: #f4f5f8; line-height: 1.8;">
            <li><strong>Product:</strong> {product_name}</li>
            <li><strong>Club:</strong> {club}</li>
            <li><strong>Size:</strong> <span style="color: #ff6b6b; font-weight: bold;">{size}</span></li>
            <li><strong>Remaining:</strong> <span style="color: #ff6b6b; font-weight: bold;">{remaining_stock}</span></li>
          </ul>
        </div>
      </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))
    return send_email_with_retry(msg, admin_email, "Low Stock Alert")