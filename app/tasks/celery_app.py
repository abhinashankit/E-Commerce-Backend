from celery import Celery

from app.config import settings

celery_app = Celery(
    "ecommerce",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.notifications", "app.tasks.maintenance"],
)
celery_app.conf.update(
    task_acks_late=True,                 # re-deliver if a worker dies mid-task
    worker_prefetch_multiplier=1,
    task_time_limit=60,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "expire-stale-orders-every-minute": {
            "task": "app.tasks.maintenance.expire_stale_orders",
            "schedule": 60.0,
        },
    },
)
