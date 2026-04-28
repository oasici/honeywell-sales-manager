"""V12 transformer-based sequence embedding table.

Revision ID: 20260428_v12_transformer_seq
Revises: 20260428_v9_quote_revisions
Create Date: 2026-04-28

Stores the transformer-derived sequence embedding per opportunity in a
dedicated table — see ``app/models/v12_transformer_seq_embedding.py``
for the rationale (V8 BoW + V12 transformer have different lifecycles
so they live in separate tables).

Idempotent.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_v12_transformer_seq"
down_revision = "20260428_v9_quote_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_transformer_seq_embeddings (
            opportunity_id INTEGER PRIMARY KEY
                REFERENCES opportunities(id) ON DELETE CASCADE,
            embedding_json TEXT NOT NULL,
            dim INTEGER NOT NULL,
            version VARCHAR(40) NOT NULL,
            vocab_hash VARCHAR(40) NOT NULL,
            generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opportunity_transformer_seq_embeddings")
