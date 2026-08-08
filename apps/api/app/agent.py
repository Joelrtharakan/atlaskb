"""LangGraph retrieval agent for /chat.

Flow: plan → retrieve (RBAC-scoped) → assess sufficiency → optionally re-query
(bounded) → generate a grounded, cited answer.

    START → plan → retrieve → assess ──sufficient?──▶ generate → END
                     ▲                    │ no (and budget left)
                     └────────────────────┘

The LLM-driven steps (assess, generate) and retrieval are injected callables so
tests can drive the graph deterministically with fakes. The iteration count is
hard-bounded by ``max_iterations`` so re-querying can never run away on cost.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app import llm
from app.config import settings
from app.llm import Assessment, GroundedAnswer, TokenUsage
from app.retrieval import RetrievedChunk

RetrieveFn = Callable[[str], list[RetrievedChunk]]
AssessFn = Callable[[str, list[RetrievedChunk]], Assessment]
GenerateFn = Callable[[str, list[RetrievedChunk]], GroundedAnswer]
# Rewrites the question into a standalone retrieval query (resolving follow-up
# references from conversation history); returns the query and its token usage.
CondenseFn = Callable[[str], tuple[str, TokenUsage]]


@dataclass
class AgentResult:
    answer: GroundedAnswer
    chunks: list[RetrievedChunk]
    iterations: int
    queries: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


class _State(TypedDict):
    question: str
    current_query: str
    iterations: int
    queries: list[str]
    chunks: list[RetrievedChunk]
    sufficient: bool
    refined_query: str | None
    answer: GroundedAnswer | None
    usage: TokenUsage


def _build_graph(
    retrieve_fn: RetrieveFn,
    assess_fn: AssessFn,
    generate_fn: GenerateFn,
    condense_fn: CondenseFn,
    max_iterations: int,
):
    def plan(state: _State) -> dict:
        if state["iterations"] == 0:
            # First pass: rewrite the (possibly follow-up) question into a
            # standalone retrieval query using conversation history.
            query, usage = condense_fn(state["question"])
            return {"current_query": query, "usage": state["usage"] + usage}
        query = state.get("refined_query") or state["question"]
        return {"current_query": query}

    def retrieve(state: _State) -> dict:
        found = retrieve_fn(state["current_query"])
        seen = {c.chunk_id for c in state["chunks"]}
        merged = list(state["chunks"])
        for c in found:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                merged.append(c)
        return {"chunks": merged, "queries": state["queries"] + [state["current_query"]]}

    def assess(state: _State) -> dict:
        iterations = state["iterations"] + 1
        # Out of budget → stop re-querying and answer with what we have.
        if iterations >= max_iterations:
            return {"iterations": iterations, "sufficient": True, "refined_query": None}
        verdict = assess_fn(state["question"], state["chunks"])
        return {
            "iterations": iterations,
            "sufficient": verdict.sufficient,
            "refined_query": verdict.refined_query,
            "usage": state["usage"] + verdict.usage,
        }

    def route(state: _State) -> str:
        if state["sufficient"] or not state["refined_query"]:
            return "generate"
        return "plan"

    def generate(state: _State) -> dict:
        answer = generate_fn(state["question"], state["chunks"])
        return {"answer": answer, "usage": state["usage"] + answer.usage}

    graph = StateGraph(_State)
    graph.add_node("plan", plan)
    graph.add_node("retrieve", retrieve)
    graph.add_node("assess", assess)
    graph.add_node("generate", generate)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "assess")
    graph.add_conditional_edges("assess", route, {"plan": "plan", "generate": "generate"})
    graph.add_edge("generate", END)
    return graph.compile()


def run_agent(
    question: str,
    retrieve_fn: RetrieveFn,
    *,
    assess_fn: AssessFn | None = None,
    generate_fn: GenerateFn | None = None,
    condense_fn: CondenseFn | None = None,
    max_iterations: int | None = None,
) -> AgentResult:
    """Run the retrieval agent to a grounded answer.

    ``condense_fn`` rewrites a follow-up question into a standalone retrieval
    query from conversation history; when omitted it is a no-op (the raw question
    is used), which keeps single-turn behavior unchanged.
    """
    assess_fn = assess_fn or llm.assess_context
    generate_fn = generate_fn or llm.generate_answer
    condense_fn = condense_fn or (lambda q: (q, TokenUsage()))
    max_iterations = max_iterations or settings.agent_max_iterations

    app = _build_graph(retrieve_fn, assess_fn, generate_fn, condense_fn, max_iterations)
    final: _State = app.invoke(
        {
            "question": question,
            "current_query": "",
            "iterations": 0,
            "queries": [],
            "chunks": [],
            "sufficient": False,
            "refined_query": None,
            "answer": None,
            "usage": TokenUsage(),
        }
    )
    answer = final["answer"] or GroundedAnswer(False, llm.CANNOT_ANSWER, [])
    return AgentResult(
        answer=answer,
        chunks=final["chunks"],
        iterations=final["iterations"],
        queries=final["queries"],
        usage=final["usage"],
    )
