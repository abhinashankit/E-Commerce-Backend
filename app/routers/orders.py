from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.errors import NotFound
from app.models import Order, User
from app.rate_limit import rate_limit
from app.schemas import CheckoutOut, OrderCreate, OrderOut
from app.security import get_current_user
from app.services import orders as order_service
from app.services import payments

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(rate_limit())])


@router.post(
    "",
    response_model=CheckoutOut,
    status_code=201,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_ORDERS, scope="place-order"))],
)
def place_order(payload: OrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reserves stock, creates the order and a Razorpay order; the client then opens Razorpay Checkout."""
    order = order_service.create_order(db, user, payload.items)
    return CheckoutOut(
        order=OrderOut.model_validate(order),
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
        razorpay_order_id=order.razorpay_order_id,
        amount_paise=payments.to_paise(order),
        currency=order.currency,
    )


@router.get("", response_model=list[OrderOut])
def my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(50)
    return db.execute(stmt).scalars().all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise NotFound("Order not found")
    return order
