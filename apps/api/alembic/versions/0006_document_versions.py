"""document_versions (Trust Layer T1: versioning & lineage)

Revision ID: 0006_document_versions
Revises: 0005_content_gap_resolutions
Create Date: 2026-08-11

Introduces a `document_versions` table so a document can be re-uploaded
without losing its history: each re-ingest creates a new version row instead
of silently overwriting chunks in place. `chunks.version_id` ties every chunk
to the version that produced it, so retrieval can be scoped to only the
current version while old versions stay queryable for lineage/history views.

Existing documents are backfilled to a single version_number=1 row (content
hash computed from the file on disk where it's still readable) and all of
their existing chunks are pointed at it, marked current.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006_document_versions"
down_revision: str | None = "0005_content_gap_resolutions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hash_file(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    path = Path(storage_path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=False),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "is_current_version", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_doc_number"
        ),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    op.add_column(
        "chunks",
        sa.Column(
            "version_id",
            UUID(as_uuid=False),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_version_id", "chunks", ["version_id"])

    bind = op.get_bind()
    documents = bind.execute(sa.text("SELECT id, storage_path FROM documents")).fetchall()
    for doc_id, storage_path in documents:
        version_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                """
                INSERT INTO document_versions
                    (id, document_id, version_number, content_hash, source, is_current_version)
                VALUES
                    (:id, :document_id, 1, :content_hash, 'upload', true)
                """
            ),
            {
                "id": version_id,
                "document_id": doc_id,
                "content_hash": _hash_file(storage_path),
            },
        )
        bind.execute(
            sa.text("UPDATE chunks SET version_id = :version_id WHERE document_id = :document_id"),
            {"version_id": version_id, "document_id": doc_id},
        )


def downgrade() -> None:
    op.drop_index("ix_chunks_version_id", "chunks")
    op.drop_column("chunks", "version_id")
    op.drop_index("ix_document_versions_document_id", "document_versions")
    op.drop_table("document_versions")
