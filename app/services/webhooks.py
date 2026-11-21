import hashlib
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import WebhookEvent
from app.services import orders

log = logging.getLogger(__name__)


def process_event(db: Session, event_id: str | None, body: bytes, event: dict) -> str:
    """Handle a verified Razorpay webhook. Handlers are idempotent, and WebhookEvent
    (primary key = event id) additionally de-duplicates Razorpay's retried deliveries."""
    event_id = event_id or hashlib.sha256(body).hexdigest()
    event_type = event.get("event", "")
    entity = event.get("payload", {}).get("payment", {}).get("entity", {})

    if event_type in ("payment.captured", "order.paid"):
        orders.mark_order_paid(
            db,
            razorpay_order_id=entity.get("order_id"),
            razorpay_payment_id=entity.get("id"),
            amount_paise=entity.get("amount"),
            source="webhook",
        )
    elif event_type == "payment.failed":
        orders.record_failed_payment(db, entity.get("order_id"), entity.get("id"), entity.get("amount"))
    else:
        log.info("Ignoring webhook event %s", event_type)

    try:
        db.add(WebhookEvent(event_id=event_id, event_type=event_type, payload=event))
        db.commit()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    return "processed"
