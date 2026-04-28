"""V9 NL search: transcript + email embeddings

Revision ID: 20260428_v9_nl_search
Revises: 20260428_v9_board_ux
Create Date: 2026-04-28

Stores V8 text-embedder output for transcripts and email_requests so
``/v9/search/semantic`` can do cosine over them. Same shape as
``opportunity_text_embeddings`` from V8.

Idempotent.
"""

from alembic import op


revision = "20260428_v9_nl_search"
down_revision = "20260428_v9_board_ux"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_embeddings (
            transcript_id INTEGER PRIMARY KEY REFERENCES transcripts(id) ON DELETE CASCADE,
            embedding_json TEXT NOT NULL,
            dim INTEGER NOT NULL,
            version VARCHAR(40) NOT NULL,
            vocab_hash VARCHAR(40) NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_embeddings (
            email_request_id INTEGER PRIMARY KEY REFERENCES email_requests(id) ON DELETE CASCADE,
            embedding_json TEXT NOT NULL,
            dim INTEGER NOT NULL,
            version VARCHAR(40) NOT NULL,
            vocab_hash VARCHAR(40) NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_embeddings")
    op.execute("DROP TABLE IF EXISTS transcript_embeddings")
