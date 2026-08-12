"""LangGraph agent behavior — deterministic, with the LLM steps mocked."""

from __future__ import annotations

from app.agent import run_agent
from app.llm import Assessment, GroundedAnswer
from app.retrieval import RetrievedChunk


def _chunk(cid: str, text: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_id="d", version_id="v1", text=text, page_num=1, section=None, score=1.0
    )


def _generate(question, chunks):
    if not chunks:
        return GroundedAnswer(False, "cannot", [])
    return GroundedAnswer(True, "answer", [{"claim": "c", "chunk_ids": [chunks[0].chunk_id]}])


def test_single_pass_when_context_sufficient():
    calls = {"retrieve": 0, "assess": 0}

    def retrieve(q):
        calls["retrieve"] += 1
        return [_chunk("c1")]

    def assess(question, chunks):
        calls["assess"] += 1
        return Assessment(sufficient=True)

    res = run_agent("q", retrieve, assess_fn=assess, generate_fn=_generate, max_iterations=3)
    assert calls["retrieve"] == 1
    assert res.iterations == 1
    assert res.answer.answerable is True
    assert res.queries == ["q"]


def test_requeries_when_insufficient_then_answers():
    state = {"assess": 0}

    def retrieve(q):
        return [_chunk(f"c-{q}")]

    def assess(question, chunks):
        state["assess"] += 1
        # Insufficient on the first look, sufficient after the re-query.
        if state["assess"] == 1:
            return Assessment(sufficient=False, refined_query="sharper query")
        return Assessment(sufficient=True)

    res = run_agent("original", retrieve, assess_fn=assess, generate_fn=_generate, max_iterations=3)
    assert res.queries == ["original", "sharper query"]
    assert res.iterations == 2
    assert len(res.chunks) == 2  # accumulated across both retrievals


def test_iterations_are_bounded():
    calls = {"retrieve": 0}

    def retrieve(q):
        calls["retrieve"] += 1
        return [_chunk(f"c{calls['retrieve']}")]

    def assess(question, chunks):
        # Never satisfied — the bound must stop the loop.
        return Assessment(sufficient=False, refined_query="again")

    res = run_agent("q", retrieve, assess_fn=assess, generate_fn=_generate, max_iterations=2)
    assert calls["retrieve"] == 2
    assert res.iterations == 2


def test_dedupes_repeated_chunks_across_iterations():
    def retrieve(q):
        return [_chunk("same"), _chunk("same")]  # duplicates within and across calls

    def assess(question, chunks):
        return Assessment(sufficient=False, refined_query="more")

    res = run_agent("q", retrieve, assess_fn=assess, generate_fn=_generate, max_iterations=3)
    assert [c.chunk_id for c in res.chunks] == ["same"]


def test_no_chunks_yields_cannot_answer():
    res = run_agent(
        "q", lambda q: [], assess_fn=lambda a, b: Assessment(True), generate_fn=_generate,
        max_iterations=2,
    )
    assert res.answer.answerable is False


def test_condense_rewrites_first_query_from_history():
    """A follow-up is condensed into a standalone query before retrieval so the
    right chunks are fetched even when the raw follow-up has no topical keywords."""
    seen = {}

    def retrieve(q):
        seen["query"] = q
        return [_chunk("c1")]

    from app.llm import TokenUsage

    def condense(_q):  # pretend history resolved "has that changed?" -> PTO
        return "PTO policy recent change", TokenUsage(prompt=5, completion=5, total=10)

    res = run_agent(
        "has that changed recently?",
        retrieve,
        assess_fn=lambda a, b: Assessment(True),
        generate_fn=_generate,
        condense_fn=condense,
        max_iterations=3,
    )
    # Retrieval ran on the rewritten query, and the raw follow-up was recorded.
    assert seen["query"] == "PTO policy recent change"
    assert res.queries == ["PTO policy recent change"]
    assert res.usage.total == 10
    assert res.answer.answerable is True
