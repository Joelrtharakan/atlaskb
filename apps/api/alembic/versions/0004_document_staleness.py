"""documents.last_verified_at (freshness / staleness signal)

Revision ID: 0004_document_staleness
Revises: 0003_workspaces
Create Date: 2026-08-09

Adds a nullable ``last_verified_at`` timestamp to documents. Freshness decays
from this (or created_at, if never verified); the derived staleness score is
computed in the app layer and is display-only — no retrieval/ACL impact.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_staleness"
down_revision: str | None = "0003_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "last_verified_at")
