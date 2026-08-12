"""LLM generation concurrency control (Trust Layer T11.1).

No real LLM calls here — ``generation_slot()``/``create_completion()`` are
exercised directly with threads and a fake completions client, and the
"/search and cached /chat are unaffected" claim is verified by manually
saturating the Redis-backed limiter and confirming those endpoints (which
never call the LLM) are untouched.
"""

from __future__ import annotations

import io
import threading
import time

import pytest
from app.llm import create_completion
from app.llm_concurrency import _active_key, active_generations, generation_slot
from app.redis_client import get_redis
from fastapi import HTTPException


@pytest.fixture
def cache_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", True)


def _occupy_slots(n: int) -> None:
    """Directly bumps the Redis counter to simulate ``n`` other in-flight
    generations, without going through generation_slot() (which would block)."""
    redis = get_redis()
    for _ in range(n):
        redis.incr(_active_key())


def _release_slots(n: int) -> None:
    redis = get_redis()
    for _ in range(n):
        redis.decr(_active_key())


def test_generation_slot_releases_after_use(monkeypatch):
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", 3)
    assert active_generations() == 0
    with generation_slot():
        assert active_generations() == 1
    assert active_generations() == 0


def test_generation_slot_rejects_with_429_when_saturated(monkeypatch):
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", 1)
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_queue_timeout_seconds", 0.2)
    _occupy_slots(1)  # simulate one other in-flight generation already at the limit
    try:
        with pytest.raises(HTTPException) as exc_info, generation_slot():
            pass  # pragma: no cover - must never be reached, limit is exhausted
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] == "0"
    finally:
        _release_slots(1)


def test_generation_slot_queues_then_succeeds_once_a_slot_frees(monkeypatch):
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", 1)
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_queue_timeout_seconds", 5.0)
    _occupy_slots(1)

    def release_after_delay():
        time.sleep(0.3)
        _release_slots(1)

    releaser = threading.Thread(target=release_after_delay)
    releaser.start()
    start = time.monotonic()
    with generation_slot():
        elapsed = time.monotonic() - start
        # Queued for roughly the hold duration, not rejected immediately and
        # not instant -- proves it actually waited for the slot to free up.
        assert elapsed >= 0.25
    releaser.join()


class _FakeCompletions:
    """Stands in for ``client.chat.completions`` -- sleeps briefly to create
    a real concurrency window threads can race inside of."""

    def __init__(self, active_counter: list[int], lock: threading.Lock, hold_seconds: float):
        self._active_counter = active_counter
        self._lock = lock
        self._hold_seconds = hold_seconds
        self.max_observed_concurrent = 0

    def create(self, **kwargs):
        with self._lock:
            self._active_counter[0] += 1
            self.max_observed_concurrent = max(self.max_observed_concurrent, self._active_counter[0])
        time.sleep(self._hold_seconds)
        with self._lock:
            self._active_counter[0] -= 1
        return "fake-completion"


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = self
        self.completions = completions


def test_create_completion_never_exceeds_configured_limit_under_real_thread_contention(monkeypatch):
    limit = 2
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", limit)
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_queue_timeout_seconds", 5.0)

    lock = threading.Lock()
    active_counter = [0]
    completions = _FakeCompletions(active_counter, lock, hold_seconds=0.15)
    client = _FakeClient(completions)

    def worker():
        create_completion(client, model="fake", messages=[])

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert completions.max_observed_concurrent <= limit
    assert active_generations() == 0  # every slot released, none leaked


def test_search_unaffected_by_saturated_generation_limit(client, make_user, monkeypatch):
    """T11.1 requirement 3: /search never calls the LLM, so it must work
    normally even while every generation slot is held."""
    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", 1)
    user = make_user()
    _occupy_slots(1)
    try:
        r = client.post("/search", headers=user.headers, json={"query": "anything", "top_k": 3})
        assert r.status_code == 200
    finally:
        _release_slots(1)


def test_cached_chat_unaffected_by_saturated_generation_limit(
    client, make_user, ingest_inline, stub_llm, cache_on, monkeypatch
):
    """T11.1 requirement 3: a cache-hit /chat response never calls the LLM
    either, so it must also work normally under a fully saturated limiter."""
    user = make_user()
    client.post(
        "/documents",
        headers=user.headers,
        files={"file": ("d.md", io.BytesIO(b"# Doc\n\nMars is the Red Planet.\n"), "text/markdown")},
    )
    question = "What is Mars?"

    # Prime the cache with stub_llm (no real LLM call either way -- this
    # confirms the *cache-hit* path specifically, not just "the LLM was
    # never configured").
    first = client.post("/chat", headers=user.headers, json={"question": question})
    assert first.status_code == 200
    assert first.json()["cached"] is False

    monkeypatch.setattr("app.llm_concurrency.settings.llm_concurrency_limit", 1)
    _occupy_slots(1)
    try:
        second = client.post("/chat", headers=user.headers, json={"question": question})
        assert second.status_code == 200
        assert second.json()["cached"] is True
    finally:
        _release_slots(1)
