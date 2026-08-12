"""Document version helpers shared by the upload/reupload endpoints and ingest.py."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion


def hash_file(storage_path: str) -> str:
    digest = hashlib.sha256()
    with Path(storage_path).open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def current_version(db: Session, document_id: str) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_current_version.is_(True),
        )
    )


def create_pending_version(
    db: Session, doc: Document, *, source: str | None, created_by: str | None
) -> DocumentVersion:
    """Add the next version row for ``doc``, not yet marked current.

    ``ingest_document`` flips ``is_current_version`` once the new version's
    chunks finish writing successfully — a version that fails ingestion is
    never promoted, so the document always has exactly one current version
    (or none, if it has never ingested successfully).
    """
    next_number = (
        db.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == doc.id
            )
        )
        or 0
    ) + 1
    version = DocumentVersion(
        document_id=doc.id,
        version_number=next_number,
        content_hash=hash_file(doc.storage_path),
        source=source,
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    return version
