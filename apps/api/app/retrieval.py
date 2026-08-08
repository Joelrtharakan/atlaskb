"""Hybrid retrieval: dense (pgvector cosine) + sparse (Postgres full-text).

The two result sets are merged with Reciprocal Rank Fusion (RRF), which combines
rankings without needing the dense and sparse scores to be on the same scale —
it uses only rank position, so it is robust to the very different score
distributions of cosine similarity and ``ts_rank``.

:func:`reciprocal_rank_fusion` is a pure function and is unit-tested directly;
the ``*_search`` helpers wrap it around SQL queries.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document
from app.rbac import Principal, document_visible_clause


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    page_num: int | None
    section: str | None
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    """Fuse several ranked ID lists into one.

    ``rankings`` is a list of ranked lists, each ordered best-first. Each item
    contributes ``1 / (k + rank)`` (rank is 1-based) to its fused score. Returns
    ``(id, fused_score)`` pairs sorted by score descending, ties broken by id for
    determinism.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _scoped(stmt, principal: Principal):
    """Join chunks to their document and restrict to what ``principal`` may read.

    This is the single choke point that enforces tenant isolation + per-document
    ACLs on retrieval — both dense and sparse queries go through it.
    """
    return stmt.join(Document, Chunk.document_id == Document.id).where(
        Chunk.workspace_id == principal.workspace_id,
        document_visible_clause(principal),
    )


def dense_search(
    db: Session, embedding: list[float], principal: Principal, *, limit: int
) -> list[tuple[str, float]]:
    """Top-``limit`` visible chunks by cosine similarity. Returns (chunk_id, sim)."""
    distance = Chunk.embedding.cosine_distance(embedding)
    stmt = _scoped(
        select(Chunk.id, distance.label("dist")).where(Chunk.embedding.isnot(None)),
        principal,
    )
    rows = db.execute(stmt.order_by(distance).limit(limit)).all()
    # Cosine similarity = 1 - cosine distance.
    return [(cid, 1.0 - float(dist)) for cid, dist in rows]


def sparse_search(
    db: Session, query: str, principal: Principal, *, limit: int
) -> list[tuple[str, float]]:
    """Top-``limit`` visible chunks by full-text ``ts_rank_cd``. Returns (id, rank)."""
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.text_tsv, tsquery)
    stmt = _scoped(
        select(Chunk.id, rank.label("rank")).where(Chunk.text_tsv.op("@@")(tsquery)),
        principal,
    )
    rows = db.execute(stmt.order_by(rank.desc()).limit(limit)).all()
    return [(cid, float(r)) for cid, r in rows]


def hybrid_search(
    db: Session,
    query: str,
    embedding: list[float],
    principal: Principal,
    *,
    top_k: int | None = None,
    candidate_multiplier: int = 3,
) -> list[RetrievedChunk]:
    """Run dense + sparse retrieval (RBAC-scoped) and fuse with RRF.

    Pulls ``top_k * candidate_multiplier`` candidates from each side so RRF has
    enough overlap to work with, then returns the fused top ``top_k`` hydrated
    with chunk text and metadata. All candidates are already restricted to the
    principal's tenant and readable documents.
    """
    top_k = top_k or settings.retrieval_top_k
    candidates = top_k * candidate_multiplier

    dense = dense_search(db, embedding, principal, limit=candidates)
    sparse = sparse_search(db, query, principal, limit=candidates)

    dense_scores = dict(dense)
    sparse_scores = dict(sparse)

    fused = reciprocal_rank_fusion(
        [[cid for cid, _ in dense], [cid for cid, _ in sparse]],
        k=settings.rrf_k,
    )
    top = fused[:top_k]
    if not top:
        return []

    ids = [cid for cid, _ in top]
    chunk_rows = db.execute(select(Chunk).where(Chunk.id.in_(ids))).scalars().all()
    by_id = {c.id: c for c in chunk_rows}

    results: list[RetrievedChunk] = []
    for cid, fused_score in top:
        c = by_id.get(cid)
        if c is None:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=c.id,
                document_id=c.document_id,
                text=c.text,
                page_num=c.page_num,
                section=c.section,
                score=fused_score,
                dense_score=dense_scores.get(cid),
                sparse_score=sparse_scores.get(cid),
            )
        )
    return results
