"""V8 sequence text embedding table

Revision ID: 20260427_v8_text_embedding
Revises: 20260427_v7_tenant_boundary
Create Date: 2026-04-27

Adds ``opportunity_text_embeddings`` — token-bigram BoW vectors of
the V6 sequence tokens. Slots in alongside the V5
``opportunity_embeddings`` (structured) so deal similarity becomes
a 3-component blend (structured + LCS + text).

Idempotent.
"""

from alembic import op


revision = "20260427_v8_text_embedding"
down_revision = "20260427_v7_tenant_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_text_embeddings (
            opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
            embedding_json TEXT NOT NULL,
            dim INTEGER NOT NULL,
            version VARCHAR(40) NOT NULL,
            vocab_hash VARCHAR(40) NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opportunity_text_embeddings")
