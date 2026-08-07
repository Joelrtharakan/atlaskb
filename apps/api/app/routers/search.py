"""Raw retrieval endpoint — tenant/ACL-scoped, cached, rate-limited.

Exposes hybrid search results with scores so retrieval quality can be inspected
independently of generation. Accepts JWT or API-key auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.cache import cache_get, cache_key, cache_set
from app.config import settings
from app.db import get_db
from app.deps import get_principal
from app.embeddings import embed_query
from app.logging_config import get_logger
from app.ratelimit import check_rate_limit
from app.rbac import Principal
from app.retrieval import hybrid_search
from app.schemas import ScoredChunk, SearchRequest, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])
log = get_logger(__name__)


@router.post("", response_model=SearchResponse)
def search(
    body: SearchRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> SearchResponse:
    check_rate_limit(principal)

    key = cache_key(
        namespace="search",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        model=f"{settings.embedding_model}:k{body.top_k}",
        query=body.query,
    )
    cached = cache_get(key)
    if cached is not None:
        log.info("search.query", user_id=principal.user_id, cached=True)
        return SearchResponse(
            query=body.query,
            results=[ScoredChunk(**c) for c in cached["results"]],
            cached=True,
        )

    embedding = embed_query(body.query)
    hits = hybrid_search(db, body.query, embedding, principal, top_k=body.top_k)
    results = [
        ScoredChunk(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            text=h.text,
            page_num=h.page_num,
            section=h.section,
            score=h.score,
            dense_score=h.dense_score,
            sparse_score=h.sparse_score,
        )
        for h in hits
    ]
    cache_set(key, {"results": [r.model_dump() for r in results]})
    log.info(
        "search.query",
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        top_k=body.top_k,
        hits=len(results),
        cached=False,
    )
    return SearchResponse(query=body.query, results=results, cached=False)
