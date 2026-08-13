"""messages.response_json (chat history rehydration).

Revision ID: 0012_message_response_json
Revises: 0011_oidc_identities
Create Date: 2026-08-13

The chat frontend previously kept conversation state only in an in-memory
React useState, so navigating away and back lost the whole transcript.
Fixing that means treating GET /conversations/{id} as the source of truth
on every remount -- but `messages` only ever stored role+content, so a
rehydrated turn could show the answer text and nothing else: no citations,
no evidence, no trust summary, no conflicts. This column stores the full
ChatResponse an assistant message was created from, so reopening a past
conversation looks the same as it did when it was first answered. Nullable
and not backfilled -- existing assistant messages predate this column and
simply render as plain text, same as before this change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012_message_response_json"
down_revision: str | None = "0011_oidc_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("response_json", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "response_json")
