"""users.password_hash nullable + user_identities table (Trust Layer Phase 11: OIDC SSO).

Revision ID: 0011_oidc_identities
Revises: 0010_connector_credentials_text
Create Date: 2026-08-12

An SSO-only user (created via OIDC login, not /auth/signup) has no
AtlasKB password at all, so `password_hash` must accept NULL. No existing
row needs backfilling -- every current user already has a real password
hash from signup, and NULL is opt-in going forward, not retroactive.

`user_identities` links a User to one external IdP account (issuer +
subject uniquely identify one IdP account, per the OIDC spec) -- kept
separate from `users` rather than adding columns there so a single
account could later link more than one provider without another schema
change, even though Phase 11 itself only ever configures one issuer.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011_oidc_identities"
down_revision: str | None = "0010_connector_credentials_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)

    op.create_table(
        "user_identities",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_user_identity_issuer_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_identities_user_id", "user_identities")
    op.drop_table("user_identities")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
