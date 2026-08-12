"""Structured request tracing (Trust Layer Phase 13).

Captures the real `log.info("chat.trace", ...)` calls chat.py makes (not a
mock of logging itself — monkeypatching `chat.log.info` directly, same
pattern this codebase already uses for capturing calls elsewhere) and checks
the fields the spec asked for are present, and that raw document/answer
content never leaks into the trace line.
"""

from __future__ import annotations

import io

import pytest
from app.config import settings


@pytest.fixture
def captured_logs(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_info(event, **kwargs):
        calls.append((event, kwargs))

    import app.routers.chat as chat_module

    monkeypatch.setattr(chat_module.log, "info", fake_info)
    return calls


def _upload(client, headers, body=b"# Doc\n\nMars is the Red Planet.\n", filename="d.md"):
    return client.post(
        "/documents", headers=headers, files={"file": (filename, io.BytesIO(body), "text/markdown")}
    )


def test_chat_trace_emitted_with_expected_fields(client, make_user, ingest_inline, stub_llm, captured_logs):
    user = make_user()
    _upload(client, user.headers)
    client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})

    traces = [c for c in captured_logs if c[0] == "chat.trace"]
    assert len(traces) == 1
    _, fields = traces[0]
    for key in (
        "cached", "trust_mode", "answerable", "model", "retrieval_count",
        "reranking_enabled", "conflict_detection_ran", "conflict_candidate_count",
        "stage_durations_ms",
    ):
        assert key in fields, f"missing field: {key}"
    assert fields["cached"] is False
    assert fields["trust_mode"] == "BALANCED"
    assert isinstance(fields["stage_durations_ms"], dict)


def test_chat_trace_never_includes_raw_answer_or_document_text(
    client, make_user, ingest_inline, stub_llm, captured_logs
):
    user = make_user()
    _upload(client, user.headers, body=b"# Doc\n\nSECRET-MARKER-TEXT lives here.\n")
    r = client.post("/chat", headers=user.headers, json={"question": "What is here?"})
    answer_text = r.json()["answer"]

    traces = [c for c in captured_logs if c[0] == "chat.trace"]
    _, fields = traces[0]
    serialized = str(fields)
    assert "SECRET-MARKER-TEXT" not in serialized
    assert answer_text not in serialized


def test_chat_trace_on_cache_hit_marks_cached_true(
    client, make_user, ingest_inline, stub_llm, captured_logs, monkeypatch
):
    monkeypatch.setattr(settings, "cache_enabled", True)
    user = make_user()
    _upload(client, user.headers)
    client.post("/chat", headers=user.headers, json={"question": "What is Mars really?"})
    client.post("/chat", headers=user.headers, json={"question": "What is Mars really?"})

    traces = [c for c in captured_logs if c[0] == "chat.trace"]
    assert len(traces) == 2
    assert traces[0][1]["cached"] is False
    assert traces[1][1]["cached"] is True


def test_chat_trace_reflects_trust_mode(client, make_user, ingest_inline, stub_llm, captured_logs):
    user = make_user()
    _upload(client, user.headers)
    client.post("/chat", headers=user.headers, json={"question": "What is Mars?", "trust_mode": "FAST"})

    traces = [c for c in captured_logs if c[0] == "chat.trace"]
    assert traces[0][1]["trust_mode"] == "FAST"
    assert traces[0][1]["conflict_detection_ran"] is False


def test_chat_trace_emitted_for_temporal_refusal(client, make_user, ingest_inline, stub_llm, captured_logs):
    user = make_user()
    _upload(client, user.headers)
    client.post(
        "/chat", headers=user.headers, json={"question": "What did version 99 of this document say?"}
    )
    traces = [c for c in captured_logs if c[0] == "chat.trace"]
    assert len(traces) == 1
    assert traces[0][1]["answerable"] is False
    assert "temporal_intent" in traces[0][1]
