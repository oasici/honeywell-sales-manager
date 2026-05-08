"""v1.13 plan-adoption primitives.

Creates six new tables that close the integratable gaps from the
2026-05-07 plan-adoption analysis:

* ``decision_nodes`` / ``decision_edges`` (S-C decision graph extension)
* ``ai_attribute_definitions`` / ``ai_attribute_values`` (S-H AI attributes)
* ``relationship_edges`` / ``relationship_scores`` (S-B relationship graph)

All tables are tenant-scoped (``tenant_id`` + index) and use idempotent
``IF NOT EXISTS`` so reruns are safe in CI and bootstrap regen.

Revision ID: 20260508_v113_plan_adopt
Revises: 20260507_drop_dup_uq_idx_p2
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op


revision = "20260508_v113_plan_adopt"
down_revision = "20260507_drop_dup_uq_idx_p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── decision_nodes ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_nodes (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            node_type VARCHAR(40) NOT NULL,
            label VARCHAR(200) NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'not_started',
            owner_stakeholder_id INTEGER NULL REFERENCES stakeholders(id),
            blocker_reason TEXT NULL,
            last_progress_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_decision_nodes_opp_type UNIQUE (opportunity_id, node_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_nodes_tenant_id ON decision_nodes (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_nodes_opportunity_id ON decision_nodes (opportunity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_nodes_state ON decision_nodes (state)"
    )

    # ── decision_edges ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_edges (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            from_node_id INTEGER NOT NULL REFERENCES decision_nodes(id),
            to_node_id INTEGER NOT NULL REFERENCES decision_nodes(id),
            edge_type VARCHAR(20) NOT NULL DEFAULT 'sequential',
            is_satisfied BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_decision_edges_triple UNIQUE (opportunity_id, from_node_id, to_node_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_edges_tenant_id ON decision_edges (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_edges_opportunity_id ON decision_edges (opportunity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_edges_from_node_id ON decision_edges (from_node_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_edges_to_node_id ON decision_edges (to_node_id)"
    )

    # ── ai_attribute_definitions ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_attribute_definitions (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            entity_type VARCHAR(30) NOT NULL,
            key VARCHAR(80) NOT NULL,
            label VARCHAR(200) NOT NULL,
            description TEXT NULL,
            data_type VARCHAR(20) NOT NULL DEFAULT 'text',
            prompt_template TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            refresh_hours INTEGER NOT NULL DEFAULT 24,
            created_by INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ai_attr_def_key UNIQUE (tenant_id, entity_type, key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_attr_def_tenant_id ON ai_attribute_definitions (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_attr_def_entity_active ON ai_attribute_definitions (entity_type, is_active)"
    )

    # ── ai_attribute_values ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_attribute_values (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            definition_id INTEGER NOT NULL REFERENCES ai_attribute_definitions(id),
            entity_type VARCHAR(30) NOT NULL,
            entity_id INTEGER NOT NULL,
            value_text TEXT NULL,
            value_number DOUBLE PRECISION NULL,
            value_bool BOOLEAN NULL,
            value_list_json TEXT NULL,
            confidence DOUBLE PRECISION NULL,
            model_name VARCHAR(80) NULL,
            trace_id VARCHAR(64) NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ai_attr_value_target UNIQUE (definition_id, entity_type, entity_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_attr_value_tenant_id ON ai_attribute_values (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_attr_value_definition_id ON ai_attribute_values (definition_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_attr_value_entity ON ai_attribute_values (entity_type, entity_id)"
    )

    # ── relationship_edges ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_edges (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            from_kind VARCHAR(20) NOT NULL,
            from_id INTEGER NOT NULL,
            to_kind VARCHAR(20) NOT NULL,
            to_id INTEGER NOT NULL,
            relation_type VARCHAR(40) NULL,
            strength DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            interaction_count INTEGER NOT NULL DEFAULT 0,
            last_interaction_at TIMESTAMPTZ NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'derived',
            metadata_json TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rel_edge_endpoints UNIQUE (from_kind, from_id, to_kind, to_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_edge_tenant_id ON relationship_edges (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_edge_from ON relationship_edges (from_kind, from_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_edge_to ON relationship_edges (to_kind, to_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_edge_strength ON relationship_edges (strength)"
    )

    # ── relationship_scores ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_scores (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NULL,
            target_kind VARCHAR(20) NOT NULL,
            target_id INTEGER NOT NULL,
            edge_count INTEGER NOT NULL DEFAULT 0,
            strongest_strength DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            avg_strength DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            coverage_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            strongest_edge_id INTEGER NULL REFERENCES relationship_edges(id),
            snapshot_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rel_score_target UNIQUE (target_kind, target_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_score_tenant_id ON relationship_scores (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rel_score_kind ON relationship_scores (target_kind)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS relationship_scores CASCADE")
    op.execute("DROP TABLE IF EXISTS relationship_edges CASCADE")
    op.execute("DROP TABLE IF EXISTS ai_attribute_values CASCADE")
    op.execute("DROP TABLE IF EXISTS ai_attribute_definitions CASCADE")
    op.execute("DROP TABLE IF EXISTS decision_edges CASCADE")
    op.execute("DROP TABLE IF EXISTS decision_nodes CASCADE")
