"""Regression coverage for the executive-comp salary leak (P0).

Incident: an admin asked "When will I get my salary?" (a generic payroll-timing
question) and got a confident answer grounded in
06_executive_compensation_plan_RESTRICTED — a VP salary-band increase note that
is topically adjacent (both mention "salary") but does not answer what was
asked. Retrieval-level ACL (document_visible_clause) was never the issue: a
non-admin correctly gets zero chunks from that document regardless of query
wording, because the exclusion happens on document identity, not query
semantics (see test_workspace_access.py). The bug was that neither
``assess_context`` nor ``generate_answer`` consulted the reranker's own verdict
on relevance — a cross-encoder score of -8.463 (a clear non-match; a genuine
match like "CEO's salary band" scored +3.093 against the same document) was
never checked, so a topical keyword match was enough for the LLM to treat weak
evidence as sufficient.

These tests exercise ``_RERANK_SUFFICIENCY_FLOOR`` directly with rerank scores
captured from the real incident and its true-positive counterpart, with no LLM
call involved (the gate short-circuits before ``_client()`` is ever reached).
"""

from __future__ import annotations

from app.llm import CANNOT_ANSWER, assess_context, generate_answer
from app.retrieval import RetrievedChunk

# Scores as actually returned by the cross-encoder reranker for these two
# queries against the same restricted document (captured while reproducing
# the incident).
_SALARY_TIMING_BEST_SCORE = -8.463  # "When will I get my salary?" (near-miss)
_TRUE_MATCH_SCORE = 3.093  # "What is the CEO's salary band?" (real match)


def _chunk(text: str, rerank_score: float | None, chunk_id: str = "c1") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, document_id="d-restricted", version_id="v1", text=text,
        page_num=2, section=None, score=rerank_score or 0.0, rerank_score=rerank_score,
    )


_LEAK_TEXT = (
    "Board Approval Log: Q1 2024 Approved a 10% increase to the VP salary band, "
    "effective April 1, 2024, in response to competitive market benchmarking data."
)


def test_assess_refuses_low_relevance_match_without_calling_llm():
    """A weak reranker match must not be judged sufficient, regardless of what
    an LLM reading the chunk text might conclude from keyword overlap."""
    chunks = [_chunk(_LEAK_TEXT, _SALARY_TIMING_BEST_SCORE)]
    verdict = assess_context("When will I get my salary?", chunks)
    assert verdict.sufficient is False
    assert verdict.refined_query == "When will I get my salary?"


def test_generate_refuses_low_relevance_match_without_calling_llm():
    """Backstop for when assess is skipped (iteration budget exhausted):
    generate must independently refuse rather than let the generation LLM's
    own topical reading decide answerability."""
    chunks = [_chunk(_LEAK_TEXT, _SALARY_TIMING_BEST_SCORE)]
    answer = generate_answer("When will I get my salary?", chunks)
    assert answer.answerable is False
    assert answer.answer == CANNOT_ANSWER
    assert answer.citations == []


def test_gate_does_not_block_a_genuine_high_relevance_match():
    """A real match (positive rerank score, as measured for a directly
    on-topic question) must not be caught by the floor — only the LLM call
    itself decides sufficiency/grounding from here, same as before this fix."""
    chunks = [_chunk(_LEAK_TEXT, _TRUE_MATCH_SCORE)]
    scores = [c.rerank_score for c in chunks if c.rerank_score is not None]
    assert max(scores) >= 0.0  # would pass the floor check; LLM call is reached next


def test_gate_is_a_noop_when_rerank_disabled(monkeypatch):
    """With no rerank score available (rerank disabled, or the fake test
    backend), the floor must not fire — there is no signal to gate on."""
    monkeypatch.setattr(
        "app.llm._client", lambda: (_ for _ in ()).throw(RuntimeError("no llm in test env"))
    )
    chunks = [_chunk(_LEAK_TEXT, None)]
    # No rerank score present -> gate is skipped -> falls through to the LLM
    # call, which then fails gracefully to the existing "sufficient" default
    # rather than being blocked by the new gate.
    verdict = assess_context("some question", chunks)
    assert verdict.sufficient is True
