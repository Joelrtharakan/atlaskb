"""Redis fixed-window rate limiting, per user and per tenant.

Each window is a Redis counter keyed by ``scope:id:minute`` that INCRs on every
request and expires after the window. The first request in a window sets the
expiry. Exceeding either the user or the tenant limit raises HTTP 429.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, status

from app.config import settings
from app.rbac import Principal
from app.redis_client import get_redis

_WINDOW_SECONDS = 60


def _hit(scope: str, ident: str, limit: int) -> bool:
    """Increment the current window counter; return True if within ``limit``."""
    window = int(time.time()) // _WINDOW_SECONDS
    key = f"{settings.rate_limit_prefix}:{scope}:{ident}:{window}"
    try:
        redis = get_redis()
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, _WINDOW_SECONDS)
        return count <= limit
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - if Redis is down, fail open, don't block traffic
        return True


def check_rate_limit(principal: Principal) -> None:
    """Raise 429 if the principal's user or tenant window is exhausted."""
    if not settings.rate_limit_enabled:
        return
    within_user = _hit("user", principal.user_id, settings.rate_limit_user_per_min)
    within_tenant = _hit("tenant", principal.tenant_id, settings.rate_limit_tenant_per_min)
    if not (within_user and within_tenant):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded. Wait a minute before sending more requests.",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )
