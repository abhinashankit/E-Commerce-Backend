import hashlib
import hmac

from app.config import settings
from app.services import payments


def _sig(secret: str, msg: bytes) -> str:
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def test_checkout_signature_valid_and_invalid():
    good = _sig(settings.RAZORPAY_KEY_SECRET, b"order_1|pay_1")
    assert payments.verify_checkout_signature("order_1", "pay_1", good)
    assert not payments.verify_checkout_signature("order_1", "pay_2", good)  # tampered payment id
    assert not payments.verify_checkout_signature("order_1", "pay_1", "deadbeef")


def test_webhook_signature_uses_raw_body():
    body = b'{"event":"payment.captured"}'
    good = _sig(settings.RAZORPAY_WEBHOOK_SECRET, body)
    assert payments.verify_webhook_signature(body, good)
    assert not payments.verify_webhook_signature(body + b" ", good)  # body changed -> reject
    assert not payments.verify_webhook_signature(body, "")
