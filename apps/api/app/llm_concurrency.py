"""Bounded concurrency control for LLM generation calls (Trust Layer T11.1).

Real LLM throughput is a hard ceiling set by whichever provider/hardware is
behind ``settings.llm_provider`` — local Ollama on typical hardware serves
about one generation well at a time; a hosted provider can serve many more.
Without an explicit limiter, demand beyond that ceiling doesn't degrade
gracefully: every in-flight call just piles up inside the LLM backend (or
the HTTP client) until each individually times out, so a burst produces N
simultaneous failures instead of a few slow-but-successful calls and a
clear "try again" for the rest.

This is a Redis-backed distributed semaphore, not a local
``threading.Semaphore`` — deliberately. With multiple API replicas (T11.3)
sharing ONE physical LLM backend, the real ceiling is global across every
replica, not per-replica; a local semaphore would only bound concurrency
within a single process and silently let ``replica_count * limit``
concurrent generations through, which is exactly the class of bug T11.3's
own audit is about.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status

from app.config import settings
from app.logging_config import get_logger
from app.redis_client import get_redis

log = get_logger(__name__)

_POLL_INTERVAL_SECONDS = 0.1


def _active_key() -> str:
    return f"{settings.llm_concurrency_prefix}:active"


def _try_acquire() -> bool:
    """Attempt to claim one generation slot. Best-effort: a Redis outage
    fails open (never blocks a generation just because the counter is
    unreachable) — the same convention app.ratelimit and app.cache already
    follow for their own Redis-backed state."""
    try:
        redis = get_redis()
        count = redis.incr(_active_key())
    except Exception:  # noqa: BLE001 - Redis outage must not block generation
        return True
    if count > settings.llm_concurrency_limit:
        try:
            redis.decr(_active_key())
        except Exception as exc:  # noqa: BLE001
            log.debug("llm_concurrency.decr_failed", error=str(exc))
        return False
    return True


def _release() -> None:
    try:
        get_redis().decr(_active_key())
    except Exception as exc:  # noqa: BLE001 - best-effort; must never raise from a `finally`
        log.debug("llm_concurrency.release_failed", error=str(exc))


def active_generations() -> int:
    """Current count of in-flight generation calls across every replica —
    exposed on ``/health/llm`` (see app/main.py) so this is an observable
    number, not a silent bottleneck. Returns 0 on a Redis outage rather
    than raising, since this is a diagnostic read, not a gate."""
    try:
        raw = get_redis().get(_active_key())
    except Exception:  # noqa: BLE001
        return 0
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


@contextmanager
def generation_slot() -> Iterator[None]:
    """Blocks, with a bounded wait, until a generation slot is free, then
    holds it for the duration of the ``with`` block. Raises 429 with
    ``Retry-After`` if the queue wait exceeds
    ``settings.llm_concurrency_queue_timeout_seconds`` — the same shape as
    ``app.ratelimit``'s Redis-backed rate limiting, so callers see one
    consistent "too much demand" contract across the app, not two.

    Every call site in ``app.llm`` and ``app.conflict_detection`` routes
    through this via ``app.llm.create_completion`` — never call the LLM
    client's ``chat.completions.create`` directly."""
    if not settings.llm_concurrency_enabled:
        yield
        return

    start = time.monotonic()
    acquired = _try_acquire()
    while not acquired:
        waited = time.monotonic() - start
        if waited >= settings.llm_concurrency_queue_timeout_seconds:
            log.warning(
                "llm_concurrency.rejected",
                queue_wait_ms=round(waited * 1000, 1),
                limit=settings.llm_concurrency_limit,
            )
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "The answer service is at capacity. Wait a moment and try again.",
                headers={"Retry-After": str(int(settings.llm_concurrency_queue_timeout_seconds))},
            )
        time.sleep(_POLL_INTERVAL_SECONDS)
        acquired = _try_acquire()

    wait_ms = round((time.monotonic() - start) * 1000, 1)
    if wait_ms > 0:
        log.info("llm_concurrency.queued", queue_wait_ms=wait_ms, limit=settings.llm_concurrency_limit)
    try:
        yield
    finally:
        _release()
