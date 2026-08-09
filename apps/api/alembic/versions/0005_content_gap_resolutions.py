"""content_gap_resolutions (Fog of War resolve state)

Revision ID: 0005_content_gap_resolutions
Revises: 0004_document_staleness
Create Date: 2026-08-09

Persists which content-gap clusters an admin has marked resolved. The gaps
themselves are derived on the fly from unanswered chat turns; only resolution
state is stored, keyed by a stable hash of the cluster's representative query.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005_content_gap_resolutions"
down_revision: str | None = "0004_document_staleness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_gap_resolutions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("gap_key", sa.String(32), nullable=False),
        sa.Column("resolved_by", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "gap_key", name="uq_gap_resolution_ws_key"),
    )
    op.create_index(
        "ix_content_gap_resolutions_workspace_id",
        "content_gap_resolutions",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_gap_resolutions_workspace_id", "content_gap_resolutions")
    op.drop_table("content_gap_resolutions")
