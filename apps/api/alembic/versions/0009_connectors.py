"""connector_configs, connector_documents (Trust Layer Phase 10: connector
architecture -- no real provider ships in this phase, see app/connectors/)

Revision ID: 0009_connectors
Revises: 0008_conflicts
Create Date: 2026-08-12

Introduces the metadata tables a generic connector abstraction needs:
`connector_configs` (one row per configured external connection --
credentials_ref is deliberately never a plaintext secret, just an opaque
reference) and `connector_documents` (per-external-document sync state,
linking to the normal `documents` table once first synced). No backfill --
no connector has ever existed in this codebase before this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009_connectors"
down_revision: str | None = "0008_conflicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_configs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("credentials_ref", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(16), nullable=True),
    )
    op.create_index("ix_connector_configs_workspace_id", "connector_configs", ["workspace_id"])

    op.create_table(
        "connector_documents",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "connector_id",
            UUID(as_uuid=False),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("external_source_id", sa.String(64), nullable=False),
        sa.Column("external_document_id", sa.String(300), nullable=False),
        sa.Column(
            "document_id", UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("external_version", sa.String(200), nullable=True),
        sa.Column("permission_metadata", JSONB(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(16), nullable=False, server_default="pending"),
        sa.UniqueConstraint(
            "connector_id", "external_document_id", name="uq_connector_doc_external_id"
        ),
    )
    op.create_index("ix_connector_documents_connector_id", "connector_documents", ["connector_id"])
    op.create_index("ix_connector_documents_workspace_id", "connector_documents", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_connector_documents_workspace_id", "connector_documents")
    op.drop_index("ix_connector_documents_connector_id", "connector_documents")
    op.drop_table("connector_documents")
    op.drop_index("ix_connector_configs_workspace_id", "connector_configs")
    op.drop_table("connector_configs")
