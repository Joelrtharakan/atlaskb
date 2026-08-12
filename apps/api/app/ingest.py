"""Ingestion pipeline: parse -> chunk -> embed -> write chunks.

Lives in the shared ``app`` package so the Celery worker can call it directly
(``apps/workers`` depends on ``atlaskb-api``). Kept free of any Celery/FastAPI
imports so it can be run and tested standalone.
"""

from __future__ import annotations

from sqlalchemy import select

from app.chunking import chunk_blocks, parse_document
from app.db import SessionLocal
from app.embeddings import embed_texts
from app.logging_config import get_logger
from app.models import Chunk, Document, DocumentVersion

log = get_logger(__name__)

# Embed in batches to bound memory when a document has many chunks.
_EMBED_BATCH = 64


def ingest_document(document_id: str) -> None:
    """Process one document end to end, updating its status to ready/failed.

    Operates on the document's latest ``DocumentVersion`` row (created
    synchronously by the upload/reupload endpoint before enqueueing this task —
    it's always the highest ``version_number`` for the document, pending or
    already-current). Chunks are written tagged with that version; the version
    is only promoted to current once its chunks finish writing successfully, so
    a failed re-ingest never leaves the document without a working version.
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("ingest.missing_document", document_id=document_id)
            return

        version = db.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
        )
        if version is None:
            log.warning("ingest.missing_version", document_id=document_id)
            return

        try:
            blocks = parse_document(doc.storage_path, doc.content_type)
            chunks = chunk_blocks(blocks)
            log.info(
                "ingest.parsed",
                document_id=document_id,
                version_number=version.version_number,
                blocks=len(blocks),
                chunks=len(chunks),
            )

            if not chunks:
                raise ValueError("no extractable text in document")

            texts = [c.text for c in chunks]
            embeddings: list[list[float]] = []
            for i in range(0, len(texts), _EMBED_BATCH):
                embeddings.extend(embed_texts(texts[i : i + _EMBED_BATCH]))

            # Replace this version's own chunks (idempotent retry of the same version).
            db.query(Chunk).filter(Chunk.version_id == version.id).delete()
            for c, vec in zip(chunks, embeddings, strict=True):
                db.add(
                    Chunk(
                        document_id=doc.id,
                        workspace_id=doc.workspace_id,
                        version_id=version.id,
                        chunk_index=c.chunk_index,
                        text=c.text,
                        page_num=c.page_num,
                        section=c.section,
                        embedding=vec,
                    )
                )

            # Promote this version to current; demote whichever one held it before.
            db.query(DocumentVersion).filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.id != version.id,
                DocumentVersion.is_current_version.is_(True),
            ).update({"is_current_version": False})
            version.is_current_version = True

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
