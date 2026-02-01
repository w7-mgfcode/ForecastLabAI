"""rag_dynamic_embedding_dimension

Revision ID: c5d9e1f2g345
Revises: b4c8d9e0f123
Create Date: 2026-02-01 12:49:28.000000

CRITICAL: This migration alters the embedding column dimension.
This migration is deterministic - it changes from 1536 to 1536 (no-op by default).
To change dimensions, create a NEW migration with the desired target dimension.

If changing to a different dimension, existing embeddings will be incompatible
and re-indexing is required.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d9e1f2g345"
down_revision: str | None = "b4c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CRITICAL: Hardcoded dimensions for deterministic, reversible migrations.
# To change dimensions, create a NEW migration with updated values.
PREVIOUS_DIMENSION = 1536  # Dimension before this migration
TARGET_DIMENSION = 1536  # Dimension after this migration (change this for new dimension)


def upgrade() -> None:
    """Apply migration - alter embedding column to target dimension.

    Uses hardcoded TARGET_DIMENSION for deterministic behavior.
    WARNING: Changing dimension requires re-indexing all documents.
    """
    # Drop the HNSW index first (required before altering column type)
    op.drop_index("ix_chunk_embedding_hnsw", table_name="document_chunk")

    # Alter the embedding column type with target dimension
    # Note: This will invalidate any existing embeddings if dimension changes
    op.execute(
        f"ALTER TABLE document_chunk ALTER COLUMN embedding TYPE vector({TARGET_DIMENSION})"
    )

    # Recreate the HNSW index with the target dimension
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
    """Revert migration - restore embedding column to previous dimension.

    Uses hardcoded PREVIOUS_DIMENSION for deterministic rollback.
    WARNING: This will invalidate any embeddings that were generated
    with the target dimension.
    """
    # Drop the HNSW index
    op.drop_index("ix_chunk_embedding_hnsw", table_name="document_chunk")

    # Restore to previous dimension
    op.execute(
        f"ALTER TABLE document_chunk ALTER COLUMN embedding TYPE vector({PREVIOUS_DIMENSION})"
    )

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
