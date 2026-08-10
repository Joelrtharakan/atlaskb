"""Document upload, listing, detail, and per-document access grants.

All access is workspace-scoped and role-gated. Retrieval enforcement lives in
``rbac.document_visible_clause`` / ``can_read_document``; this router enforces the
same rules for direct-by-id access and for who may *manage* access.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.celery_client import enqueue_ingest
from app.config import settings
from app.db import get_db
from app.deps import get_principal, require_role
from app.logging_config import get_logger
from app.models import (
    GRANT_ROLE,
    GRANT_USER,
    ROLE_EDITOR,
    ROLES,
    Chunk,
    Document,
    DocumentAccessGrant,
    WorkspaceMembership,
)
from app.rbac import Principal, can_read_document, document_visible_clause, role_at_least
from app.schemas import (
    AccessGrant,
    ChunkSample,
    ChunkSamplesResponse,
    DocumentAccessOut,
    DocumentAccessUpdate,
    DocumentDetail,
    DocumentOut,
)

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger(__name__)

_ALLOWED = {
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/x-markdown": ".md",
    "text/html": ".html",
}
_ALLOWED_SUFFIXES = {".pdf", ".md", ".markdown", ".html", ".htm"}


def _resolve_extension(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if upload.content_type in _ALLOWED:
        return _ALLOWED[upload.content_type]
    if suffix in _ALLOWED_SUFFIXES:
        return ".md" if suffix == ".markdown" else suffix
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "Only PDF, Markdown, or HTML files are supported.",
    )


def _load_document_or_404(db: Session, document_id: str, principal: Principal) -> Document:
    """Load a readable document, or 404 — never revealing out-of-workspace or
    access-restricted documents (this is the direct-by-id isolation path)."""
    doc = db.get(Document, document_id)
    if doc is None or not can_read_document(db, principal, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def _can_manage(doc: Document, principal: Principal) -> bool:
    return principal.is_admin or (
        doc.owner_id == principal.user_id and role_at_least(principal.role, ROLE_EDITOR)
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_EDITOR)),
) -> Document:
    ext = _resolve_extension(file)

    doc = Document(
        workspace_id=principal.workspace_id,
        owner_id=principal.user_id,
        filename=file.filename or f"upload{ext}",
        content_type=file.content_type or "application/octet-stream",
        storage_path="",
        source="upload",
        status="processing",
    )
    db.add(doc)
    db.flush()

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{doc.id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    doc.storage_path = str(dest)
    audit.record(
        db, workspace_id=principal.workspace_id, user_id=principal.user_id,
        action="document.upload", target=doc.id,
    )
    db.commit()
    db.refresh(doc)

    enqueue_ingest(doc.id)
    log.info(
        "documents.upload",
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        document_id=doc.id,
    )
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.workspace_id == principal.workspace_id, document_visible_clause(principal))
            .order_by(Document.created_at.desc())
        )
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDetail:
    doc = _load_document_or_404(db, document_id, principal)
    chunk_count = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        status=doc.status,
        source=doc.source,
        error=doc.error,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        last_verified_at=doc.last_verified_at,
        staleness=doc.staleness,
        chunk_count=chunk_count or 0,
        can_manage_access=_can_manage(doc, principal),
    )


@router.post("/{document_id}/verify", response_model=DocumentDetail)
def verify_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDetail:
    """Mark a document as freshly verified (resets its staleness to 0).

    Manage-gated like access changes — the owner or a workspace admin/editor.
    Display-only signal; does not touch chunks, retrieval, or ACL.
    """
    doc = _require_manage(db, document_id, principal)
    doc.last_verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(doc)
    chunk_count = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        status=doc.status,
        source=doc.source,
        error=doc.error,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        last_verified_at=doc.last_verified_at,
        staleness=doc.staleness,
        chunk_count=chunk_count or 0,
        can_manage_access=_can_manage(doc, principal),
    )


@router.post("/{document_id}/retry", response_model=DocumentDetail)
def retry_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDetail:
    """Re-enqueue ingestion for a document that's failed, or stuck in
    ``processing`` with no worker ever going to finish it (e.g. the message
    that dispatched it hit a worker that didn't have the task registered —
    a dispatch-level failure, which happens before `ingest_document`'s own
    try/except and so never reaches a terminal status on its own). Safe to
    call on an in-progress document too: ingestion re-does the same
    parse/chunk/embed/write idempotently rather than duplicating anything.
    """
    doc = _require_manage(db, document_id, principal)
    if doc.status not in ("failed", "processing"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a failed or processing document can be retried.")
    doc.status = "processing"
    doc.error = None
    db.commit()
    db.refresh(doc)
    enqueue_ingest(doc.id)
    chunk_count = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        status=doc.status,
        source=doc.source,
        error=doc.error,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        last_verified_at=doc.last_verified_at,
        staleness=doc.staleness,
        chunk_count=chunk_count or 0,
        can_manage_access=_can_manage(doc, principal),
    )


@router.get("/{document_id}/chunks", response_model=ChunkSamplesResponse)
def document_chunks(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ChunkSamplesResponse:
    """The document's chunks as Core-Sample strata.

    ``confidence`` is each chunk's embedding centrality — cosine similarity to the
    document's mean embedding — so representative chunks score high and
    boilerplate/outliers low. Read-only, ACL-scoped via ``_load_document_or_404``.
    """
    doc = _load_document_or_404(db, document_id, principal)
    rows = db.scalars(
        select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
    ).all()

    # Mean embedding of the document, then per-chunk cosine to it (centrality).
    vectors = [list(c.embedding) for c in rows if c.embedding is not None]
    confidences: dict[str, float] = {}
    if vectors:
        import numpy as np

        mat = np.asarray(vectors, dtype=float)
        mean = mat.mean(axis=0)
        mean_norm = np.linalg.norm(mean) or 1.0
        for c in rows:
            if c.embedding is None:
                confidences[c.id] = 0.5
                continue
            v = np.asarray(list(c.embedding), dtype=float)
            vn = np.linalg.norm(v) or 1.0
            cos = float(np.dot(v, mean) / (vn * mean_norm))
            confidences[c.id] = max(0.0, min(1.0, cos))

    layers = [
        ChunkSample(
            chunk_id=c.id,
            chunk_index=c.chunk_index,
            length=len(c.text),
            page_num=c.page_num,
            section=c.section,
            preview=c.text[:280],
            confidence=confidences.get(c.id, 0.5),
            staleness=doc.staleness,
        )
        for c in rows
    ]
    return ChunkSamplesResponse(document_id=doc.id, filename=doc.filename, layers=layers)


def _require_manage(db: Session, document_id: str, principal: Principal) -> Document:
    # Must be at least an editor to touch access at all...
    if not role_at_least(principal.role, ROLE_EDITOR):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Managing document access requires the editor role."
        )
    doc = db.get(Document, document_id)
    if doc is None or doc.workspace_id != principal.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    # ...and either own the document or be an admin.
    if not _can_manage(doc, principal):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the document's owner or a workspace admin can change its access.",
        )
    return doc


@router.get("/{document_id}/access", response_model=DocumentAccessOut)
def get_document_access(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentAccessOut:
    doc = _require_manage(db, document_id, principal)
    grants = db.scalars(
        select(DocumentAccessGrant).where(DocumentAccessGrant.document_id == doc.id)
    ).all()
    return DocumentAccessOut(
        grants=[AccessGrant(grant_type=g.grant_type, role_or_user_id=g.role_or_user_id) for g in grants]
    )


@router.patch("/{document_id}/access", response_model=DocumentAccessOut)
def set_document_access(
    document_id: str,
    body: DocumentAccessUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentAccessOut:
    doc = _require_manage(db, document_id, principal)

    # Validate grants: role grants must be real roles; user grants must be members.
    user_ids = {g.role_or_user_id for g in body.grants if g.grant_type == GRANT_USER}
    role_values = {g.role_or_user_id for g in body.grants if g.grant_type == GRANT_ROLE}
    bad_roles = role_values - set(ROLES)
    if bad_roles:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown role(s): {', '.join(sorted(bad_roles))}."
        )
    if user_ids:
        members = set(
            db.scalars(
                select(WorkspaceMembership.user_id).where(
                    WorkspaceMembership.workspace_id == principal.workspace_id,
                    WorkspaceMembership.user_id.in_(user_ids),
                )
            )
        )
        missing = user_ids - members
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"These users are not members of this workspace: {', '.join(sorted(missing))}.",
            )

    # Replace all grants wholesale (dedupe on the way in).
    db.query(DocumentAccessGrant).filter(DocumentAccessGrant.document_id == doc.id).delete()
    seen: set[tuple[str, str]] = set()
    for g in body.grants:
        key = (g.grant_type, g.role_or_user_id)
        if key in seen:
            continue
        seen.add(key)
        db.add(
            DocumentAccessGrant(
                document_id=doc.id, grant_type=g.grant_type, role_or_user_id=g.role_or_user_id
            )
        )
    audit.record(
        db, workspace_id=principal.workspace_id, user_id=principal.user_id,
        action="document.access_change", target=doc.id, meta={"grants": len(seen)},
    )
    db.commit()
    log.info("documents.access_set", document_id=doc.id, grants=len(seen))
    return DocumentAccessOut(
        grants=[AccessGrant(grant_type=t, role_or_user_id=v) for t, v in sorted(seen)]
    )
