"""workspaces: rename tenant→workspace, role|user grants, invites, audit logs

Revision ID: 0003_workspaces
Revises: 0002_multitenancy
Create Date: 2026-08-08

Reworks the placeholder tenant model into first-class workspaces:
- tenants → workspaces (+ settings)
- tenant_memberships → workspace_memberships (tenant_id→workspace_id, created_at→joined_at)
- tenant_id → workspace_id on documents/chunks/conversations/messages/api_keys
- drop users.tenant_id (users are no longer bound to a single workspace)
- document_acls → document_access_grants (grant by role OR user)
- add invites, audit_logs; add documents.source
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003_workspaces"
down_revision: str | None = "0002_multitenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- workspaces ---
    op.rename_table("tenants", "workspaces")
    op.add_column(
        "workspaces",
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
    )

    # --- memberships ---
    op.rename_table("tenant_memberships", "workspace_memberships")
    op.alter_column("workspace_memberships", "tenant_id", new_column_name="workspace_id")
    op.alter_column("workspace_memberships", "created_at", new_column_name="joined_at")

    # --- workspace_id renames + drop placeholder defaults ---
    for table in ("documents", "chunks", "conversations", "messages", "api_keys"):
        op.alter_column(table, "tenant_id", new_column_name="workspace_id")
    for table in ("documents", "chunks", "conversations"):
        op.alter_column(table, "workspace_id", server_default=None)

    # users are no longer bound to a single workspace
    op.drop_column("users", "tenant_id")

    # documents.source (forward-compatible origin marker)
    op.add_column(
        "documents",
        sa.Column("source", sa.String(32), nullable=True, server_default="upload"),
    )

    # --- document_acls → document_access_grants ---
    op.drop_table("document_acls")
    op.create_table(
        "document_access_grants",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=False),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("grant_type", sa.String(8), nullable=False),
        sa.Column("role_or_user_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "document_id", "grant_type", "role_or_user_id", name="uq_grant_doc_type_value"
        ),
    )
    op.create_index(
        "ix_document_access_grants_document_id", "document_access_grants", ["document_id"]
    )

    # --- invites ---
    op.create_table(
        "invites",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("invited_by", UUID(as_uuid=False), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_invites_workspace_id", "invites", ["workspace_id"])
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token", "invites", ["token"], unique=True)

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(200), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("invites")
    op.drop_table("document_access_grants")
    op.create_table(
        "document_acls",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "user_id", name="uq_acl_document_user"),
    )
    op.drop_column("documents", "source")
    op.add_column(
        "users",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            nullable=False,
            server_default="00000000-0000-0000-0000-000000000000",
        ),
    )
    for table in ("documents", "chunks", "conversations", "messages", "api_keys"):
        op.alter_column(table, "workspace_id", new_column_name="tenant_id")
    op.alter_column("workspace_memberships", "joined_at", new_column_name="created_at")
    op.alter_column("workspace_memberships", "workspace_id", new_column_name="tenant_id")
    op.rename_table("workspace_memberships", "tenant_memberships")
    op.drop_column("workspaces", "settings")
    op.rename_table("workspaces", "tenants")
