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
        # Trust Layer T11.2: redis-py's ConnectionPool has no cap by default,
        # so without an explicit max_connections it grows unbounded under
        # load instead of failing predictably — the same silent-limit
        # problem this phase closes for Postgres via db_pool_size/overflow.
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
        )
    return _client


def reset_redis() -> None:
    """Drop the cached client (used by tests when the URL changes)."""
    global _client
    _client = None
