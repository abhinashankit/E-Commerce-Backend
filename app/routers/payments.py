import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.errors import NotFound
from app.models import Order, User
from app.rate_limit import rate_limit
from app.schemas import OrderOut, PaymentVerify
from app.security import get_current_user
from app.services import orders as order_service
from app.services import payments, webhooks

log = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/verify", response_model=OrderOut, dependencies=[Depends(rate_limit(30, scope="verify"))])
def verify_payment(payload: PaymentVerify, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Called by the frontend after Razorpay Checkout succeeds. The HMAC proves the payment is genuine."""
    order = db.execute(
        select(Order).where(Order.razorpay_order_id == payload.razorpay_order_id)
    ).scalar_one_or_none()
    if order is None or order.user_id != user.id:
        raise NotFound("Order not found")
    if not payments.verify_checkout_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    ):
        raise HTTPException(400, "Invalid payment signature")
    return order_service.mark_order_paid(
        db, payload.razorpay_order_id, payload.razorpay_payment_id, amount_paise=None, source="verify"
    )


@router.post("/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request):
    """Source of truth for payment status - works even if the user closes the tab before /verify.
    No rate limit here: Razorpay must always be able to reach us."""
    body = await request.body()  # signature is computed over the RAW bytes, so don't re-serialize
    if not payments.verify_webhook_signature(body, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Malformed payload")

    event_id = request.headers.get("x-razorpay-event-id")

    def _work() -> str:
        with SessionLocal() as db:
            return webhooks.process_event(db, event_id, body, event)

    result = await run_in_threadpool(_work)
    return {"status": result}  # 2xx tells Razorpay to stop retrying
