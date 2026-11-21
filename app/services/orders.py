import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import InsufficientStock, NotFound
from app.models import Order, OrderItem, OrderStatus, Payment, User
from app.schemas import OrderItemIn
from app.services import inventory, payments
from app.tasks.notifications import send_order_email, send_order_sms

log = logging.getLogger(__name__)


def create_order(db: Session, user: User, items_in: list[OrderItemIn]) -> Order:
    """Reserve stock + create a PENDING order atomically, then create the Razorpay order."""
    merged: dict[int, int] = defaultdict(int)
    for it in items_in:
        merged[it.product_id] += it.quantity

    try:
        products = inventory.reserve_stock(db, merged)
        order = Order(
            user_id=user.id,
            status=OrderStatus.PENDING,
            total_amount=sum(products[pid].price * qty for pid, qty in merged.items()),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.ORDER_EXPIRY_MINUTES),
            items=[
                OrderItem(product_id=pid, quantity=qty, unit_price=products[pid].price)
                for pid, qty in merged.items()
            ],
        )
        db.add(order)
        db.commit()  # stock decrement + order row become visible together; row locks released
    except Exception:
        db.rollback()
        raise

    # External call happens OUTSIDE the DB transaction so we never hold row locks while waiting on the network.
    try:
        order.razorpay_order_id = payments.create_razorpay_order(order)
        db.commit()
    except Exception:
        release_order(db, order.id, OrderStatus.FAILED)
        raise
    return order


def release_order(db: Session, order_id: int, new_status: str) -> bool:
    """Give reserved stock back. Idempotent: only acts on PENDING orders (row-locked)."""
    order = db.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if order is None or order.status != OrderStatus.PENDING:
        db.rollback()
        return False
    inventory.restock(db, {i.product_id: i.quantity for i in order.items})
    order.status = new_status
    db.commit()
    return True


def mark_order_paid(
    db: Session,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    amount_paise: int | None,
    source: str,
) -> Order | None:
    """Idempotent PENDING -> PAID transition. Safe to call from both /verify and the webhook,
    in any order and any number of times (the order row is locked for the duration)."""
    order = db.execute(
        select(Order).where(Order.razorpay_order_id == razorpay_order_id).with_for_update()
    ).scalar_one_or_none()
    if order is None:
        db.rollback()
        return None

    if amount_paise is not None and amount_paise != payments.to_paise(order):
        log.error("Amount mismatch on order %s: got %s expected %s", order.id, amount_paise, payments.to_paise(order))
        db.rollback()
        return order

    newly_paid = False
    if order.status == OrderStatus.PENDING:
        order.status = OrderStatus.PAID
        newly_paid = True
    elif order.status in (OrderStatus.EXPIRED, OrderStatus.FAILED):
        # Customer paid after we released the stock. Try to re-reserve; otherwise flag for refund.
        try:
            inventory.reserve_stock(db, {i.product_id: i.quantity for i in order.items})
            order.status = OrderStatus.PAID
            newly_paid = True
        except (InsufficientStock, NotFound):
            order.status = OrderStatus.REFUND_REQUIRED
            log.warning("Order %s paid after expiry and stock unavailable -> REFUND_REQUIRED", order.id)

    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()
    if payment is None:
        db.add(Payment(order_id=order.id, razorpay_payment_id=razorpay_payment_id,
                       status="captured", amount_paise=amount_paise, source=source))
    else:
        payment.status = "captured"
    db.commit()

    if newly_paid:
        _enqueue_notifications(order.id)
    return order


def record_failed_payment(db: Session, razorpay_order_id: str, razorpay_payment_id: str,
                          amount_paise: int | None) -> None:
    """A failed attempt does NOT cancel the order: Razorpay lets the customer retry on the same order.
    Stock is released by the expiry job if no attempt succeeds in time."""
    order = db.execute(select(Order).where(Order.razorpay_order_id == razorpay_order_id)).scalar_one_or_none()
    if order is None:
        return
    exists = db.execute(
        select(Payment.id).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).first()
    if not exists:
        db.add(Payment(order_id=order.id, razorpay_payment_id=razorpay_payment_id,
                       status="failed", amount_paise=amount_paise, source="webhook"))
        db.commit()


def expire_stale_orders(db: Session, batch: int = 200) -> int:
    """Release stock held by PENDING orders that were never paid. Run periodically by Celery beat."""
    now = datetime.now(timezone.utc)
    ids = db.execute(
        select(Order.id)
        .where(Order.status == OrderStatus.PENDING, Order.expires_at < now)
        .order_by(Order.expires_at)
        .limit(batch)
    ).scalars().all()
    return sum(1 for oid in ids if release_order(db, oid, OrderStatus.EXPIRED))


def _enqueue_notifications(order_id: int) -> None:
    """Fire-and-forget: a broker outage must never fail the payment response."""
    try:
        send_order_email.delay(order_id)
        send_order_sms.delay(order_id)
    except Exception:
        log.exception("Could not enqueue notifications for order %s", order_id)
