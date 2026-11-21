"""Redis fixed-window rate limiter used as a FastAPI dependency."""
import logging
import time

from fastapi import HTTPException, Request

from app.config import settings
from app.redis_client import redis_client

log = logging.getLogger(__name__)


def rate_limit(limit: int | None = None, window: int | None = None, scope: str = "default"):
    def dependency(request: Request) -> None:
        max_requests = limit or settings.RATE_LIMIT_DEFAULT
        win = window or settings.RATE_LIMIT_WINDOW_SECONDS
        # Behind a proxy/load balancer, configure uvicorn --proxy-headers so client.host is the real IP.
        ip = request.client.host if request.client else "unknown"
        bucket = int(time.time()) // win
        key = f"rl:{scope}:{ip}:{bucket}"
        try:
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, win)
            count, _ = pipe.execute()
        except Exception:
            log.warning("rate limiter unavailable - failing open")
            return
        if count > max_requests:
            retry_after = win - (int(time.time()) % win)
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
