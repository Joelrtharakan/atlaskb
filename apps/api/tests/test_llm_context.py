"""build_context's staleness marker (T9.3 adversarial finding: staleness was
shown in the UI evidence panel but never reached the LLM's own context, so
answers stated stale facts with unqualified confidence)."""

from app.llm import build_context
from app.retrieval import RetrievedChunk


def _chunk(staleness: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1", document_id="d1", version_id="v1", text="The cap is $500.",
        page_num=None, section="Policy", score=1.0, staleness=staleness,
    )


def test_stale_chunk_marked_in_context():
    ctx = build_context([_chunk(0.9)])
    assert "STALE" in ctx


def test_fresh_chunk_not_marked():
    ctx = build_context([_chunk(0.1)])
    assert "STALE" not in ctx


def test_default_staleness_not_marked():
    ctx = build_context(
        [
            RetrievedChunk(
                chunk_id="c1", document_id="d1", version_id="v1", text="text",
                page_num=None, section=None, score=1.0,
            )
        ]
    )
    assert "STALE" not in ctx
