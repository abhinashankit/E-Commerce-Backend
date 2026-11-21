"""Tiny Redis JSON cache. Fails open: if Redis is down, the API just hits Postgres."""
import json
import logging
from typing import Any

from app.config import settings
from app.redis_client import redis_client

log = logging.getLogger(__name__)
VERSION_KEY = "cache:products:version"


def products_version() -> int:
    try:
        return int(redis_client.get(VERSION_KEY) or 0)
    except Exception:
        return 0


def bump_products_version() -> None:
    """Invalidate every cached product list/detail in O(1) by bumping a namespace version."""
    try:
        redis_client.incr(VERSION_KEY)
    except Exception:
        log.warning("cache invalidation failed")


def get_json(key: str) -> Any | None:
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        redis_client.set(key, json.dumps(value), ex=ttl or settings.CACHE_TTL_SECONDS)
    except Exception:
        log.warning("cache write failed")
