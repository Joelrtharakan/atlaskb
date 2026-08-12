"""Explainable Trust Summary (Trust Layer Phase 5)."""

from __future__ import annotations

import io

from app.schemas import Citation, Conflict, Evidence
from app.trust_summary import build_trust_summary, citation_coverage


def _evidence(**kwargs) -> Evidence:
    defaults = {
        "chunk_id": "c1", "document_id": "d1", "filename": "f.md", "staleness": 0.0,
        "is_current_version": True, "dense_score": 0.7, "sparse_score": None, "rerank_score": None,
    }
    defaults.update(kwargs)
    return Evidence(**defaults)


# --- citation_coverage (reused algorithm) ---


def test_citation_coverage_full_match():
    citations = [Citation(claim="The sky is blue.", chunk_ids=["c1"])]
    assert citation_coverage("The sky is blue.", citations) == 1.0


def test_citation_coverage_no_citations():
    citations: list[Citation] = []
    assert citation_coverage("The sky is blue.", citations) == 0.0


def test_citation_coverage_no_sentences_returns_none():
    assert citation_coverage("", []) is None


def test_citation_coverage_partial():
    citations = [Citation(claim="The sky is blue.", chunk_ids=["c1"])]
    answer = "The sky is blue. Grass is green."
    coverage = citation_coverage(answer, citations)
    assert coverage == 0.5


# --- build_trust_summary ---


def test_unanswerable_returns_none():
    assert build_trust_summary(
        answerable=False, answer="I cannot answer.", citations=[], evidence=[], conflicts=[]
    ) is None


def test_no_citations_or_evidence_reads_as_weak_not_falsely_high():
    summary = build_trust_summary(
        answerable=True, answer="Some claim.", citations=[], evidence=[], conflicts=[]
    )
    assert summary is not None
    assert summary.citation_coverage == 0.0
    assert summary.citation_quality == "Low"
    assert summary.source_freshness == "Unknown"
    assert summary.evidence_completeness == "Low"


def test_strong_answer_reads_high():
    citations = [Citation(claim="PTO is 20 days.", chunk_ids=["c1"])]
    evidence = [_evidence(staleness=0.0, dense_score=0.8, rerank_score=5.0)]
    summary = build_trust_summary(
        answerable=True, answer="PTO is 20 days.", citations=citations, evidence=evidence, conflicts=[]
    )
    assert summary.citation_coverage == 1.0
    assert summary.citation_quality == "High"
    assert summary.source_freshness == "High"
    assert summary.version == "Current"
    assert summary.evidence_completeness == "High"
    assert summary.permission_check == "Passed"


def test_stale_source_reads_low_freshness():
    citations = [Citation(claim="PTO is 20 days.", chunk_ids=["c1"])]
    evidence = [_evidence(staleness=0.9)]
    summary = build_trust_summary(
        answerable=True, answer="PTO is 20 days.", citations=citations, evidence=evidence, conflicts=[]
    )
    assert summary.source_freshness == "Low"


def test_historical_version_reflected():
    citations = [Citation(claim="x", chunk_ids=["c1"])]
    evidence = [_evidence(is_current_version=False)]
    summary = build_trust_summary(
        answerable=True, answer="x", citations=citations, evidence=evidence, conflicts=[]
    )
    assert summary.version == "Historical"


def test_mixed_version_reflected():
    citations = [Citation(claim="x", chunk_ids=["c1", "c2"])]
    evidence = [
        _evidence(chunk_id="c1", is_current_version=True),
        _evidence(chunk_id="c2", is_current_version=False),
    ]
    summary = build_trust_summary(
        answerable=True, answer="x", citations=citations, evidence=evidence, conflicts=[]
    )
    assert summary.version == "Mixed"


def test_evidence_with_no_scores_reads_low_completeness():
    citations = [Citation(claim="x", chunk_ids=["c1"])]
    evidence = [_evidence(dense_score=None, sparse_score=None, rerank_score=None)]
    summary = build_trust_summary(
        answerable=True, answer="x", citations=citations, evidence=evidence, conflicts=[]
    )
    assert summary.evidence_completeness == "Low"


def test_conflicts_surfaced_in_summary():
    citations = [Citation(claim="x", chunk_ids=["c1"])]
    conflicts = [
        Conflict(
            topic="PTO accrual", description="disagree", chunk_ids=["c1", "c2"],
            document_ids=["d1", "d2"], relationship="CONTRADICTS", confidence=0.9,
        )
    ]
    summary = build_trust_summary(
        answerable=True, answer="x", citations=citations, evidence=[], conflicts=conflicts
    )
    assert summary.conflicts_detected == 1
    assert "PTO accrual" in summary.conflicts_summary


def test_non_contradicts_relationship_not_counted_as_conflict():
    citations = [Citation(claim="x", chunk_ids=["c1"])]
    conflicts = [
        Conflict(
            topic="unrelated", description="not a conflict", chunk_ids=["c1", "c2"],
            document_ids=["d1", "d2"], relationship="COMPLEMENTS", confidence=0.5,
        )
    ]
    summary = build_trust_summary(
        answerable=True, answer="x", citations=citations, evidence=[], conflicts=conflicts
    )
    assert summary.conflicts_detected == 0
    assert summary.conflicts_summary == "None detected"


# --- /chat integration ---

PTO_TEXT = "# PTO Policy\n\nPTO accrues at 1.5 days per month, capped at 18 days per year.\n"


def _upload(client, headers, text: str, filename: str = "pto.md"):
    return client.post(
        "/documents", headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def test_chat_answerable_response_includes_trust_summary(client, auth_headers, ingest_inline, stub_llm):
    _upload(client, auth_headers, PTO_TEXT)
    r = client.post("/chat", headers=auth_headers, json={"question": "What is PTO?"})
    assert r.status_code == 200
    body = r.json()
    assert body["trust_summary"] is not None
    assert body["trust_summary"]["permission_check"] == "Passed"
    assert body["trust_summary"]["citation_coverage"] is not None


def test_chat_refusal_has_no_trust_summary(client, auth_headers, ingest_inline, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "What is the meaning of life?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answerable"] is False
    assert body["trust_summary"] is None


def test_chat_cache_hit_still_includes_trust_summary(client, auth_headers, ingest_inline, stub_llm, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", True)
    _upload(client, auth_headers, PTO_TEXT)
    r1 = client.post("/chat", headers=auth_headers, json={"question": "What is PTO policy exactly?"})
    assert r1.json()["cached"] is False
    r2 = client.post("/chat", headers=auth_headers, json={"question": "What is PTO policy exactly?"})
    assert r2.json()["cached"] is True
    assert r2.json()["trust_summary"] is not None
