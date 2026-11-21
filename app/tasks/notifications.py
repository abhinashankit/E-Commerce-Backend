"""Asynchronous SMS + email so the checkout API never waits on third-party providers."""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models import Order
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

RETRY = dict(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300,
             retry_jitter=True, max_retries=5)


def _load(order_id: int) -> tuple[Order, str, str, str]:
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        user = order.user
        return order, user.email, user.phone, user.full_name


@celery_app.task(bind=True, name="app.tasks.notifications.send_order_email", **RETRY)
def send_order_email(self, order_id: int) -> None:
    order, email, _, name = _load(order_id)
    body = (f"Hi {name},\n\nThanks for your order #{order.id}. "
            f"We received your payment of {order.currency} {order.total_amount}.\n")
    if not settings.SMTP_HOST:
        log.info("[email:dry-run] to=%s subject=Order #%s confirmed", email, order.id)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.EMAIL_FROM, email, f"Order #{order.id} confirmed"
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


@celery_app.task(bind=True, name="app.tasks.notifications.send_order_sms", **RETRY)
def send_order_sms(self, order_id: int) -> None:
    order, _, phone, _ = _load(order_id)
    text = f"Order #{order.id} confirmed. Amount paid: {order.currency} {order.total_amount}. Thank you!"
    if not settings.SMS_API_URL:
        log.info("[sms:dry-run] to=%s text=%s", phone, text)
        return
    # Provider-agnostic HTTP call - adapt the payload to MSG91 / Twilio / Fast2SMS.
    resp = httpx.post(
        settings.SMS_API_URL,
        headers={"Authorization": f"Bearer {settings.SMS_API_KEY}"},
        json={"to": phone, "message": text},
        timeout=10,
    )
    resp.raise_for_status()
