"""message_feedback (Trust Layer T6: feedback loop)

Revision ID: 0007_message_feedback
Revises: 0006_document_versions
Create Date: 2026-08-11

Lets a user thumbs up/down an assistant answer. One rating per (message,
user); re-rating overwrites via upsert rather than accumulating duplicates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0007_message_feedback"
down_revision: str | None = "0006_document_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=False),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
    )
    op.create_index("ix_message_feedback_message_id", "message_feedback", ["message_id"])
    op.create_index("ix_message_feedback_workspace_id", "message_feedback", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_workspace_id", "message_feedback")
    op.drop_index("ix_message_feedback_message_id", "message_feedback")
    op.drop_table("message_feedback")
