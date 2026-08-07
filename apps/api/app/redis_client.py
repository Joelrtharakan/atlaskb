"""Lazy Redis accessor shared by the cache and rate limiter.

Created on first use so importing the app never requires a live Redis. Tests can
reset the singleton after pointing ``settings.redis_url`` at a test database.
"""

from __future__ import annotations

import redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def reset_redis() -> None:
    """Drop the cached client (used by tests when the URL changes)."""
    global _client
    _client = None
