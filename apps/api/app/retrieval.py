"""Hybrid retrieval: dense (pgvector cosine) + sparse (Postgres full-text).

The two result sets are merged with Reciprocal Rank Fusion (RRF), which combines
rankings without needing the dense and sparse scores to be on the same scale —
it uses only rank position, so it is robust to the very different score
distributions of cosine similarity and ``ts_rank``.

:func:`reciprocal_rank_fusion` is a pure function and is unit-tested directly;
the ``*_search`` helpers wrap it around SQL queries.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models import Chunk, Document, DocumentVersion
from app.rbac import Principal, document_visible_clause
from app.rerank import score as rerank_score
from app.timing import StageTimer

log = get_logger(__name__)


def config_fingerprint() -> str:
    """Short string identifying the active retrieval/rerank/version flags.

    Folded into every semantic-cache key that depends on retrieval (search and
    chat). Without this, flipping a T9.0 component-toggle flag with a warm
    cache would silently keep serving answers computed under the *previous*
    flag combination until the TTL expired — corrupting exactly the kind of
    before/after or ablation comparison these flags exist to support, and, in
    production, silently stale-serving across any real config change.
    """
    return (
        f"rm{settings.retrieval_mode}"
        f":rr{int(settings.rerank_enabled)}"
        f":va{int(settings.version_aware_retrieval)}"
        f":cd{int(settings.conflict_detection_enabled)}"
    )


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    version_id: str | None
    text: str
    page_num: int | None
    section: str | None
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None
    # The source document's staleness (0..1), so the LLM can caveat an answer
    # grounded only in old/unverified content instead of stating it as a
    # confident current fact (Trust Layer T9.3 adversarial finding).
    staleness: float = 0.0


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


def _scoped(stmt, principal: Principal, *, all_versions: bool = False):
    """Join chunks to their document, and restrict to what ``principal`` may read.

    This is the single choke point that enforces tenant isolation + per-document
    ACLs — both dense and sparse queries go through it. When
    ``settings.version_aware_retrieval`` is on (the default), it also joins
    ``DocumentVersion`` and restricts to ``is_current_version`` rows, so a
    superseded version's chunks are never returned. Turning that flag off
    (T9.0 ablation only) reproduces the pre-T1 behavior of searching every
    version's chunks at once.

    ``all_versions=True`` (Trust Layer Phase 2: temporal document targeting)
    explicitly searches every version regardless of the flag above — used only
    to figure out *which document* a historical question is about (a topic
    can be findable in an old version even if the current version no longer
    mentions it); it is never used to answer a question, only to locate a
    document before resolving which specific version to actually read.
    """
    stmt = stmt.join(Document, Chunk.document_id == Document.id)
    if settings.version_aware_retrieval and not all_versions:
        stmt = stmt.join(DocumentVersion, Chunk.version_id == DocumentVersion.id).where(
            DocumentVersion.is_current_version.is_(True)
        )
    return stmt.where(
        Chunk.workspace_id == principal.workspace_id,
        document_visible_clause(principal),
    )


def dense_search(
    db: Session, embedding: list[float], principal: Principal, *, limit: int, all_versions: bool = False
) -> list[tuple[str, float]]:
    """Top-``limit`` visible chunks by cosine similarity. Returns (chunk_id, sim)."""
    distance = Chunk.embedding.cosine_distance(embedding)
    stmt = _scoped(
        select(Chunk.id, distance.label("dist")).where(Chunk.embedding.isnot(None)),
        principal,
        all_versions=all_versions,
    )
    rows = db.execute(stmt.order_by(distance).limit(limit)).all()
    # Cosine similarity = 1 - cosine distance.
    return [(cid, 1.0 - float(dist)) for cid, dist in rows]


def sparse_search(
    db: Session, query: str, principal: Principal, *, limit: int, all_versions: bool = False
) -> list[tuple[str, float]]:
    """Top-``limit`` visible chunks by full-text ``ts_rank_cd``. Returns (id, rank)."""
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.text_tsv, tsquery)
    stmt = _scoped(
        select(Chunk.id, rank.label("rank")).where(Chunk.text_tsv.op("@@")(tsquery)),
        principal,
        all_versions=all_versions,
    )
    rows = db.execute(stmt.order_by(rank.desc()).limit(limit)).all()
    return [(cid, float(r)) for cid, r in rows]


def find_relevant_document(
    db: Session, query: str, embedding: list[float] | None, principal: Principal
) -> str | None:
    """Which document (searched across ALL versions) a question is most
    topically about — used only to locate a document before a temporal query
    (Trust Layer Phase 2) resolves which specific version to read. Never used
    to answer a question directly. Returns ``None`` if nothing matches at all.
    """
    dense = dense_search(db, embedding, principal, limit=5, all_versions=True) if embedding else []
    sparse = sparse_search(db, query, principal, limit=5, all_versions=True)
    fused = reciprocal_rank_fusion(
        [[cid for cid, _ in dense], [cid for cid, _ in sparse]], k=settings.rrf_k
    )
    if not fused:
        return None
    top_chunk_id = fused[0][0]
    row = db.execute(select(Chunk.document_id).where(Chunk.id == top_chunk_id)).first()
    return row[0] if row else None


def hybrid_search(
    db: Session,
    query: str,
    embedding: list[float] | None,
    principal: Principal,
    *,
    top_k: int | None = None,
    candidate_multiplier: int = 3,
    timer: StageTimer | None = None,
) -> list[RetrievedChunk]:
    """Run retrieval (RBAC-scoped) per ``settings.retrieval_mode``, then rerank.

    Modes (T9.0 component-toggle flags, eval/ablation harness only):
      * "hybrid" (default) — dense + sparse, fused with RRF.
      * "dense_only" — the sparse/BM25 query and RRF fusion never run at all.
      * "sparse_only" — the dense pgvector query never runs, and ``embedding``
        is expected to be ``None`` (the caller skips computing it too, so this
        mode has zero embedding cost, not just an unused vector).

    Pulls ``top_k * candidate_multiplier`` candidates so RRF (or the single
    active side, in a *_only mode) has enough to work with. When reranking is
    enabled (the default), the top ``settings.rerank_candidate_k`` candidates are
    hydrated and re-scored by a cross-encoder that reads the query and each
    chunk's text together — a more accurate relevance signal than RRF's
    rank-position-only fusion — and the final ``top_k`` is chosen from *that*
    ordering. All candidates are already restricted to the principal's tenant
    and readable documents.
    """
    top_k = top_k or settings.retrieval_top_k
    candidates = top_k * candidate_multiplier
    mode = settings.retrieval_mode

    dense: list[tuple[str, float]] = []
    sparse: list[tuple[str, float]] = []
    with timer.stage("retrieval") if timer else contextlib.nullcontext():
        if mode in ("hybrid", "dense_only"):
            if embedding is None:
                raise ValueError(f"retrieval_mode={mode!r} requires an embedding, got None")
            dense = dense_search(db, embedding, principal, limit=candidates)
        if mode in ("hybrid", "sparse_only"):
            sparse = sparse_search(db, query, principal, limit=candidates)

        dense_scores = dict(dense)
        sparse_scores = dict(sparse)

        if mode == "dense_only":
            fused = list(dense)
        elif mode == "sparse_only":
            fused = list(sparse)
        elif mode == "hybrid":
            fused = reciprocal_rank_fusion(
                [[cid for cid, _ in dense], [cid for cid, _ in sparse]],
                k=settings.rrf_k,
            )
        else:
            raise ValueError(f"unknown retrieval_mode: {mode!r}")

    log.info(
        "retrieval.hybrid_search",
        mode=mode,
        dense_candidates=len(dense),
        sparse_candidates=len(sparse),
        fused_candidates=len(fused),
        rerank_enabled=settings.rerank_enabled,
        version_aware=settings.version_aware_retrieval,
    )

    pool_size = max(top_k, settings.rerank_candidate_k) if settings.rerank_enabled else top_k
    pool = fused[:pool_size]
    if not pool:
        return []

    fused_scores = dict(pool)
    ids = [cid for cid, _ in pool]
    chunk_rows = db.execute(select(Chunk).where(Chunk.id.in_(ids))).scalars().all()
    by_id = {c.id: c for c in chunk_rows}
    ordered_ids = [cid for cid in ids if cid in by_id]

    doc_ids = {c.document_id for c in chunk_rows}
    staleness_by_doc = {
        d.id: d.staleness
        for d in db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars()
    } if doc_ids else {}

    rerank_scores: dict[str, float] = {}
    if settings.rerank_enabled and ordered_ids:
        with timer.stage("reranking") if timer else contextlib.nullcontext():
            texts = [by_id[cid].text for cid in ordered_ids]
            scores = rerank_score(query, texts)
            rerank_scores = dict(zip(ordered_ids, scores, strict=True))
            ordered_ids.sort(key=lambda cid: rerank_scores[cid], reverse=True)

    results: list[RetrievedChunk] = []
    for cid in ordered_ids[:top_k]:
        c = by_id[cid]
        results.append(
            RetrievedChunk(
                chunk_id=c.id,
                document_id=c.document_id,
                version_id=c.version_id,
                text=c.text,
                page_num=c.page_num,
                section=c.section,
                score=rerank_scores.get(cid, fused_scores[cid]),
                dense_score=dense_scores.get(cid),
                sparse_score=sparse_scores.get(cid),
                rerank_score=rerank_scores.get(cid),
                staleness=staleness_by_doc.get(c.document_id, 0.0),
            )
        )
    return results
