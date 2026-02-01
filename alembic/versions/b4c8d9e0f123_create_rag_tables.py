"""create_rag_tables

Revision ID: b4c8d9e0f123
Revises: 37e16ecef223
Create Date: 2026-02-01 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4c8d9e0f123"
down_revision: Union[str, None] = "37e16ecef223"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration - create document_source and document_chunk tables with pgvector."""
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create document_source table
    op.create_table(
        "document_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        # Timestamps (from TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_path", name="uq_source_type_path"),
    )

    # Create indexes for document_source
    op.create_index(
        op.f("ix_document_source_source_id"),
        "document_source",
        ["source_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_document_source_source_type"),
        "document_source",
        ["source_type"],
        unique=False,
    )

    # Create document_chunk table with Vector column
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Timestamps (from TimestampMixin)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["document_source.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("source_id", "chunk_index", name="uq_source_chunk_index"),
    )

    # Create indexes for document_chunk
    op.create_index(
        op.f("ix_document_chunk_chunk_id"),
        "document_chunk",
        ["chunk_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_document_chunk_source_id"),
        "document_chunk",
        ["source_id"],
        unique=False,
    )

    # Create HNSW index for vector similarity search (cosine distance)
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "document_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Create GIN index for metadata filtering
    op.create_index(
        "ix_chunk_metadata_gin",
        "document_chunk",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Revert migration - drop document_source and document_chunk tables."""
    # Drop document_chunk indexes and table
    op.drop_index("ix_chunk_metadata_gin", table_name="document_chunk")
    op.drop_index("ix_chunk_embedding_hnsw", table_name="document_chunk")
    op.drop_index(op.f("ix_document_chunk_source_id"), table_name="document_chunk")
    op.drop_index(op.f("ix_document_chunk_chunk_id"), table_name="document_chunk")
    op.drop_table("document_chunk")

    # Drop document_source indexes and table
    op.drop_index(op.f("ix_document_source_source_type"), table_name="document_source")
    op.drop_index(op.f("ix_document_source_source_id"), table_name="document_source")
    op.drop_table("document_source")

    # Note: We don't drop the vector extension as it might be used by other tables
