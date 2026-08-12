"""Structured conflict-detection pipeline (Trust Layer Phase 1):
signal extraction, candidate selection, deterministic classification, LLM
classification, and full pipeline orchestration."""

from __future__ import annotations

import json

from app.conflict_detection import Relationship, detect_conflicts_structured
from app.conflict_detection.candidates import select_candidates
from app.conflict_detection.claims import extract_claims
from app.conflict_detection.deterministic import try_classify
from app.conflict_detection.llm_stage import classify_candidates
from app.conflict_detection.signals import (
    extract_dates,
    extract_entities,
    extract_numbers,
    topic_similarity,
)
from app.conflict_detection.types import Claim, ConflictCandidate
from app.llm import TokenUsage
from app.retrieval import RetrievedChunk


def _claim(cid: str, doc: str, text: str, **kwargs) -> Claim:
    return Claim(
        chunk_id=cid,
        document_id=doc,
        version_id="v1",
        text=text,
        numbers=extract_numbers(text),
        dates=extract_dates(text),
        entities=extract_entities(text),
        **kwargs,
    )


def _chunk(cid: str, doc: str, text: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_id=doc, version_id="v1", text=text, page_num=1, section=None, score=1.0
    )


# --- signals ---


def test_extract_numbers():
    assert extract_numbers("PTO accrues at 1.5 days per month, capped at 18 days.") == [1.5, 18.0]


def test_extract_dates_years_and_month_day():
    assert "2024" in extract_dates("Effective in 2024.")
    assert any("March" in d for d in extract_dates("Effective March 3, 2025."))


def test_extract_entities_filters_stopwords_and_short_words():
    entities = extract_entities("PTO accrues with the policy over time")
    assert "accrues" in entities
    assert "policy" in entities
    assert "with" not in entities  # stopword
    assert "the" not in entities  # too short


def test_topic_similarity_jaccard():
    assert topic_similarity({"pto", "accrual"}, {"pto", "accrual"}) == 1.0
    assert topic_similarity({"pto"}, {"billing"}) == 0.0
    assert topic_similarity(set(), {"pto"}) == 0.0


# --- candidates ---


def test_select_candidates_excludes_same_document():
    claims = [_claim("c1", "doc-a", "PTO is 20 days"), _claim("c2", "doc-a", "PTO is 25 days")]
    assert select_candidates(claims) == []


def test_select_candidates_filters_below_similarity_threshold(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "conflict_candidate_min_similarity", 0.9)
    claims = [_claim("c1", "doc-a", "PTO accrues monthly"), _claim("c2", "doc-b", "Billing is quarterly")]
    assert select_candidates(claims) == []


def test_select_candidates_caps_to_max_pairs(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "conflict_candidate_min_similarity", 0.0)
    monkeypatch.setattr(settings, "conflict_max_candidate_pairs", 2)
    claims = [
        _claim("a", "doc-a", "PTO policy applies to employees"),
        _claim("b", "doc-b", "PTO policy applies to contractors"),
        _claim("c", "doc-c", "PTO policy applies to interns"),
        _claim("d", "doc-d", "PTO policy applies to managers"),
    ]
    candidates = select_candidates(claims)
    assert len(candidates) == 2


# --- deterministic ---


def test_deterministic_numeric_contradiction():
    a = _claim("c1", "doc-a", "Employees receive 20 days of annual leave.")
    b = _claim("c2", "doc-b", "Employees receive 25 days of annual leave.")
    result = try_classify(ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5))
    assert result is not None
    assert result.relationship == Relationship.CONTRADICTS
    assert result.method == "deterministic"
    assert 0.0 < result.confidence <= 1.0


def test_deterministic_numeric_agreement():
    a = _claim("c1", "doc-a", "Employees receive 20 days of annual leave.")
    b = _claim("c2", "doc-b", "Employees receive 20 days of annual leave.")
    result = try_classify(ConflictCandidate(claim_a=a, claim_b=b, similarity=0.9))
    assert result is not None
    assert result.relationship == Relationship.SUPPORTS


def test_deterministic_date_contradiction():
    a = _claim("c1", "doc-a", "The policy was introduced in 2023.")
    b = _claim("c2", "doc-b", "The policy was introduced in 2025.")
    result = try_classify(ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5))
    assert result is not None
    assert result.relationship == Relationship.CONTRADICTS


def test_deterministic_returns_none_for_ambiguous_text_only_claims():
    a = _claim("c1", "doc-a", "Employees submit leave requests through HR.")
    b = _claim("c2", "doc-b", "Managers approve leave requests.")
    assert try_classify(ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)) is None


def test_deterministic_returns_none_for_partial_number_overlap():
    a = _claim("c1", "doc-a", "Section 5 allows 20 days.")
    b = _claim("c2", "doc-b", "Section 5 allows 20 days, extendable to 25.")
    # a_nums={5,20}, b_nums={5,20,25}: overlapping, not disjoint -> ambiguous.
    assert try_classify(ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)) is None


# --- llm_stage ---


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None


class _FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        return _FakeCompletion(self._content)


def test_classify_candidates_empty_list_skips_llm(monkeypatch):
    def _boom():
        raise AssertionError("should not call the LLM with no candidates")

    monkeypatch.setattr("app.llm._client", _boom)
    results, usage = classify_candidates([])
    assert results == []
    assert usage == TokenUsage()


def test_classify_candidates_parses_relationship_and_confidence(monkeypatch):
    content = json.dumps(
        {
            "results": [
                {
                    "index": 0,
                    "topic": "Leave requests",
                    "relationship": "complements",
                    "confidence": 1.5,  # out-of-range, must be clamped to 1.0
                    "explanation": "Different steps of the same process.",
                }
            ]
        }
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    a = _claim("c1", "doc-a", "Employees submit leave requests through HR.")
    b = _claim("c2", "doc-b", "Managers approve leave requests.")
    results, _usage = classify_candidates([ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)])
    assert len(results) == 1
    assert results[0].relationship == Relationship.COMPLEMENTS
    assert results[0].confidence == 1.0
    assert results[0].method == "llm"


def test_classify_candidates_unknown_relationship_becomes_uncertain(monkeypatch):
    content = json.dumps(
        {"results": [{"index": 0, "relationship": "MAYBE", "confidence": 0.5, "explanation": "?"}]}
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    a = _claim("c1", "doc-a", "x")
    b = _claim("c2", "doc-b", "y")
    results, _usage = classify_candidates([ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)])
    assert results[0].relationship == Relationship.UNCERTAIN


def test_classify_candidates_llm_failure_degrades_to_uncertain(monkeypatch):
    def _raise():
        raise RuntimeError("LLM unreachable")

    monkeypatch.setattr("app.llm._client", _raise)
    a = _claim("c1", "doc-a", "x")
    b = _claim("c2", "doc-b", "y")
    results, usage = classify_candidates([ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)])
    assert len(results) == 1
    assert results[0].relationship == Relationship.UNCERTAIN
    assert usage == TokenUsage()


def test_classify_candidates_missing_pair_in_response_becomes_uncertain(monkeypatch):
    content = json.dumps({"results": []})
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    a = _claim("c1", "doc-a", "x")
    b = _claim("c2", "doc-b", "y")
    results, _usage = classify_candidates([ConflictCandidate(claim_a=a, claim_b=b, similarity=0.5)])
    assert results[0].relationship == Relationship.UNCERTAIN


# --- claims (extraction) ---


def test_extract_claims_llm_failure_falls_back_to_whole_chunk():
    def _raise():
        raise RuntimeError("LLM unreachable")

    import app.llm as llm_module

    orig = llm_module._client
    llm_module._client = _raise
    try:
        chunks = [_chunk("c1", "doc-a", "PTO accrues at 1.5 days per month.")]
        claims, usage = extract_claims(chunks)
    finally:
        llm_module._client = orig
    assert len(claims) == 1
    assert claims[0].text == "PTO accrues at 1.5 days per month."
    assert usage == TokenUsage()


def test_extract_claims_parses_llm_output(monkeypatch):
    content = json.dumps(
        {"claims": [{"chunk_index": 0, "text": "PTO accrues at 1.5 days per month."}]}
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    chunks = [_chunk("c1", "doc-a", "Some longer chunk text about PTO accrual rates.")]
    claims, _usage = extract_claims(chunks)
    assert len(claims) == 1
    assert claims[0].chunk_id == "c1"
    assert claims[0].numbers == [1.5]


# --- full pipeline ---


def test_pipeline_skips_when_fewer_than_two_documents():
    def _boom():
        raise AssertionError("should not call the LLM for a single-document chunk set")

    import app.llm as llm_module

    orig = llm_module._client
    llm_module._client = _boom
    try:
        chunks = [_chunk("c1", "doc-a"), _chunk("c2", "doc-a")]
        results, usage = detect_conflicts_structured(chunks)
    finally:
        llm_module._client = orig
    assert results == []
    assert usage == TokenUsage()


def test_pipeline_resolves_obvious_numeric_case_via_deterministic_stage(monkeypatch):
    """End-to-end: claim extraction falls back to whole-chunk (LLM down),
    candidate selection finds the cross-document pair, and the deterministic
    stage resolves it without ever reaching LLM classification."""

    def _raise():
        raise RuntimeError("LLM unreachable")

    monkeypatch.setattr("app.llm._client", _raise)
    monkeypatch.setattr("app.config.settings.conflict_candidate_min_similarity", 0.0)

    chunks = [
        _chunk("c1", "doc-a", "Employees receive 20 days of annual leave."),
        _chunk("c2", "doc-b", "Employees receive 25 days of annual leave."),
    ]
    results, _usage = detect_conflicts_structured(chunks)
    assert len(results) == 1
    assert results[0].relationship == Relationship.CONTRADICTS
    assert results[0].method == "deterministic"


def test_pipeline_persists_workspace_scoped_rows(client, make_user, ingest_inline, monkeypatch):
    """The pipeline's persistence step never crosses a workspace boundary —
    every row it writes carries the caller's own workspace_id."""
    import uuid

    from app.conflict_detection import persistence
    from app.conflict_detection.types import Relationship as Rel
    from app.conflict_detection.types import StructuredConflict
    from app.db import SessionLocal
    from app.models import ConflictRecord

    user = make_user()
    db = SessionLocal()
    try:
        sc = StructuredConflict(
            topic="Test",
            document_id_a=str(uuid.uuid4()),
            document_version_a=None,
            chunk_id_a=str(uuid.uuid4()),
            claim_a="20 days",
            document_id_b=str(uuid.uuid4()),
            document_version_b=None,
            chunk_id_b=str(uuid.uuid4()),
            claim_b="25 days",
            relationship=Rel.CONTRADICTS,
            confidence=0.9,
            explanation="differ",
            method="deterministic",
        )
        persistence.persist(db, workspace_id=user.workspace_id, conflicts=[sc])
        db.commit()
        rows = db.query(ConflictRecord).filter_by(workspace_id=user.workspace_id).all()
        assert len(rows) == 1
        assert rows[0].relationship == "CONTRADICTS"
        assert rows[0].confidence == 0.9
    finally:
        db.close()
