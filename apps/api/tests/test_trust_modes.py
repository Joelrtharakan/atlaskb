"""Trust modes (Trust Layer Phase 4): FAST/BALANCED/MAX_TRUST."""

from __future__ import annotations

import io

from app.config import settings

PTO_HR = "# PTO Policy\n\nPTO accrues at 1.5 days per month, capped at 18 days per year.\n"
PTO_ENG = "# Engineering Time Off\n\nEngineering is unlimited PTO with no accrual cap.\n"


def _upload(client, headers, text: str, filename: str):
    return client.post(
        "/documents", headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def test_default_trust_mode_is_balanced(client, auth_headers, ingest_inline, stub_llm):
    _upload(client, auth_headers, PTO_HR, "hr.md")
    r = client.post("/chat", headers=auth_headers, json={"question": "What is PTO?"})
    assert r.status_code == 200
    assert r.json()["trust_mode"] == "BALANCED"


def test_fast_mode_skips_conflict_detection_entirely(client, auth_headers, ingest_inline, stub_llm, monkeypatch):
    calls = {"n": 0}

    def fake_detect_conflicts_structured(chunks, **kwargs):
        calls["n"] += 1
        from app.llm import TokenUsage

        return [], TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO?", "trust_mode": "FAST"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["trust_mode"] == "FAST"
    assert body["conflicts"] == []
    assert calls["n"] == 0


def test_balanced_mode_still_runs_conflict_detection(client, auth_headers, ingest_inline, stub_llm, monkeypatch):
    calls = {"n": 0}

    def fake_detect_conflicts_structured(chunks, **kwargs):
        calls["n"] += 1
        from app.llm import TokenUsage

        return [], TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r = client.post("/chat", headers=auth_headers, json={"question": "How much PTO?"})
    assert r.status_code == 200
    assert calls["n"] == 1


def test_max_trust_widens_candidate_params(client, auth_headers, ingest_inline, stub_llm, monkeypatch):
    captured = {}

    def fake_detect_conflicts_structured(chunks, **kwargs):
        captured.update(kwargs)
        from app.llm import TokenUsage

        return [], TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO?", "trust_mode": "MAX_TRUST"}
    )
    assert r.status_code == 200
    assert captured == {
        "candidate_min_similarity": settings.max_trust_candidate_min_similarity,
        "candidate_max_pairs": settings.max_trust_max_candidate_pairs,
    }


def test_balanced_mode_does_not_override_candidate_params(
    client, auth_headers, ingest_inline, stub_llm, monkeypatch
):
    captured = {"called_with_kwargs": None}

    def fake_detect_conflicts_structured(chunks, **kwargs):
        captured["called_with_kwargs"] = kwargs
        from app.llm import TokenUsage

        return [], TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r = client.post("/chat", headers=auth_headers, json={"question": "How much PTO?"})
    assert r.status_code == 200
    assert captured["called_with_kwargs"] == {}


def test_max_trust_builds_evidence_for_all_retrieved_not_just_cited(
    client, auth_headers, ingest_inline, stub_llm
):
    """stub_llm's fake_generate only cites chunks[0] — BALANCED should give
    exactly 1 evidence entry, MAX_TRUST should give evidence for every
    retrieved chunk (both documents), each flagged whether it was cited."""
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r_balanced = client.post("/chat", headers=auth_headers, json={"question": "How much PTO?"})
    r_max = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO now?", "trust_mode": "MAX_TRUST"}
    )
    assert r_balanced.status_code == 200
    assert r_max.status_code == 200
    balanced_evidence = r_balanced.json()["evidence"]
    max_evidence = r_max.json()["evidence"]
    assert len(balanced_evidence) == 1
    assert all(e["is_cited"] for e in balanced_evidence)
    assert len(max_evidence) >= 2
    assert any(not e["is_cited"] for e in max_evidence)


def test_cache_does_not_leak_between_trust_modes(client, auth_headers, ingest_inline, stub_llm, monkeypatch):
    """FAST and BALANCED must never share a cached answer, since they do
    genuinely different work (conflict detection on/off)."""
    monkeypatch.setattr(settings, "cache_enabled", True)
    _upload(client, auth_headers, PTO_HR, "hr.md")
    _upload(client, auth_headers, PTO_ENG, "eng.md")

    r_fast = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO total?", "trust_mode": "FAST"}
    )
    r_balanced = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO total?", "trust_mode": "BALANCED"}
    )
    assert r_fast.json()["cached"] is False
    assert r_balanced.json()["cached"] is False  # not served from FAST's cache entry

    r_fast_again = client.post(
        "/chat", headers=auth_headers, json={"question": "How much PTO total?", "trust_mode": "FAST"}
    )
    assert r_fast_again.json()["cached"] is True
    assert r_fast_again.json()["trust_mode"] == "FAST"
