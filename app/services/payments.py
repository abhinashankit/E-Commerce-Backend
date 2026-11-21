"""Razorpay integration: order creation + HMAC signature verification."""
import hashlib
import hmac
import logging

import razorpay

from app.config import settings
from app.errors import PaymentGatewayError
from app.models import Order

log = logging.getLogger(__name__)
_client: razorpay.Client | None = None


def _get_client() -> razorpay.Client:
    global _client
    if _client is None:
        _client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        _client.set_app_details({"title": "ecommerce-backend", "version": "1.0"})
    return _client


def to_paise(order: Order) -> int:
    return int((order.total_amount * 100).to_integral_value())


def create_razorpay_order(order: Order) -> str:
    try:
        rzp_order = _get_client().order.create(
            {
                "amount": to_paise(order),
                "currency": order.currency,
                "receipt": f"order_{order.id}",
                "notes": {"order_id": str(order.id), "user_id": str(order.user_id)},
            }
        )
        return rzp_order["id"]
    except Exception as exc:  # network / auth / gateway errors
        log.exception("Razorpay order creation failed for order %s", order.id)
        raise PaymentGatewayError("Payment gateway unavailable, please retry") from exc


def _hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_checkout_signature(razorpay_order_id: str, razorpay_payment_id: str, signature: str) -> bool:
    """Signature returned to the browser by Razorpay Checkout: HMAC(order_id|payment_id)."""
    expected = _hmac_sha256_hex(
        settings.RAZORPAY_KEY_SECRET, f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    )
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Webhook signature: HMAC of the *raw* request body using the webhook secret."""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = _hmac_sha256_hex(settings.RAZORPAY_WEBHOOK_SECRET, raw_body)
    return hmac.compare_digest(expected, signature or "")
