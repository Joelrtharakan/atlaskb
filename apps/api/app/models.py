"""SQLAlchemy ORM models.

A **user account is separate from a workspace**. Users join zero or more
workspaces via ``workspace_memberships``, each with a role (viewer/editor/admin).
Documents, chunks, conversations, API keys, and audit logs are scoped to a
``workspace_id``. Per-document access is layered on top of role via
``document_access_grants`` (grant by role or by named user); absence of any grant
means "visible to all workspace members".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base

# Roles, lowest to highest privilege.
ROLE_VIEWER = "viewer"
ROLE_EDITOR = "editor"
ROLE_ADMIN = "admin"
ROLES = (ROLE_VIEWER, ROLE_EDITOR, ROLE_ADMIN)

# Grant types for document_access_grants.
GRANT_ROLE = "role"
GRANT_USER = "user"


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    # Nullable (Trust Layer Phase 11): an SSO-only user, created via OIDC
    # login rather than /auth/signup, has no AtlasKB password at all — not
    # an empty string or a sentinel hash, genuinely null, so
    # verify_password() is never reachable for that account (see
    # app/routers/auth.py's login(), which must check for None first).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    documents: Mapped[list[Document]] = relationship(back_populates="owner")
    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="user")
    identities: Mapped[list[UserIdentity]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserIdentity(Base):
    """Links a ``User`` to one external identity provider account (Trust
    Layer Phase 11: OIDC SSO). Kept as its own table rather than columns on
    ``User`` so a single AtlasKB account can later be linked to more than
    one IdP (e.g. Google *and* Okta) without a schema change — Phase 11
    itself only ever creates one row per user (one configured OIDC issuer
    at a time), but the shape doesn't foreclose more."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_user_identity_issuer_subject"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "oidc"
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)  # the IdP's `iss` claim
    subject: Mapped[str] = mapped_column(String(255), nullable=False)  # the IdP's `sub` claim
    email: Mapped[str] = mapped_column(String(320), nullable=False)  # IdP's email at link time
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="identities")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="workspace")


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_VIEWER)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_VIEWER)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    invited_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_VIEWER)
    lookup: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Forward-compatible origin marker: 'upload' today, an external connector
    # ('confluence', 'gdrive', …) in a future phase — no schema change needed.
    source: Mapped[str | None] = mapped_column(String(32), nullable=True, default="upload")
    # Lifecycle: processing -> ready | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # When a human last confirmed this document is still current. Null until the
    # first verification; freshness then decays with age. Drives the Dashboard
    # relief-map valleys and the Fog-of-War staleness signal (frontend), and is
    # independent of retrieval/ACL logic.
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    owner: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def staleness(self) -> float:
        """0.0 (fresh) → 1.0 (fully stale), from age since last verification.

        Age is measured from ``last_verified_at`` if the document has ever been
        verified, otherwise from ``created_at``. Fully stale once older than
        ``settings.staleness_max_age_days``. Read-only/derived — carried through
        ``DocumentOut`` so the UI can render freshness without extra queries.
        """
        from app.config import settings

        anchor = self.last_verified_at or self.created_at
        if anchor is None:
            return 0.0
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        age_days = (datetime.now(UTC) - anchor).total_seconds() / 86400.0
        span = max(1, settings.staleness_max_age_days)
        return max(0.0, min(1.0, age_days / span))
    grants: Mapped[list[DocumentAccessGrant]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentAccessGrant(Base):
    """Per-document access override. If a document has any grant rows, only the
    granted roles / named users (plus the owner and workspace admins) may read
    it. No grant rows → visible to all workspace members."""

    __tablename__ = "document_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "grant_type", "role_or_user_id", name="uq_grant_doc_type_value"
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grant_type: Mapped[str] = mapped_column(String(8), nullable=False)  # 'role' | 'user'
    role_or_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="grants")


class DocumentVersion(Base):
    """One ingested revision of a document. Re-uploading never overwrites a prior
    version's chunks in place — it creates a new version row and re-points
    retrieval at it, so history stays queryable (lineage) while search only ever
    sees the current version (see ``retrieval.py``'s ``is_current_version`` scoping)."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_doc_number"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    is_current_version: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    document: Mapped[Document] = relationship()
    chunks: Mapped[list[Chunk]] = relationship(back_populates="version")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim), nullable=True)
    text_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    version: Mapped[DocumentVersion | None] = relationship(back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Untitled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Full ChatResponse payload (citations, evidence, trust_summary, conflicts,
    # retrieved chunks) for an assistant message — None for user messages and
    # for assistant messages written before this column existed. Without this,
    # reopening a past conversation could only ever show plain text: citations,
    # the trust panel, and "Why this answer?" all depend on data this table
    # never used to keep.
    response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class MessageFeedback(Base):
    """A user's thumbs up/down on one assistant answer. One rating per
    (message, user) — re-rating overwrites rather than accumulating duplicates,
    since it's "does this answer look right to you", not a vote count."""

    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String(8), nullable=False)  # "up" | "down"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContentGapResolution(Base):
    """Marks a content-gap cluster (identified by a stable key derived from its
    representative query) as resolved. Gaps themselves are derived on the fly from
    unanswered chat turns; only the resolution state is persisted."""

    __tablename__ = "content_gap_resolutions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "gap_key", name="uq_gap_resolution_ws_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    gap_key: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConflictRecord(Base):
    """Persisted output of the structured conflict-detection pipeline (Trust
    Layer Phase 1) — one row per *classified chunk pair*, not only the
    contradictions: SUPPORTS/COMPLEMENTS/UNRELATED/UNCERTAIN pairs are written
    too, so the full classification is auditable even though ``/chat``'s
    response only surfaces CONTRADICTS pairs today. Always workspace-scoped —
    the pipeline only ever runs over chunks already RBAC/workspace-scoped by
    retrieval, so a row here can never span two workspaces."""

    __tablename__ = "conflicts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)

    document_id_a: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    document_version_a: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    chunk_id_a: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    claim_a: Mapped[str] = mapped_column(Text, nullable=False)

    document_id_b: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    document_version_b: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    chunk_id_b: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    claim_b: Mapped[str] = mapped_column(Text, nullable=False)

    # SUPPORTS | CONTRADICTS | COMPLEMENTS | UNRELATED | UNCERTAIN
    relationship: Mapped[str] = mapped_column(String(16), nullable=False)
    # 0.0-1.0. "deterministic" rows use fixed constants documented in
    # app/config.py; "llm" rows are the model's own self-reported confidence,
    # not independently calibrated — see eval/conflicts/README.md.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # "deterministic" | "llm" — which pipeline stage produced this classification.
    method: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConnectorConfig(Base):
    """One configured connection to an external source (Trust Layer
    Phase 10 architecture, Phase 11 real Google Drive provider; see
    app/connectors/base.py and app/connectors/google_drive.py).
    ``credentials_ref`` is deliberately never a plaintext secret — for the
    Google Drive provider it's a Fernet-encrypted OAuth refresh token (see
    app/connectors/tokens.py), decrypted only in-memory for the duration of
    a sync."""

    __tablename__ = "connector_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "google_drive"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # TEXT, not VARCHAR(200): holds the Fernet-encrypted refresh token (see
    # app/connectors/tokens.py), which routinely exceeds 200 chars.
    credentials_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active | disabled
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ok | error


class ConnectorDocument(Base):
    """Sync state for one external document under a ``ConnectorConfig`` —
    links it to the normal ``Document`` row once first synced, so re-syncs
    can tell "new" from "changed" from "unchanged" without re-fetching
    content that hasn't changed (``checksum``/``external_version``)."""

    __tablename__ = "connector_documents"
    __table_args__ = (
        UniqueConstraint(
            "connector_id", "external_document_id", name="uq_connector_doc_external_id"
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    connector_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    external_source_id: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. drive folder/site id
    external_document_id: Mapped[str] = mapped_column(String(300), nullable=False)
    document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    permission_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending|ok|error


# GIN index for full-text search; the vector (HNSW) index is created in the
# migration so index parameters can be tuned independently of the model.
Index("ix_chunks_text_tsv", Chunk.text_tsv, postgresql_using="gin")
