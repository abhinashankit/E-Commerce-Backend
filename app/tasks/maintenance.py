import logging

from app.database import SessionLocal
from app.services.orders import expire_stale_orders as _expire
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance.expire_stale_orders")
def expire_stale_orders() -> int:
    with SessionLocal() as db:
        released = _expire(db)
    if released:
        log.info("Released stock for %s unpaid orders", released)
    return released
