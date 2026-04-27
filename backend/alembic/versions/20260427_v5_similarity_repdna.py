"""V5 deal similarity + rep DNA profiles

Revision ID: 20260427_v5_similarity_repdna
Revises: 20260427_v5_playbook_expansion
Create Date: 2026-04-27

`opportunity_embeddings` stores a structured-feature vector (no LLM
yet) per opportunity; `deal_similarity_links` is the precomputed
top-K cosine neighbour index. `rep_dna_profiles` is the cluster
assignment + strengths/gaps narrative for each rep.

Vector type: we use a TEXT JSON-encoded float array rather than
``vector(...)`` from pgvector to avoid forcing the pgvector extension
on Render free-tier. Cosine sim is computed in Python; switch to
pgvector when traffic justifies it.
"""

from alembic import op


revision = "20260427_v5_similarity_repdna"
down_revision = "20260427_v5_playbook_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_embeddings (
            opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
            embedding_json TEXT NOT NULL,
            dim INTEGER NOT NULL,
            version VARCHAR(40) NOT NULL DEFAULT 'v5-structured-1',
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_similarity_links (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            similar_opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            similarity_score DOUBLE PRECISION NOT NULL,
            similarity_reason_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (opportunity_id, similar_opportunity_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_sim_links_opp_score "
        "ON deal_similarity_links (opportunity_id, similarity_score DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rep_dna_profiles (
            rep_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            cluster_label VARCHAR(40) NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}',
            strengths_json TEXT NOT NULL DEFAULT '[]',
            gaps_json TEXT NOT NULL DEFAULT '[]',
            sample_period_start DATE,
            sample_period_end DATE,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rep_dna_profiles")
    op.execute("DROP TABLE IF EXISTS deal_similarity_links")
    op.execute("DROP TABLE IF EXISTS opportunity_embeddings")
