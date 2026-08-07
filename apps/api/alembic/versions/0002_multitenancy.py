"""multitenancy: tenants, memberships, api keys, document ACLs, conversations

Revision ID: 0002_multitenancy
Revises: 0001_initial
Create Date: 2026-08-07

Backfills a tenant matching the pre-multitenancy DEFAULT_TENANT_ID and makes all
existing users admins of it, so their existing documents/chunks remain reachable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002_multitenancy"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("lookup", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_lookup", "api_keys", ["lookup"], unique=True)

    op.create_table(
        "document_acls",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=False),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "user_id", name="uq_acl_document_user"),
    )
    op.create_index("ix_document_acls_document_id", "document_acls", ["document_id"])

    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False, server_default="Untitled"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=False),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])

    # --- Backfill: default tenant + admin memberships for existing users. ---
    op.execute(
        sa.text(
            "INSERT INTO tenants (id, name) VALUES (CAST(:id AS uuid), :name) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(id=DEFAULT_TENANT_ID, name="Default workspace")
    )
    op.execute(
        sa.text(
            "INSERT INTO tenant_memberships (id, tenant_id, user_id, role) "
            "SELECT gen_random_uuid(), CAST(:tenant AS uuid), u.id, 'admin' FROM users u "
            "ON CONFLICT (tenant_id, user_id) DO NOTHING"
        ).bindparams(tenant=DEFAULT_TENANT_ID)
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("document_acls")
    op.drop_table("api_keys")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
