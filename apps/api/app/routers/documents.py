"""Document upload, listing, detail, and per-document ACLs (tenant-scoped)."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_client import enqueue_ingest
from app.config import settings
from app.db import get_db
from app.deps import get_principal, require_role
from app.logging_config import get_logger
from app.models import (
    ROLE_EDITOR,
    Chunk,
    Document,
    DocumentACL,
    TenantMembership,
)
from app.rbac import Principal, document_visible_clause
from app.schemas import DocumentACLOut, DocumentACLUpdate, DocumentDetail, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger(__name__)

# Accepted upload types, mapped to a canonical extension.
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


def _load_visible_document(db: Session, document_id: str, principal: Principal) -> Document:
    """Load a document the principal may read, or raise 404.

    404 (not 403) for out-of-tenant or ACL-hidden documents so their existence
    is never revealed.
    """
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not principal.is_admin and doc.owner_id != principal.user_id:
        acl_ids = set(
            db.scalars(select(DocumentACL.user_id).where(DocumentACL.document_id == doc.id))
        )
        if acl_ids and principal.user_id not in acl_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_EDITOR)),
) -> Document:
    ext = _resolve_extension(file)

    doc = Document(
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        filename=file.filename or f"upload{ext}",
        content_type=file.content_type or "application/octet-stream",
        storage_path="",  # set below once we know the id
        status="processing",
    )
    db.add(doc)
    db.flush()  # assigns doc.id without committing

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{doc.id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    doc.storage_path = str(dest)
    db.commit()
    db.refresh(doc)

    enqueue_ingest(doc.id)
    log.info(
        "documents.upload",
        tenant_id=principal.tenant_id,
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
            .where(Document.tenant_id == principal.tenant_id, document_visible_clause(principal))
            .order_by(Document.created_at.desc())
        )
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentDetail:
    doc = _load_visible_document(db, document_id, principal)
    chunk_count = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunk_count=chunk_count or 0,
    )


def _require_owner_or_admin(doc: Document, principal: Principal) -> None:
    if not principal.is_admin and doc.owner_id != principal.user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the document owner or a workspace admin can manage its access list.",
        )


@router.get("/{document_id}/acl", response_model=DocumentACLOut)
def get_document_acl(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentACLOut:
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _require_owner_or_admin(doc, principal)
    user_ids = list(
        db.scalars(select(DocumentACL.user_id).where(DocumentACL.document_id == doc.id))
    )
    return DocumentACLOut(user_ids=user_ids)


@router.put("/{document_id}/acl", response_model=DocumentACLOut)
def set_document_acl(
    document_id: str,
    body: DocumentACLUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> DocumentACLOut:
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _require_owner_or_admin(doc, principal)

    requested = set(body.user_ids)
    if requested:
        members = set(
            db.scalars(
                select(TenantMembership.user_id).where(
                    TenantMembership.tenant_id == principal.tenant_id,
                    TenantMembership.user_id.in_(requested),
                )
            )
        )
        missing = requested - members
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Every user in the access list must be a member of this workspace. "
                f"Not members: {', '.join(sorted(missing))}.",
            )

    # Replace the allowlist wholesale.
    db.query(DocumentACL).filter(DocumentACL.document_id == doc.id).delete()
    for uid in requested:
        db.add(DocumentACL(document_id=doc.id, user_id=uid))
    db.commit()
    log.info("documents.acl_set", document_id=doc.id, count=len(requested))
    return DocumentACLOut(user_ids=sorted(requested))
