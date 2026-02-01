"""rag_dynamic_embedding_dimension

Revision ID: c5d9e1f2g345
Revises: b4c8d9e0f123
Create Date: 2026-02-01 12:49:28.000000

CRITICAL: This migration alters the embedding column dimension.
If changing from 1536 to a different dimension, existing embeddings
will be incompatible and re-indexing is required.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d9e1f2g345"
down_revision: str | None = "b4c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - alter embedding column to configurable dimension.

    Reads RAG_EMBEDDING_DIMENSION from environment (default: 1536).
    WARNING: Changing dimension requires re-indexing all documents.
    """
    # Get dimension from environment or use default
    dimension = int(os.environ.get("RAG_EMBEDDING_DIMENSION", "1536"))

    # Drop the HNSW index first (required before altering column type)
    op.drop_index("ix_chunk_embedding_hnsw", table_name="document_chunk")

    # Alter the embedding column type with new dimension
    # Note: This will invalidate any existing embeddings if dimension changes
    op.execute(f"ALTER TABLE document_chunk ALTER COLUMN embedding TYPE vector({dimension})")

    # Recreate the HNSW index with the new dimension
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "document_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Revert migration - restore embedding column to 1536 dimensions.

    WARNING: This will invalidate any embeddings that were generated
    with a different dimension.
    """
    # Drop the HNSW index
    op.drop_index("ix_chunk_embedding_hnsw", table_name="document_chunk")

    # Restore to original 1536 dimension
    op.execute("ALTER TABLE document_chunk ALTER COLUMN embedding TYPE vector(1536)")

    # Recreate the HNSW index
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "document_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
