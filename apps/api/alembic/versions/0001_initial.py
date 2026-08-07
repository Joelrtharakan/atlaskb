"""initial schema: users, documents, chunks (pgvector + full-text)

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

from app.config import settings

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # pgvector must exist before any vector column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
        sa.Column(
            "owner_id",
            UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=False),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(settings.embedding_dim), nullable=True),
        sa.Column(
            "text_tsv",
            TSVECTOR,
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index(
        "ix_chunks_text_tsv", "chunks", ["text_tsv"], postgresql_using="gin"
    )
    # Approximate-nearest-neighbour index for dense cosine search.
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("users")
