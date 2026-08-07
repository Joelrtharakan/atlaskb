"""Semantic cache hit/miss and tenant isolation of cached answers.

These tests enable the cache (off by default in the suite) and use the dedicated
test Redis DB, which is flushed between tests.
"""

from __future__ import annotations

import io

import pytest
from app.config import settings
from app.llm import Assessment, GroundedAnswer


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setattr(settings, "cache_enabled", True)


@pytest.fixture
def counting_llm(monkeypatch):
    """Deterministic LLM that counts how many times generation actually runs."""
    calls = {"generate": 0}

    def fake_assess(question, chunks):
        return Assessment(sufficient=True)

    def fake_generate(question, chunks):
        calls["generate"] += 1
        if not chunks:
            return GroundedAnswer(False, "cannot", [])
        return GroundedAnswer(
            True, f"answer {calls['generate']}", [{"claim": "c", "chunk_ids": [chunks[0].chunk_id]}]
        )

    monkeypatch.setattr("app.llm.assess_context", fake_assess)
    monkeypatch.setattr("app.llm.generate_answer", fake_generate)
    return calls


def _upload(client, headers, body=b"# Doc\n\nMars is the Red Planet.\n"):
    return client.post(
        "/documents", headers=headers, files={"file": ("d.md", io.BytesIO(body), "text/markdown")}
    )


def test_chat_second_identical_call_is_a_cache_hit(
    client, make_user, ingest_inline, cache_on, counting_llm
):
    user = make_user()
    _upload(client, user.headers)

    first = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert first.json()["cached"] is False
    assert counting_llm["generate"] == 1

    second = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert second.json()["cached"] is True
    # Generation did NOT run again — served from cache.
    assert counting_llm["generate"] == 1
    assert second.json()["answer"] == first.json()["answer"]


def test_cache_normalizes_query(client, make_user, ingest_inline, cache_on, counting_llm):
    user = make_user()
    _upload(client, user.headers)
    client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    # Different case/whitespace → same normalized key → cache hit.
    r = client.post("/chat", headers=user.headers, json={"question": "  what   IS  mars? "})
    assert r.json()["cached"] is True
    assert counting_llm["generate"] == 1


def test_cache_is_isolated_per_tenant(client, make_user, ingest_inline, cache_on, counting_llm):
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)
    _upload(client, bob.headers)

    a = client.post("/chat", headers=alice.headers, json={"question": "What is Mars?"})
    assert a.json()["cached"] is False
    assert counting_llm["generate"] == 1

    # Same text, different tenant → must be a miss (no cross-tenant reuse).
    b = client.post("/chat", headers=bob.headers, json={"question": "What is Mars?"})
    assert b.json()["cached"] is False
    assert counting_llm["generate"] == 2


def test_search_reports_cache_hit(client, make_user, ingest_inline, cache_on):
    user = make_user()
    _upload(client, user.headers)
    first = client.post("/search", headers=user.headers, json={"query": "Mars"})
    assert first.json()["cached"] is False
    second = client.post("/search", headers=user.headers, json={"query": "Mars"})
    assert second.json()["cached"] is True
    assert second.json()["results"] == first.json()["results"]
