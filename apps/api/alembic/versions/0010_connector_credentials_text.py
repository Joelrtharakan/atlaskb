"""Widen connector_configs.credentials_ref to TEXT (Trust Layer Phase 11).

Revision ID: 0010_connector_credentials_text
Revises: 0009_connectors
Create Date: 2026-08-12

Phase 10's VARCHAR(200) assumed a short opaque reference (e.g. a
secrets-manager key). Phase 11's Google Drive provider instead stores the
Fernet-encrypted refresh token (+ small provider config) directly here —
see app/connectors/tokens.py — and that encrypted blob routinely exceeds
200 characters, hitting Postgres's StringDataRightTruncation on the very
first real OAuth connection. No data to migrate: no connector has ever
successfully stored credentials before this fix.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_connector_credentials_text"
down_revision: str | None = "0009_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "connector_configs", "credentials_ref", type_=sa.Text(), existing_type=sa.String(200)
    )


def downgrade() -> None:
    op.alter_column(
        "connector_configs", "credentials_ref", type_=sa.String(200), existing_type=sa.Text()
    )
