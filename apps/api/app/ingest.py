"""Ingestion pipeline: parse -> chunk -> embed -> write chunks.

Lives in the shared ``app`` package so the Celery worker can call it directly
(``apps/workers`` depends on ``atlaskb-api``). Kept free of any Celery/FastAPI
imports so it can be run and tested standalone.
"""

from __future__ import annotations

from app.chunking import chunk_blocks, parse_document
from app.db import SessionLocal
from app.embeddings import embed_texts
from app.logging_config import get_logger
from app.models import Chunk, Document

log = get_logger(__name__)

# Embed in batches to bound memory when a document has many chunks.
_EMBED_BATCH = 64


def ingest_document(document_id: str) -> None:
    """Process one document end to end, updating its status to ready/failed."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("ingest.missing_document", document_id=document_id)
            return

        try:
            blocks = parse_document(doc.storage_path, doc.content_type)
            chunks = chunk_blocks(blocks)
            log.info(
                "ingest.parsed",
                document_id=document_id,
                blocks=len(blocks),
                chunks=len(chunks),
            )

            if not chunks:
                raise ValueError("no extractable text in document")

            texts = [c.text for c in chunks]
            embeddings: list[list[float]] = []
            for i in range(0, len(texts), _EMBED_BATCH):
                embeddings.extend(embed_texts(texts[i : i + _EMBED_BATCH]))

            # Replace any prior chunks (idempotent re-ingest).
            db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
            for c, vec in zip(chunks, embeddings, strict=True):
                db.add(
                    Chunk(
                        document_id=doc.id,
                        tenant_id=doc.tenant_id,
                        chunk_index=c.chunk_index,
                        text=c.text,
                        page_num=c.page_num,
                        section=c.section,
                        embedding=vec,
                    )
                )

            doc.status = "ready"
            doc.error = None
            db.commit()
            log.info("ingest.ready", document_id=document_id, chunks=len(chunks))
        except Exception as exc:
            db.rollback()
            doc = db.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = str(exc)[:1000]
                db.commit()
            log.exception("ingest.failed", document_id=document_id, error=str(exc))
    finally:
        db.close()
