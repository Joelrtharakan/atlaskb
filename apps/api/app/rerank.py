"""Second-stage relevance reranking over the RRF-fused candidate pool.

RRF blends dense and sparse rank *positions* — it has no notion of how much
better one candidate is than another, and treats a candidate that fused to the
top by rank the same as one that's actually a strong semantic match. A
cross-encoder reads the query and a candidate's text together and scores
relevance directly, so it can correct RRF's ordering before the final top_k is
decided. See ``retrieval.hybrid_search`` for how this plugs in.
"""

from __future__ import annotations

from app.config import settings

_model = None


def _fake_score(query: str, texts: list[str]) -> list[float]:
    """Deterministic term-overlap score — for fast tests only, no model download."""
    q_terms = set(query.lower().split())
    scores: list[float] = []
    for t in texts:
        t_terms = set(t.lower().split())
        scores.append(len(q_terms & t_terms) / (len(q_terms) or 1))
    return scores


def _cross_encoder_score(query: str, texts: list[str]) -> list[float]:
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(settings.rerank_model, device=settings.rerank_device)
    pairs = [(query, t) for t in texts]
    return [float(s) for s in _model.predict(pairs)]


def score(query: str, texts: list[str]) -> list[float]:
    """Relevance score for each of ``texts`` against ``query`` (higher = more relevant)."""
    if not texts:
        return []
    backend = settings.rerank_backend.lower()
    if backend == "fake":
        return _fake_score(query, texts)
    return _cross_encoder_score(query, texts)
