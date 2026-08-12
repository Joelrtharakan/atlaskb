"""conflicts (Trust Layer Phase 1: structured conflict-detection pipeline)

Revision ID: 0008_conflicts
Revises: 0007_message_feedback
Create Date: 2026-08-11

Introduces a `conflicts` table so the structured conflict-detection pipeline
(claim extraction -> candidate pairing -> relationship classification ->
confidence scoring) has somewhere to persist its output. Every classified
chunk pair is written (SUPPORTS/CONTRADICTS/COMPLEMENTS/UNRELATED/UNCERTAIN),
not only contradictions -- this is a full audit trail, not just what surfaces
in the `/chat` "Sources disagree" banner. No backfill: conflict detection was
previously ephemeral (request-scoped only, never persisted), so there is
nothing to migrate from.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008_conflicts"
down_revision: str | None = "0007_message_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conflicts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("document_id_a", UUID(as_uuid=False), nullable=False),
        sa.Column("document_version_a", UUID(as_uuid=False), nullable=True),
        sa.Column("chunk_id_a", UUID(as_uuid=False), nullable=False),
        sa.Column("claim_a", sa.Text(), nullable=False),
        sa.Column("document_id_b", UUID(as_uuid=False), nullable=False),
        sa.Column("document_version_b", UUID(as_uuid=False), nullable=True),
        sa.Column("chunk_id_b", UUID(as_uuid=False), nullable=False),
        sa.Column("claim_b", sa.Text(), nullable=False),
        sa.Column("relationship", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_conflicts_workspace_id", "conflicts", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_conflicts_workspace_id", "conflicts")
    op.drop_table("conflicts")
