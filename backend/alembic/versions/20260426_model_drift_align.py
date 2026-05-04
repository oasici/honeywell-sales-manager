"""Eksik tablolar (V2) ve modellerde olup DB'de olmayan kolonlar — idempotent IF NOT EXISTS.

Revision ID: 20260426_model_drift_align
Revises: 20260425_user_customer_pins
Create Date: 2026-04-26

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from app.core.migration_helpers import create_table_if_absent

revision = "20260426_model_drift_align"
down_revision = "20260425_user_customer_pins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names(schema="public"))

    def cols(t: str) -> set[str]:
        if t not in tables:
            return set()
        return {c["name"] for c in insp.get_columns(t, schema="public")}

    # ── Yeni tablolar (V2 sequence telemetry + buyer map) ─────────────────
    if "domain_events" not in tables:
        create_table_if_absent(
            "domain_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("entity_type", sa.String(50), nullable=True),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_domain_events_event_type ON domain_events (event_type)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_domain_events_created_at ON domain_events (created_at)")
        tables.add("domain_events")

    if "sequence_step_runs" not in tables:
        create_table_if_absent(
            "sequence_step_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("enrollment_id", sa.Integer(), nullable=False),
            sa.Column("sequence_id", sa.Integer(), nullable=False),
            sa.Column("step_number", sa.Integer(), nullable=False),
            sa.Column("step_action", sa.String(30), nullable=False),
            sa.Column("variant_key", sa.String(10), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="started"),
            sa.Column("reason_codes", sa.Text(), nullable=True),
            sa.Column("payload_snapshot", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["enrollment_id"], ["sequence_enrollments.id"]),
            sa.ForeignKeyConstraint(["sequence_id"], ["sequences.id"]),
            sa.UniqueConstraint("enrollment_id", "step_number", name="uq_step_run_enrollment_step"),
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_sequence_step_runs_enrollment_id ON sequence_step_runs (enrollment_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_sequence_step_runs_sequence_id ON sequence_step_runs (sequence_id)")
        tables.add("sequence_step_runs")

    if "stakeholders" not in tables:
        create_table_if_absent(
            "stakeholders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("opportunity_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("title", sa.String(200), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("seniority", sa.String(30), nullable=True),
            sa.Column("department_group", sa.String(30), nullable=True),
            sa.Column("buyer_role", sa.String(30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_auto_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_stakeholders_opportunity_id ON stakeholders (opportunity_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_stakeholders_customer_id ON stakeholders (customer_id)")
        tables.add("stakeholders")

    # ── Kolonlar: ADD IF NOT EXISTS (PostgreSQL 9.1+) ─────────────────────
    stmts: list[str] = []

    def add_col(table: str, name: str, ddl: str) -> None:
        if table in tables and name not in cols(table):
            stmts.append(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS {name} {ddl}')

    add_col("approval_rules", "escalation_hours", "INTEGER")
    add_col("approval_rules", "escalation_action", "VARCHAR(30)")

    add_col("customers", "industry", "VARCHAR(100)")
    add_col("customers", "employee_count", "INTEGER")
    add_col("customers", "annual_revenue", "VARCHAR(50)")
    add_col("customers", "website", "VARCHAR(255)")
    add_col("customers", "linkedin_url", "VARCHAR(255)")
    add_col("customers", "enriched_at", "TIMESTAMP WITH TIME ZONE")
    add_col("customers", "territory_id", "INTEGER")
    add_col("customers", "parent_id", "INTEGER")

    add_col("opportunities", "previous_stage", "VARCHAR(30)")
    add_col("opportunities", "previous_close_date", "DATE")
    add_col("opportunities", "previous_amount", "DOUBLE PRECISION")
    add_col("opportunities", "pipeline_id", "INTEGER")
    add_col("opportunities", "territory_id", "INTEGER")

    add_col("sequence_enrollments", "lead_id", "INTEGER")
    add_col("sequence_enrollments", "exit_reason", "VARCHAR(50)")
    add_col("sequence_enrollments", "completed_at", "TIMESTAMP WITH TIME ZONE")

    add_col("sequences", "exit_criteria_json", "TEXT")

    add_col("spare_parts", "min_margin_pct", "DOUBLE PRECISION DEFAULT 0 NOT NULL")

    add_col("transcripts", "summary", "TEXT")
    add_col("transcripts", "action_items_json", "TEXT")
    add_col("transcripts", "sentiment", "VARCHAR(20)")

    add_col("webhook_deliveries", "retry_count", "INTEGER DEFAULT 0 NOT NULL")

    add_col("workflow_rules", "flow_json", "TEXT")

    for sql in stmts:
        op.execute(sa.text(sql))

    # FK'ler (yalnız kolon varsa ve kısıt yoksa — hata yutulur)
    fk_ddl = [
        """
        DO $$ BEGIN
          ALTER TABLE customers
            ADD CONSTRAINT fk_customers_territory_id
            FOREIGN KEY (territory_id) REFERENCES territories(id);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
          ALTER TABLE customers
            ADD CONSTRAINT fk_customers_parent_id
            FOREIGN KEY (parent_id) REFERENCES customers(id);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
          ALTER TABLE opportunities
            ADD CONSTRAINT fk_opportunities_pipeline_id
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
          ALTER TABLE opportunities
            ADD CONSTRAINT fk_opportunities_territory_id
            FOREIGN KEY (territory_id) REFERENCES territories(id);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
          ALTER TABLE sequence_enrollments
            ADD CONSTRAINT fk_sequence_enrollments_lead_id
            FOREIGN KEY (lead_id) REFERENCES leads(id);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """,
    ]
    for ddl in fk_ddl:
        op.execute(sa.text(ddl))


def downgrade() -> None:
    # İdempotent kolon ekleri; geri alma veri kaybı riski — bilinçli no-op
    pass
