"""Hands a connector's output to the existing ingestion pipeline.

external source -> connector -> normalized document -> parse -> chunk ->
embed -> version -> index -> existing RAG pipeline

Everything from "normalized document" onward is the exact same pipeline
direct upload already uses (``app.versioning.create_pending_version`` +
``app.ingest.ingest_document``) — this module's only job is to create a
``Document``/``DocumentVersion`` row per synced external document and track
``ConnectorDocument`` sync state, never to duplicate parsing/chunking/
embedding logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.ingest import ingest_document
from app.logging_config import get_logger
from app.models import ConnectorConfig, ConnectorDocument, Document
from app.versioning import create_pending_version, hash_file

from .base import Connector, ConnectorError, NormalizedDocument

log = get_logger(__name__)

_EXT_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/html": ".html",
}


def _extension_for(doc: NormalizedDocument) -> str:
    suffix = Path(doc.filename).suffix.lower()
    if suffix in (".pdf", ".md", ".markdown", ".html", ".htm"):
        return ".md" if suffix == ".markdown" else (".html" if suffix == ".htm" else suffix)
    return _EXT_BY_CONTENT_TYPE.get(doc.content_type, ".md")


def _write_and_ingest(
    db: Session,
    *,
    workspace_id: str,
    owner_id: str,
    provider: str,
    normalized: NormalizedDocument,
    existing_document_id: str | None,
) -> Document:
    """Reuses exactly the upload/reupload endpoints' own sequence: write
    bytes to ``upload_dir``, create a new Document (first sync) or a new
    DocumentVersion on the existing one (a changed re-sync — mirrors
    ``POST /documents/{id}/reupload``, not a second unrelated Document),
    then run the same ``ingest_document`` a Celery task would run for a
    direct upload — no parsing/chunking/embedding/versioning logic
    duplicated here."""
    ext = _extension_for(normalized)
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    doc = db.get(Document, existing_document_id) if existing_document_id else None
    is_new = doc is None
    if is_new:
        doc = Document(
            workspace_id=workspace_id,
            owner_id=owner_id,
            filename=normalized.filename,
            content_type=normalized.content_type,
            storage_path="",
            source=provider,
            status="processing",
        )
        db.add(doc)
        db.flush()
    else:
        doc.filename = normalized.filename
        doc.content_type = normalized.content_type
        doc.status = "processing"
        doc.error = None

    dest = upload_dir / f"{doc.id}-{datetime.now(UTC).timestamp()}{ext}" if not is_new else upload_dir / f"{doc.id}{ext}"
    dest.write_bytes(normalized.content)
    doc.storage_path = str(dest)

    create_pending_version(db, doc, source=provider, created_by=None)
    db.commit()
    db.refresh(doc)

    # Synchronous here — the caller (a Celery task in production, per Phase
    # 10's "sync runs on its own schedule" framing) already owns its own
    # background execution; ingest_document itself has no FastAPI/Celery
    # dependency (see app/ingest.py's own docstring) so it's safe to call
    # directly rather than re-enqueueing a second hop.
    ingest_document(doc.id)
    return doc


def run_connector_sync(
    db: Session, connector: Connector, config: ConnectorConfig, *, owner_id: str
) -> None:
    """Full sync: list every source the connector can see, fetch each,
    create/update the corresponding Document, and record
    ConnectorDocument sync state. Never raises past this function for a
    single document's failure — ``config.last_sync_status`` reflects
    whether the *connector-level* auth/connection succeeded, not whether
    every individual document did (those are per-``ConnectorDocument``
    ``sync_status``, so a partial failure is visible without hiding the
    documents that did succeed).
    """
    try:
        connector.authenticate()
        if not connector.test_connection():
            raise ConnectorError(f"connector {config.id} failed test_connection() after authenticate()")
        # Listing is connector-level, not per-document: a bad query, a
        # revoked scope, or an unreachable API here means the whole sync
        # never got off the ground, same as an auth failure — it must not
        # be left for the per-document try/except below to catch (that one
        # only runs once sources already exist). Real providers aren't
        # contractually limited to raising ConnectorError here (base.py
        # doesn't require it of list_sources()), so this catches broadly
        # rather than assuming every provider wraps its own client's errors.
        sources = connector.list_sources()
    except Exception as exc:  # noqa: BLE001 - any connector-level failure must surface as "error", not crash the task
        config.last_sync_status = "error"
        config.last_sync_at = datetime.now(UTC)
        db.commit()
        log.warning("connector.sync_failed", connector_id=config.id, provider=config.provider, error=str(exc))
        return

    for source in sources:
        record = db.scalar(
            select(ConnectorDocument).where(
                ConnectorDocument.connector_id == config.id,
                ConnectorDocument.external_document_id == source.external_id,
            )
        )
        try:
            normalized = connector.fetch_document(source.external_id)
            checksum = normalized.checksum
            if record is not None and record.checksum == checksum and checksum is not None:
                # Unchanged since last sync — skip re-ingesting identical content.
                record.last_sync_at = datetime.now(UTC)
                record.sync_status = "ok"
                db.commit()
                continue

            doc = _write_and_ingest(
                db, workspace_id=config.workspace_id, owner_id=owner_id,
                provider=config.provider, normalized=normalized,
                existing_document_id=record.document_id if record is not None else None,
            )
            if checksum is None:
                checksum = hash_file(doc.storage_path)

            if record is None:
                record = ConnectorDocument(
                    connector_id=config.id,
                    workspace_id=config.workspace_id,
                    external_source_id=config.provider,
                    external_document_id=source.external_id,
                )
                db.add(record)
            record.document_id = doc.id
            record.checksum = checksum
            record.external_version = normalized.external_version
            record.last_sync_at = datetime.now(UTC)
            record.sync_status = "ok"
            db.commit()
        except Exception as exc:  # noqa: BLE001 - one bad document must not abort the whole sync
            db.rollback()
            log.warning(
                "connector.document_sync_failed",
                connector_id=config.id, external_id=source.external_id, error=str(exc),
            )
            if record is not None:
                record.sync_status = "error"
                record.last_sync_at = datetime.now(UTC)
                db.commit()

    config.last_sync_status = "ok"
    config.last_sync_at = datetime.now(UTC)
    db.commit()
