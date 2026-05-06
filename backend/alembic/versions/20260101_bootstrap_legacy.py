"""Bootstrap legacy tables that pre-date alembic adoption

Revision ID: 20260101_bootstrap_legacy
Revises:
Create Date: 2026-05-04

The tables below were created by ``Base.metadata.create_all()`` at
first boot of the production database in 2024-2025, before alembic
was wired in. No migration in the chain creates them — every
subsequent migration ALTERs them on the assumption they exist.

Round-4 audit (R4-DB-1, R4-DB-2) flagged this as a fragility: the CI
"schema-drift check" step needs a full ``alembic upgrade head`` from
an empty schema, which would otherwise fail at the first ``op.add_
column("customers", ...)`` call.

This migration is the head of the chain (``down_revision = None``);
the previous root (20260413_add_customer_parent_id) now depends on it.

The DDL is auto-generated from ``Base.metadata`` at HEAD via
``backend/scripts/regenerate_bootstrap_migration.py``. To regenerate
after a model change, re-run that script — or just author a new
incremental migration; the bootstrap is now a snapshot we don't edit
by hand.

Idempotent in both directions:
  - upgrade() uses CREATE TABLE/INDEX IF NOT EXISTS so it's a no-op
    on existing prod and on re-runs.
  - downgrade() is a no-op (refusing to drop production data).
"""

from alembic import op


revision = "20260101_bootstrap_legacy"
down_revision = None
branch_labels = None
depends_on = None


# Auto-generated from Base.metadata; do not edit by hand.
# Regenerate via backend/scripts/regenerate_bootstrap_migration.py.
_BOOTSTRAP_DDL = r"""
-- Bootstrap DDL — auto-generated from Base.metadata at HEAD

CREATE TABLE IF NOT EXISTS dna_patterns (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	pattern_name VARCHAR(200) NOT NULL, 
	pattern_type VARCHAR(40) NOT NULL, 
	sequence_template_json TEXT NOT NULL, 
	support_count INTEGER NOT NULL, 
	win_rate FLOAT NOT NULL, 
	baseline_win_rate FLOAT NOT NULL, 
	lift_vs_baseline FLOAT NOT NULL, 
	confidence_score FLOAT NOT NULL, 
	smoothed_win_rate FLOAT, 
	uplift_score FLOAT, 
	ci_low FLOAT, 
	ci_high FLOAT, 
	is_promotable BOOLEAN NOT NULL, 
	last_trained_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS domain_events (
	id SERIAL NOT NULL, 
	event_type VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id INTEGER, 
	payload_json TEXT, 
	actor_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS feature_usage (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	feature_name VARCHAR(100) NOT NULL, 
	action VARCHAR(50) NOT NULL, 
	metadata_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS federated_benchmarks (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	benchmark_key VARCHAR(120) NOT NULL, 
	snapshot_date DATE NOT NULL, 
	metric_name VARCHAR(60) NOT NULL, 
	metric_value FLOAT, 
	sample_bucket VARCHAR(40), 
	privacy_level VARCHAR(20) NOT NULL, 
	tenant_count INTEGER NOT NULL, 
	sample_size INTEGER NOT NULL, 
	suppressed BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS field_permissions (
	id SERIAL NOT NULL, 
	role VARCHAR(30) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	field_name VARCHAR(100) NOT NULL, 
	access_level VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_role_entity_field UNIQUE (role, entity_type, field_name)
);

CREATE TABLE IF NOT EXISTS keyword_packs (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	keywords_json TEXT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS lead_scoring_configs (
	id SERIAL NOT NULL, 
	factor_name VARCHAR(50) NOT NULL, 
	weight INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	description VARCHAR(200), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS network_anomalies (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	metric_name VARCHAR(60) NOT NULL, 
	expected_value FLOAT NOT NULL, 
	actual_value FLOAT NOT NULL, 
	z_score FLOAT NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	explanation_json TEXT, 
	detected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS network_patterns (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	pattern_type VARCHAR(40) NOT NULL, 
	pattern_json TEXT NOT NULL, 
	performance_metric VARCHAR(40) NOT NULL, 
	metric_value FLOAT NOT NULL, 
	sample_size INTEGER NOT NULL, 
	confidence_score FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS network_segments (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	definition_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS objection_patterns (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	objection_type VARCHAR(40) NOT NULL, 
	recommended_resolution_json TEXT NOT NULL, 
	success_rate FLOAT NOT NULL, 
	sample_size INTEGER NOT NULL, 
	last_trained_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (segment_key, objection_type)
);

CREATE TABLE IF NOT EXISTS pipeline_snapshots (
	id SERIAL NOT NULL, 
	snapshot_date DATE NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	opportunity_count INTEGER NOT NULL, 
	total_amount FLOAT NOT NULL, 
	weighted_amount FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS product_bundles (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	items_json TEXT NOT NULL, 
	bundle_price FLOAT, 
	discount_pct FLOAT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS retention_policies (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	retention_days INTEGER NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS segment_benchmarks_daily (
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	snapshot_date DATE NOT NULL, 
	win_rate_90d FLOAT, 
	followup_median_days FLOAT, 
	avg_discount_pct FLOAT, 
	avg_stakeholder_count FLOAT, 
	objection_rate_14d FLOAT, 
	sample_size INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (segment_key, snapshot_date)
);

CREATE TABLE IF NOT EXISTS settings (
	id SERIAL NOT NULL, 
	key VARCHAR(100) NOT NULL, 
	value TEXT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spare_parts (
	id SERIAL NOT NULL, 
	honeywell_code VARCHAR(500) NOT NULL, 
	name_en TEXT, 
	name_tr TEXT, 
	description_en TEXT, 
	description_tr TEXT, 
	category VARCHAR(200), 
	subcategory VARCHAR(200), 
	keywords_json TEXT, 
	aliases_json TEXT, 
	info TEXT, 
	model_number VARCHAR(200), 
	transfer_price FLOAT, 
	supplier_price FLOAT, 
	price_currency VARCHAR(10), 
	min_margin_pct FLOAT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS stage_configs (
	id SERIAL NOT NULL, 
	stage_name VARCHAR(30) NOT NULL, 
	label VARCHAR(100) NOT NULL, 
	probability_pct FLOAT NOT NULL, 
	rotting_threshold_days INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	wip_limit INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (stage_name)
);

CREATE TABLE IF NOT EXISTS stage_requirements (
	id SERIAL NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	required_fields_json TEXT NOT NULL, 
	validation_rules_json TEXT, 
	coaching_tips_json TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (stage)
);

CREATE TABLE IF NOT EXISTS tenants (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	region VARCHAR(60), 
	plan_tier VARCHAR(40) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	full_name VARCHAR(255) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	email_setup_completed BOOLEAN NOT NULL, 
	password_change_required BOOLEAN NOT NULL, 
	manager_id INTEGER, 
	tenant_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(manager_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS v4_sales_events_shadow (
	id SERIAL NOT NULL, 
	source_ref VARCHAR(180) NOT NULL, 
	provenance VARCHAR(40) NOT NULL, 
	account_id INTEGER, 
	opportunity_id INTEGER, 
	contact_id INTEGER, 
	event_type VARCHAR(120) NOT NULL, 
	event_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor_type VARCHAR(20) NOT NULL, 
	actor_id INTEGER, 
	channel VARCHAR(30) NOT NULL, 
	direction VARCHAR(20) NOT NULL, 
	payload_json TEXT NOT NULL, 
	synced_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS achievements (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	achievement_type VARCHAR(50) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT, 
	earned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	metadata_json TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS api_keys (
	id SERIAL NOT NULL, 
	key_hash VARCHAR(128) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	user_id INTEGER NOT NULL, 
	scopes_json TEXT, 
	rate_limit INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_used_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS approval_rules (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	condition_type VARCHAR(30) NOT NULL, 
	threshold_value FLOAT NOT NULL, 
	threshold_operator VARCHAR(10) NOT NULL, 
	approver_role VARCHAR(30), 
	approver_user_id INTEGER, 
	chain_mode VARCHAR(20) NOT NULL, 
	priority INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	delegate_to INTEGER, 
	delegate_until TIMESTAMP WITH TIME ZONE, 
	escalation_hours INTEGER, 
	escalation_action VARCHAR(30), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(approver_user_id) REFERENCES users (id), 
	FOREIGN KEY(delegate_to) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	tenant_id INTEGER, 
	action VARCHAR(50) NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	changes TEXT, 
	ip_address VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS auto_response_rules (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	trigger_keyword VARCHAR(200) NOT NULL, 
	response_text TEXT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	priority INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS breach_notifications (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	breach_type VARCHAR(50) NOT NULL, 
	description TEXT, 
	affected_customers_json TEXT, 
	severity VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	notified_at TIMESTAMP WITH TIME ZONE, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS calendar_connections (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	calendar_id VARCHAR(200), 
	oauth_token_encrypted TEXT, 
	refresh_token_encrypted TEXT, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	is_active BOOLEAN NOT NULL, 
	last_sync_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_calendar_connections_user_provider UNIQUE (user_id, provider), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaigns (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	description TEXT, 
	start_date TIMESTAMP WITH TIME ZONE, 
	end_date TIMESTAMP WITH TIME ZONE, 
	budget FLOAT, 
	actual_cost FLOAT NOT NULL, 
	expected_revenue FLOAT, 
	actual_revenue FLOAT NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	visitor_id VARCHAR(64) NOT NULL, 
	assigned_agent_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	metadata_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assigned_agent_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS coaching_plans (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	manager_id INTEGER NOT NULL, 
	goals_json TEXT NOT NULL, 
	weeks INTEGER NOT NULL, 
	start_date DATE, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(manager_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS coaching_snapshots (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	score INTEGER NOT NULL, 
	indicators_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS comments (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	entity_type VARCHAR(30) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	mentions_json TEXT, 
	parent_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(parent_id) REFERENCES comments (id)
);

CREATE TABLE IF NOT EXISTS crm_connections (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	provider VARCHAR(40) NOT NULL, 
	label VARCHAR(120) NOT NULL, 
	base_url VARCHAR(400), 
	oauth_token_encrypted TEXT, 
	refresh_token_encrypted TEXT, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	sync_state VARCHAR(40) NOT NULL, 
	last_sync_at TIMESTAMP WITH TIME ZONE, 
	is_active BOOLEAN NOT NULL, 
	credentials_json TEXT, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS custom_fields (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	field_name VARCHAR(100) NOT NULL, 
	field_type VARCHAR(20) NOT NULL, 
	options_json TEXT, 
	is_required BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_custom_field_entity_name UNIQUE (entity_type, field_name), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS dashboard_configs (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	widgets_json TEXT NOT NULL, 
	is_default BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS dead_letter_events (
	id SERIAL NOT NULL, 
	event_type VARCHAR(80) NOT NULL, 
	handler_name VARCHAR(120) NOT NULL, 
	payload_json TEXT NOT NULL, 
	error_message TEXT, 
	error_traceback TEXT, 
	attempt_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	replayed_at TIMESTAMP WITH TIME ZONE, 
	replayed_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(replayed_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS dna_recommendations (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	segment_key VARCHAR(80) NOT NULL, 
	stage_scope VARCHAR(40), 
	recommendation_json TEXT NOT NULL, 
	source_pattern_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_pattern_id) REFERENCES dna_patterns (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS email_templates (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	subject VARCHAR(500) NOT NULL, 
	body_html TEXT NOT NULL, 
	variables_json TEXT, 
	category VARCHAR(50), 
	is_shared BOOLEAN NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS lead_assignment_rules (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	criteria_json TEXT NOT NULL, 
	assign_to_user_id INTEGER, 
	assign_mode VARCHAR(20) NOT NULL, 
	priority INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assign_to_user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS meeting_links (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	slug VARCHAR(50) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	availability_json TEXT, 
	calendar_provider VARCHAR(20), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS notifications (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	message TEXT, 
	is_read BOOLEAN NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS pipelines (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(100) NOT NULL, 
	stages_json TEXT, 
	is_default BOOLEAN NOT NULL, 
	description TEXT, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS playbooks (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	trigger_conditions_json TEXT NOT NULL, 
	steps_json TEXT NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS price_entries (
	id SERIAL NOT NULL, 
	spare_part_id INTEGER NOT NULL, 
	list_price FLOAT NOT NULL, 
	discount_pct FLOAT NOT NULL, 
	net_price FLOAT NOT NULL, 
	currency VARCHAR(10) NOT NULL, 
	valid_from DATE, 
	valid_until DATE, 
	price_list_version VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(spare_part_id) REFERENCES spare_parts (id)
);

CREATE TABLE IF NOT EXISTS product_rules (
	id SERIAL NOT NULL, 
	spare_part_id INTEGER, 
	category VARCHAR(100), 
	rule_type VARCHAR(30) NOT NULL, 
	condition_json TEXT NOT NULL, 
	action_json TEXT NOT NULL, 
	priority INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(spare_part_id) REFERENCES spare_parts (id)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	endpoint TEXT NOT NULL, 
	keys_json TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS rep_dna_profiles (
	rep_id INTEGER NOT NULL, 
	cluster_label VARCHAR(40) NOT NULL, 
	profile_json TEXT NOT NULL, 
	strengths_json TEXT NOT NULL, 
	gaps_json TEXT NOT NULL, 
	sample_period_start DATE, 
	sample_period_end DATE, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (rep_id), 
	FOREIGN KEY(rep_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rep_features_daily (
	rep_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	avg_followup_hours FLOAT, 
	stakeholder_coverage_rate FLOAT, 
	win_rate_adj FLOAT, 
	objection_recovery_rate FLOAT, 
	sequence_adherence_rate FLOAT, 
	stage_slippage_rate FLOAT, 
	discount_dependence FLOAT, 
	sample_deals INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (rep_id, snapshot_date), 
	FOREIGN KEY(rep_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS report_folders (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	parent_id INTEGER, 
	owner_id INTEGER NOT NULL, 
	is_shared BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES report_folders (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS saved_views (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	route VARCHAR(255) NOT NULL, 
	query_json TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS segments (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	rules_json TEXT NOT NULL, 
	customer_count INTEGER NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS selling_guides (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	steps_json TEXT, 
	product_rules_json TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS sequences (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	steps_json TEXT NOT NULL, 
	auto_enroll_rules_json TEXT, 
	exit_criteria_json TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS sharing_rules (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	criteria_json TEXT NOT NULL, 
	share_with_role VARCHAR(30), 
	share_with_user_id INTEGER, 
	access_level VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(share_with_user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS signature_requests (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	document_type VARCHAR(20) NOT NULL, 
	document_id INTEGER NOT NULL, 
	signer_email VARCHAR(255) NOT NULL, 
	signer_name VARCHAR(200), 
	status VARCHAR(20) NOT NULL, 
	token VARCHAR(64) NOT NULL, 
	signed_at TIMESTAMP WITH TIME ZONE, 
	viewed_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	signature_data TEXT, 
	ip_address VARCHAR(45), 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS territories (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(100) NOT NULL, 
	parent_id INTEGER, 
	description TEXT, 
	region VARCHAR(100), 
	rules_json TEXT, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES territories (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	jti VARCHAR(64) NOT NULL, 
	device_info VARCHAR(200), 
	ip_address VARCHAR(45), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (jti)
);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	event_types TEXT NOT NULL, 
	secret VARCHAR(255), 
	is_active BOOLEAN NOT NULL, 
	created_by INTEGER NOT NULL, 
	last_triggered_at TIMESTAMP WITH TIME ZONE, 
	failure_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS workflow_rules (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	trigger_event VARCHAR(100) NOT NULL, 
	conditions_json TEXT, 
	actions_json TEXT NOT NULL, 
	flow_json TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS approval_requests (
	id SERIAL NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	rule_id INTEGER, 
	level INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	requested_by INTEGER NOT NULL, 
	assigned_to INTEGER, 
	decided_by INTEGER, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	comments TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(rule_id) REFERENCES approval_rules (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(assigned_to) REFERENCES users (id), 
	FOREIGN KEY(decided_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	session_id INTEGER NOT NULL, 
	sender_type VARCHAR(20) NOT NULL, 
	sender_id VARCHAR(100), 
	content TEXT NOT NULL, 
	message_type VARCHAR(20) NOT NULL, 
	is_read BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id)
);

CREATE TABLE IF NOT EXISTS crm_field_mappings (
	id SERIAL NOT NULL, 
	connection_id INTEGER NOT NULL, 
	entity_type VARCHAR(40) NOT NULL, 
	internal_field VARCHAR(120) NOT NULL, 
	external_field VARCHAR(120) NOT NULL, 
	direction VARCHAR(20) NOT NULL, 
	transform_rule_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connection_id) REFERENCES crm_connections (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crm_record_links (
	id SERIAL NOT NULL, 
	connection_id INTEGER NOT NULL, 
	internal_entity_type VARCHAR(40) NOT NULL, 
	internal_id INTEGER NOT NULL, 
	external_id VARCHAR(120) NOT NULL, 
	last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	hash_signature VARCHAR(64), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_crm_record_links UNIQUE (connection_id, internal_entity_type, internal_id), 
	FOREIGN KEY(connection_id) REFERENCES crm_connections (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crm_sync_jobs (
	id SERIAL NOT NULL, 
	connection_id INTEGER NOT NULL, 
	entity_type VARCHAR(40) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	items_pulled INTEGER NOT NULL, 
	items_pushed INTEGER NOT NULL, 
	items_failed INTEGER NOT NULL, 
	error_log_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connection_id) REFERENCES crm_connections (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS custom_field_values (
	id SERIAL NOT NULL, 
	custom_field_id INTEGER NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	value_text TEXT, 
	value_number FLOAT, 
	value_date DATE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(custom_field_id) REFERENCES custom_fields (id)
);

CREATE TABLE IF NOT EXISTS customers (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	company VARCHAR(255), 
	email VARCHAR(255) NOT NULL, 
	phone VARCHAR(50), 
	address TEXT, 
	tax_id VARCHAR(50), 
	preferred_lang VARCHAR(5) NOT NULL, 
	tenant_id INTEGER, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	kvkk_consent BOOLEAN NOT NULL, 
	kvkk_consent_date TIMESTAMP WITH TIME ZONE, 
	kvkk_consent_method VARCHAR(50), 
	data_retention_until TIMESTAMP WITH TIME ZONE, 
	data_processing_purpose VARCHAR(200), 
	deletion_requested_at TIMESTAMP WITH TIME ZONE, 
	data_classification VARCHAR(20), 
	industry VARCHAR(100), 
	employee_count INTEGER, 
	annual_revenue VARCHAR(50), 
	website VARCHAR(255), 
	linkedin_url VARCHAR(255), 
	enriched_at TIMESTAMP WITH TIME ZONE, 
	territory_id INTEGER, 
	parent_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(territory_id) REFERENCES territories (id), 
	FOREIGN KEY(parent_id) REFERENCES customers (id)
);

CREATE TABLE IF NOT EXISTS playbook_performance (
	id SERIAL NOT NULL, 
	playbook_id INTEGER NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	usage_count INTEGER NOT NULL, 
	completion_rate FLOAT NOT NULL, 
	won_rate FLOAT NOT NULL, 
	lift_vs_control FLOAT NOT NULL, 
	sample_size INTEGER NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (playbook_id, period_start, period_end), 
	FOREIGN KEY(playbook_id) REFERENCES playbooks (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS playbook_steps (
	id SERIAL NOT NULL, 
	playbook_id INTEGER NOT NULL, 
	step_no INTEGER NOT NULL, 
	trigger_condition_json TEXT NOT NULL, 
	recommended_action_json TEXT NOT NULL, 
	expected_window_hours INTEGER NOT NULL, 
	success_metric VARCHAR(60), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (playbook_id, step_no), 
	FOREIGN KEY(playbook_id) REFERENCES playbooks (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS price_tiers (
	id SERIAL NOT NULL, 
	price_entry_id INTEGER NOT NULL, 
	min_qty INTEGER NOT NULL, 
	max_qty INTEGER, 
	unit_price FLOAT NOT NULL, 
	discount_pct FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(price_entry_id) REFERENCES price_entries (id)
);

CREATE TABLE IF NOT EXISTS report_templates (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	entity_type VARCHAR(30) NOT NULL, 
	columns_json TEXT NOT NULL, 
	filters_json TEXT, 
	group_by VARCHAR(100), 
	sort_by VARCHAR(100), 
	sort_order VARCHAR(4) NOT NULL, 
	chart_type VARCHAR(20), 
	is_system BOOLEAN NOT NULL, 
	created_by INTEGER, 
	is_public BOOLEAN NOT NULL, 
	folder_id INTEGER, 
	email_schedule VARCHAR(20), 
	email_recipients TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(folder_id) REFERENCES report_folders (id)
);

CREATE TABLE IF NOT EXISTS territory_assignments (
	id SERIAL NOT NULL, 
	territory_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_territory_user UNIQUE (territory_id, user_id), 
	FOREIGN KEY(territory_id) REFERENCES territories (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	subscription_id INTEGER NOT NULL, 
	event_type VARCHAR(50) NOT NULL, 
	payload_json TEXT NOT NULL, 
	status_code INTEGER, 
	response_body TEXT, 
	retry_count INTEGER NOT NULL, 
	delivered_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subscription_id) REFERENCES webhook_subscriptions (id)
);

CREATE TABLE IF NOT EXISTS account_enrichments (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	pipeline_open_amount FLOAT NOT NULL, 
	closed_won_revenue FLOAT NOT NULL, 
	active_deal_count INTEGER NOT NULL, 
	won_deal_count INTEGER NOT NULL, 
	lost_deal_count INTEGER NOT NULL, 
	total_deal_count INTEGER NOT NULL, 
	risk_index FLOAT NOT NULL, 
	engagement_score FLOAT NOT NULL, 
	last_touch_at TIMESTAMP WITH TIME ZONE, 
	computed_at TIMESTAMP WITH TIME ZONE, 
	extra JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS account_features_daily (
	account_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	open_opportunity_count INTEGER NOT NULL, 
	total_open_pipeline FLOAT NOT NULL, 
	avg_deal_health FLOAT, 
	last_touch_days INTEGER NOT NULL, 
	avg_momentum FLOAT, 
	stakeholder_coverage_avg FLOAT, 
	buyer_engagement_score FLOAT, 
	objection_density_30d FLOAT NOT NULL, 
	expansion_signal_score FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (account_id, snapshot_date), 
	FOREIGN KEY(account_id) REFERENCES customers (id)
);

CREATE TABLE IF NOT EXISTS account_teams (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	role VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_account_team_customer_user UNIQUE (customer_id, user_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS contacts (
	id SERIAL NOT NULL, 
	account_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	title VARCHAR(160), 
	department VARCHAR(120), 
	email VARCHAR(255), 
	phone VARCHAR(60), 
	seniority_score INTEGER NOT NULL, 
	is_decision_maker BOOLEAN NOT NULL, 
	linkedin_url VARCHAR(400), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS customer_pricing (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	spare_part_id INTEGER NOT NULL, 
	contracted_price FLOAT NOT NULL, 
	currency VARCHAR(10) NOT NULL, 
	discount_pct FLOAT NOT NULL, 
	valid_from TIMESTAMP WITH TIME ZONE, 
	valid_until TIMESTAMP WITH TIME ZONE, 
	notes TEXT, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_customer_part_pricing UNIQUE (customer_id, spare_part_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(spare_part_id) REFERENCES spare_parts (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS opportunities (
	id SERIAL NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	amount FLOAT, 
	currency VARCHAR(10) NOT NULL, 
	close_date DATE, 
	owner_id INTEGER NOT NULL, 
	customer_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	forecast_category VARCHAR(20), 
	probability FLOAT, 
	loss_reason VARCHAR(200), 
	source VARCHAR(30), 
	previous_stage VARCHAR(30), 
	previous_close_date DATE, 
	previous_amount FLOAT, 
	pipeline_id INTEGER, 
	territory_id INTEGER, 
	tenant_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(pipeline_id) REFERENCES pipelines (id), 
	FOREIGN KEY(territory_id) REFERENCES territories (id)
);

CREATE TABLE IF NOT EXISTS user_customer_pins (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	pinned_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_customer_pins_user_customer UNIQUE (user_id, customer_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS action_experiments (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	variant_a_json TEXT NOT NULL, 
	variant_b_json TEXT NOT NULL, 
	selected_variant VARCHAR(1), 
	outcome VARCHAR(20), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS activity_logs (
	id SERIAL NOT NULL, 
	activity_type VARCHAR(30) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	user_id INTEGER, 
	summary VARCHAR(500) NOT NULL, 
	duration_minutes INTEGER, 
	outcome VARCHAR(50), 
	attendees_json TEXT, 
	agenda TEXT, 
	metadata_json TEXT, 
	source_ref VARCHAR(120), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS buyer_state_history (
	opportunity_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	confidence FLOAT NOT NULL, 
	drivers_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (opportunity_id, snapshot_date), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS competitor_mentions (
	id SERIAL NOT NULL, 
	competitor_name VARCHAR(200) NOT NULL, 
	source_entity_type VARCHAR(30) NOT NULL, 
	source_entity_id INTEGER NOT NULL, 
	opportunity_id INTEGER, 
	context_snippet TEXT, 
	sentiment VARCHAR(20), 
	detected_by VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS deal_replay_deltas (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	from_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	to_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	change_type VARCHAR(40) NOT NULL, 
	change_summary TEXT, 
	impact_score FLOAT, 
	drivers_json TEXT, 
	counterfactual_hint VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deal_rooms (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	external_token VARCHAR(64) NOT NULL, 
	shared_items_json TEXT, 
	mutual_action_plan_json TEXT, 
	welcome_message TEXT, 
	is_active BOOLEAN NOT NULL, 
	last_buyer_activity_at TIMESTAMP WITH TIME ZONE, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	UNIQUE (external_token), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS deal_similarity_links (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	similar_opportunity_id INTEGER NOT NULL, 
	similarity_score FLOAT NOT NULL, 
	similarity_reason_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (opportunity_id, similar_opportunity_id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE, 
	FOREIGN KEY(similar_opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS decision_gaps (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	gap_type VARCHAR(50) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	is_resolved BOOLEAN NOT NULL, 
	expected_roles_json TEXT, 
	observed_roles_json TEXT, 
	recommended_actions_json TEXT, 
	drivers_json TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS email_requests (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	customer_id INTEGER, 
	message_id VARCHAR(255) NOT NULL, 
	from_address VARCHAR(255) NOT NULL, 
	subject VARCHAR(500), 
	body_text TEXT, 
	body_html TEXT, 
	language VARCHAR(5), 
	received_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	parsed_data TEXT, 
	error_message TEXT, 
	category VARCHAR(50), 
	category_confidence FLOAT, 
	price_sensitivity BOOLEAN, 
	sentiment VARCHAR(20), 
	sentiment_score FLOAT, 
	is_duplicate BOOLEAN, 
	duplicate_of_id INTEGER, 
	priority VARCHAR(20), 
	triage_reason TEXT, 
	data_classification VARCHAR(20), 
	is_read BOOLEAN NOT NULL, 
	last_parsed_at TIMESTAMP WITH TIME ZONE, 
	opportunity_id INTEGER, 
	thread_id VARCHAR(255), 
	in_reply_to VARCHAR(255), 
	review_status VARCHAR(20), 
	assigned_to INTEGER, 
	reviewed_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(assigned_to) REFERENCES users (id), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS forecast_adjustments (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	adjusted_by INTEGER NOT NULL, 
	original_amount FLOAT NOT NULL, 
	adjusted_amount FLOAT NOT NULL, 
	original_category VARCHAR(20), 
	adjusted_category VARCHAR(20), 
	reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(adjusted_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS forecast_snapshot_details (
	id SERIAL NOT NULL, 
	snapshot_id INTEGER, 
	opportunity_id INTEGER NOT NULL, 
	forecast_category VARCHAR(20), 
	amount FLOAT NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES pipeline_snapshots (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS leads (
	id SERIAL NOT NULL, 
	first_name VARCHAR(100) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	phone VARCHAR(50), 
	company VARCHAR(255), 
	title VARCHAR(100), 
	source VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	lead_score INTEGER NOT NULL, 
	tenant_id INTEGER, 
	owner_id INTEGER NOT NULL, 
	converted_customer_id INTEGER, 
	converted_opportunity_id INTEGER, 
	converted_at TIMESTAMP WITH TIME ZONE, 
	converted_by INTEGER, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(converted_customer_id) REFERENCES customers (id), 
	FOREIGN KEY(converted_opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(converted_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS meeting_bookings (
	id SERIAL NOT NULL, 
	meeting_link_id INTEGER NOT NULL, 
	booker_name VARCHAR(200) NOT NULL, 
	booker_email VARCHAR(255) NOT NULL, 
	scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	notes TEXT, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(meeting_link_id) REFERENCES meeting_links (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE IF NOT EXISTS objections (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	event_id INTEGER, 
	objection_type VARCHAR(40) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	evidence_text TEXT, 
	resolved_flag BOOLEAN NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	ttr_hours FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS opportunity_embeddings (
	opportunity_id INTEGER NOT NULL, 
	embedding_json TEXT NOT NULL, 
	dim INTEGER NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (opportunity_id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS opportunity_events (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	entity_type VARCHAR(30), 
	entity_id INTEGER, 
	description TEXT, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS opportunity_features_daily (
	opportunity_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	deal_age_days INTEGER NOT NULL, 
	days_since_last_rep_touch INTEGER NOT NULL, 
	days_since_last_buyer_touch INTEGER NOT NULL, 
	rep_touch_count_14d INTEGER NOT NULL, 
	buyer_reply_count_14d INTEGER NOT NULL, 
	meeting_count_30d INTEGER NOT NULL, 
	quote_count INTEGER NOT NULL, 
	latest_discount_pct FLOAT, 
	competitor_mentions_30d INTEGER NOT NULL, 
	pricing_objections_30d INTEGER NOT NULL, 
	positive_signal_count_14d INTEGER NOT NULL, 
	negative_signal_count_14d INTEGER NOT NULL, 
	momentum_score INTEGER, 
	momentum_band VARCHAR(20), 
	momentum_drivers_json TEXT, 
	buyer_state VARCHAR(30), 
	close_probability FLOAT, 
	quote_revision_count_30d INTEGER NOT NULL, 
	stage_velocity_days FLOAT, 
	decision_maker_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (opportunity_id, snapshot_date), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS opportunity_signals (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	signal_type VARCHAR(30) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	evidence TEXT, 
	source_type VARCHAR(30), 
	source_id INTEGER, 
	is_resolved BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS opportunity_text_embeddings (
	opportunity_id INTEGER NOT NULL, 
	embedding_json TEXT NOT NULL, 
	dim INTEGER NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	vocab_hash VARCHAR(40) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (opportunity_id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pipeline_review_queue (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	suggested_stage VARCHAR(30), 
	suggested_close_date DATE, 
	suggested_amount FLOAT, 
	suggestion_source VARCHAR(40) NOT NULL, 
	evidence_json TEXT, 
	suggested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	decision VARCHAR(20), 
	decided_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE, 
	FOREIGN KEY(decided_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS playbook_adherence (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	playbook_id INTEGER NOT NULL, 
	step_id INTEGER NOT NULL, 
	eligible_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE, 
	FOREIGN KEY(playbook_id) REFERENCES playbooks (id) ON DELETE CASCADE, 
	FOREIGN KEY(step_id) REFERENCES playbook_steps (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recommended_action_windows (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	action_type VARCHAR(60) NOT NULL, 
	window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	window_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	recommended_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expected_uplift FLOAT, 
	urgency_score FLOAT, 
	reason_codes_json TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	done_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS revenue_signals (
	id SERIAL NOT NULL, 
	signal_type VARCHAR(50) NOT NULL, 
	source_entity_type VARCHAR(30) NOT NULL, 
	source_entity_id INTEGER, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	owner_id INTEGER, 
	severity VARCHAR(10) NOT NULL, 
	confidence FLOAT NOT NULL, 
	recommended_action TEXT, 
	metadata_json TEXT, 
	depth INTEGER NOT NULL, 
	event_key VARCHAR(128), 
	is_resolved BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	UNIQUE (event_key)
);

CREATE TABLE IF NOT EXISTS stakeholders (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	email VARCHAR(255), 
	title VARCHAR(200), 
	phone VARCHAR(50), 
	seniority VARCHAR(30), 
	department_group VARCHAR(30), 
	buyer_role VARCHAR(30), 
	notes TEXT, 
	is_auto_detected BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS tasks (
	id SERIAL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	opportunity_id INTEGER, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	due_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	priority VARCHAR(10) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS transcripts (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	title VARCHAR(255) NOT NULL, 
	source VARCHAR(30) NOT NULL, 
	content TEXT NOT NULL, 
	duration_minutes INTEGER, 
	participants TEXT, 
	keywords_found TEXT, 
	summary TEXT, 
	action_items_json TEXT, 
	sentiment VARCHAR(20), 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS v4_deal_replay_snapshots (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	frames_json TEXT NOT NULL, 
	meta_json TEXT NOT NULL, 
	source_timeline_version VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_v4_deal_replay_opp_day UNIQUE (opportunity_id, snapshot_date), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS v4_sales_dna_snapshots (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	traits_json TEXT NOT NULL, 
	meta_json TEXT NOT NULL, 
	miner_version VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_v4_sales_dna_opp_day UNIQUE (opportunity_id, snapshot_date), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS ai_training_data (
	id SERIAL NOT NULL, 
	email_id INTEGER NOT NULL, 
	original_parse TEXT NOT NULL, 
	corrected_parse TEXT NOT NULL, 
	correction_fields VARCHAR(255) NOT NULL, 
	model_used VARCHAR(20) NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(email_id) REFERENCES email_requests (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS campaign_members (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	campaign_id INTEGER NOT NULL, 
	lead_id INTEGER, 
	customer_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	responded_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_campaign_lead UNIQUE (campaign_id, lead_id), 
	CONSTRAINT uq_campaign_customer UNIQUE (campaign_id, customer_id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE IF NOT EXISTS email_embeddings (
	email_request_id INTEGER NOT NULL, 
	embedding_json TEXT NOT NULL, 
	dim INTEGER NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	vocab_hash VARCHAR(40) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (email_request_id), 
	FOREIGN KEY(email_request_id) REFERENCES email_requests (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meeting_auto_links (
	id SERIAL NOT NULL, 
	meeting_booking_id INTEGER, 
	external_event_id VARCHAR(200), 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	matched_by VARCHAR(40) NOT NULL, 
	confidence FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(meeting_booking_id) REFERENCES meeting_bookings (id) ON DELETE CASCADE, 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE SET NULL, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS objection_resolution_actions (
	id SERIAL NOT NULL, 
	objection_id INTEGER NOT NULL, 
	action_type VARCHAR(40) NOT NULL, 
	action_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	payload_json TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(objection_id) REFERENCES objections (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS playbook_executions (
	id SERIAL NOT NULL, 
	playbook_id INTEGER NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	triggered_by_signal_id INTEGER, 
	current_step INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	next_action_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(playbook_id) REFERENCES playbooks (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(triggered_by_signal_id) REFERENCES revenue_signals (id)
);

CREATE TABLE IF NOT EXISTS quotes (
	id SERIAL NOT NULL, 
	quote_number VARCHAR(50) NOT NULL, 
	customer_id INTEGER, 
	email_request_id INTEGER, 
	created_by INTEGER, 
	approved_by INTEGER, 
	status VARCHAR(20) NOT NULL, 
	language VARCHAR(5) NOT NULL, 
	currency VARCHAR(10) NOT NULL, 
	subtotal FLOAT NOT NULL, 
	discount_total FLOAT NOT NULL, 
	tax_rate FLOAT NOT NULL, 
	tax_amount FLOAT NOT NULL, 
	grand_total FLOAT NOT NULL, 
	valid_days INTEGER NOT NULL, 
	notes TEXT, 
	tenant_id INTEGER, 
	parent_quote_id INTEGER, 
	revision_no INTEGER NOT NULL, 
	superseded_by INTEGER, 
	pdf_path VARCHAR(500), 
	close_reason VARCHAR(50), 
	closed_at TIMESTAMP WITH TIME ZONE, 
	opportunity_id INTEGER, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(email_request_id) REFERENCES email_requests (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	FOREIGN KEY(parent_quote_id) REFERENCES quotes (id), 
	FOREIGN KEY(superseded_by) REFERENCES quotes (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
);

CREATE TABLE IF NOT EXISTS sequence_enrollments (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	sequence_id INTEGER NOT NULL, 
	opportunity_id INTEGER, 
	customer_id INTEGER, 
	lead_id INTEGER, 
	current_step INTEGER NOT NULL, 
	is_paused BOOLEAN, 
	status VARCHAR(20) NOT NULL, 
	next_action_at TIMESTAMP WITH TIME ZONE, 
	exit_reason VARCHAR(50), 
	completed_at TIMESTAMP WITH TIME ZONE, 
	enrolled_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sequence_id) REFERENCES sequences (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(enrolled_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS stakeholder_roles (
	id SERIAL NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	stakeholder_id INTEGER NOT NULL, 
	role_key VARCHAR(30) NOT NULL, 
	confidence INTEGER NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id), 
	FOREIGN KEY(stakeholder_id) REFERENCES stakeholders (id)
);

CREATE TABLE IF NOT EXISTS transcript_embeddings (
	transcript_id INTEGER NOT NULL, 
	embedding_json TEXT NOT NULL, 
	dim INTEGER NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	vocab_hash VARCHAR(40) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (transcript_id), 
	FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contracts (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	quote_id INTEGER, 
	title VARCHAR(200) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	value FLOAT, 
	terms_json TEXT, 
	signed_at TIMESTAMP WITH TIME ZONE, 
	signed_by VARCHAR(200), 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(quote_id) REFERENCES quotes (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS quote_items (
	id SERIAL NOT NULL, 
	quote_id INTEGER NOT NULL, 
	spare_part_id INTEGER, 
	original_text TEXT, 
	honeywell_code VARCHAR(100), 
	description VARCHAR(500), 
	quantity INTEGER NOT NULL, 
	unit_price FLOAT NOT NULL, 
	discount_pct FLOAT NOT NULL, 
	line_total FLOAT NOT NULL, 
	match_score FLOAT, 
	match_strategy VARCHAR(50), 
	is_confirmed BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(quote_id) REFERENCES quotes (id) ON DELETE CASCADE, 
	FOREIGN KEY(spare_part_id) REFERENCES spare_parts (id)
);

CREATE TABLE IF NOT EXISTS sequence_step_runs (
	id SERIAL NOT NULL, 
	enrollment_id INTEGER NOT NULL, 
	sequence_id INTEGER NOT NULL, 
	step_number INTEGER NOT NULL, 
	step_action VARCHAR(30) NOT NULL, 
	variant_key VARCHAR(10), 
	status VARCHAR(20) NOT NULL, 
	reason_codes TEXT, 
	payload_snapshot TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_step_run_enrollment_step UNIQUE (enrollment_id, step_number), 
	FOREIGN KEY(enrollment_id) REFERENCES sequence_enrollments (id), 
	FOREIGN KEY(sequence_id) REFERENCES sequences (id)
);

CREATE TABLE IF NOT EXISTS shared_documents (
	id SERIAL NOT NULL, 
	quote_id INTEGER, 
	file_name VARCHAR(255) NOT NULL, 
	file_url VARCHAR(500) NOT NULL, 
	shared_with_email VARCHAR(255) NOT NULL, 
	tracking_token VARCHAR(64) NOT NULL, 
	views_count INTEGER NOT NULL, 
	first_viewed_at TIMESTAMP WITH TIME ZONE, 
	last_viewed_at TIMESTAMP WITH TIME ZONE, 
	total_view_seconds INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(quote_id) REFERENCES quotes (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	quote_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	billing_cycle VARCHAR(20) NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE, 
	mrr FLOAT NOT NULL, 
	next_renewal_date DATE, 
	auto_renew BOOLEAN NOT NULL, 
	items_json TEXT, 
	currency VARCHAR(10) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(quote_id) REFERENCES quotes (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS contract_amendments (
	id SERIAL NOT NULL, 
	contract_id INTEGER NOT NULL, 
	amendment_type VARCHAR(50) NOT NULL, 
	changes_json TEXT, 
	effective_date DATE, 
	approved_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS invoices (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	invoice_number VARCHAR(50) NOT NULL, 
	quote_id INTEGER, 
	contract_id INTEGER, 
	customer_id INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	issue_date TIMESTAMP WITH TIME ZONE, 
	due_date TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	currency VARCHAR(10) NOT NULL, 
	subtotal FLOAT NOT NULL, 
	tax_rate FLOAT NOT NULL, 
	tax_amount FLOAT NOT NULL, 
	grand_total FLOAT NOT NULL, 
	items_json TEXT, 
	notes TEXT, 
	pdf_path VARCHAR(500), 
	paid_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (invoice_number), 
	FOREIGN KEY(quote_id) REFERENCES quotes (id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS revenue_schedules (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	contract_id INTEGER NOT NULL, 
	recognition_type VARCHAR(20) NOT NULL, 
	start_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	end_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	total_amount FLOAT NOT NULL, 
	recognized_amount FLOAT NOT NULL, 
	currency VARCHAR(10) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS revenue_schedule_entries (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	schedule_id INTEGER NOT NULL, 
	period VARCHAR(7) NOT NULL, 
	amount FLOAT NOT NULL, 
	recognized_amount FLOAT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	recognized_at TIMESTAMP WITH TIME ZONE, 
	notes VARCHAR(500), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(schedule_id) REFERENCES revenue_schedules (id)
);


-- Indexes

CREATE INDEX IF NOT EXISTS ix_dna_patterns_tenant_id ON dna_patterns (tenant_id);

CREATE INDEX IF NOT EXISTS ix_dna_patterns_segment_key ON dna_patterns (segment_key);

CREATE INDEX IF NOT EXISTS ix_domain_events_event_type ON domain_events (event_type);

CREATE INDEX IF NOT EXISTS ix_domain_events_created_at ON domain_events (created_at);

CREATE INDEX IF NOT EXISTS ix_feature_usage_name_created ON feature_usage (feature_name, created_at);

CREATE INDEX IF NOT EXISTS ix_feature_usage_feature_name ON feature_usage (feature_name);

CREATE INDEX IF NOT EXISTS ix_federated_benchmarks_tenant_id ON federated_benchmarks (tenant_id);

CREATE INDEX IF NOT EXISTS ix_federated_benchmarks_key_date ON federated_benchmarks (benchmark_key, snapshot_date);

CREATE UNIQUE INDEX IF NOT EXISTS ix_lead_scoring_configs_factor_name ON lead_scoring_configs (factor_name);

CREATE INDEX IF NOT EXISTS ix_network_anomalies_detected_at ON network_anomalies (detected_at);

CREATE INDEX IF NOT EXISTS ix_network_anomalies_tenant_id ON network_anomalies (tenant_id);

CREATE INDEX IF NOT EXISTS ix_network_patterns_segment_key ON network_patterns (segment_key);

CREATE INDEX IF NOT EXISTS ix_network_patterns_tenant_id ON network_patterns (tenant_id);

CREATE INDEX IF NOT EXISTS ix_network_segments_tenant_id ON network_segments (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_network_segments_segment_key ON network_segments (segment_key);

CREATE INDEX IF NOT EXISTS ix_objection_patterns_tenant_id ON objection_patterns (tenant_id);

CREATE INDEX IF NOT EXISTS ix_objection_patterns_segment_key ON objection_patterns (segment_key);

CREATE INDEX IF NOT EXISTS ix_pipeline_snapshot_date ON pipeline_snapshots (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_pb_tenant ON product_bundles (tenant_id);

CREATE INDEX IF NOT EXISTS ix_segment_benchmarks_daily_tenant_id ON segment_benchmarks_daily (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sbd_snapshot_date ON segment_benchmarks_daily (snapshot_date);

CREATE UNIQUE INDEX IF NOT EXISTS ix_settings_key ON settings (key);

CREATE UNIQUE INDEX IF NOT EXISTS ix_spare_parts_honeywell_code ON spare_parts (honeywell_code);

CREATE INDEX IF NOT EXISTS ix_spare_parts_model_number ON spare_parts (model_number);

CREATE INDEX IF NOT EXISTS ix_spare_parts_category ON spare_parts (category);

CREATE INDEX IF NOT EXISTS ix_users_manager_id ON users (manager_id);

CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users (tenant_id);

CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_opportunity_id ON v4_sales_events_shadow (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_account_id ON v4_sales_events_shadow (account_id);

CREATE INDEX IF NOT EXISTS ix_v4_sales_shadow_opp_ts ON v4_sales_events_shadow (opportunity_id, event_ts);

CREATE UNIQUE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_source_ref ON v4_sales_events_shadow (source_ref);

CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_event_ts ON v4_sales_events_shadow (event_ts);

CREATE INDEX IF NOT EXISTS ix_achievements_user_id ON achievements (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash);

CREATE INDEX IF NOT EXISTS ix_approval_rules_tenant_id ON approval_rules (tenant_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON audit_logs (tenant_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs (entity_type);

CREATE INDEX IF NOT EXISTS ix_auto_response_rules_tenant_id ON auto_response_rules (tenant_id);

CREATE INDEX IF NOT EXISTS ix_breach_tenant ON breach_notifications (tenant_id);

CREATE INDEX IF NOT EXISTS ix_campaign_tenant ON campaigns (tenant_id);

CREATE INDEX IF NOT EXISTS ix_campaign_created_by ON campaigns (created_by);

CREATE INDEX IF NOT EXISTS ix_campaign_status ON campaigns (status);

CREATE INDEX IF NOT EXISTS ix_chat_sessions_tenant_id ON chat_sessions (tenant_id);

CREATE INDEX IF NOT EXISTS ix_chat_visitor ON chat_sessions (visitor_id);

CREATE INDEX IF NOT EXISTS ix_coaching_plans_user_id ON coaching_plans (user_id);

CREATE INDEX IF NOT EXISTS ix_coaching_snapshot_user_created ON coaching_snapshots (user_id, created_at);

CREATE INDEX IF NOT EXISTS ix_coaching_snapshots_user_id ON coaching_snapshots (user_id);

CREATE INDEX IF NOT EXISTS ix_comments_tenant_id ON comments (tenant_id);

CREATE INDEX IF NOT EXISTS ix_comments_entity_id ON comments (entity_id);

CREATE INDEX IF NOT EXISTS ix_crm_connections_tenant_active ON crm_connections (tenant_id, is_active);

CREATE INDEX IF NOT EXISTS ix_crm_connections_tenant_id ON crm_connections (tenant_id);

CREATE INDEX IF NOT EXISTS ix_dle_created_at ON dead_letter_events (created_at);

CREATE INDEX IF NOT EXISTS ix_dle_event_type ON dead_letter_events (event_type);

CREATE INDEX IF NOT EXISTS ix_dle_replayed_at ON dead_letter_events (replayed_at);

CREATE INDEX IF NOT EXISTS ix_dle_handler_name ON dead_letter_events (handler_name);

CREATE INDEX IF NOT EXISTS ix_dna_recommendations_tenant_id ON dna_recommendations (tenant_id);

CREATE INDEX IF NOT EXISTS ix_dna_recommendations_segment_key ON dna_recommendations (segment_key);

CREATE INDEX IF NOT EXISTS ix_email_templates_created_by ON email_templates (created_by);

CREATE INDEX IF NOT EXISTS ix_meeting_links_user_id ON meeting_links (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_meeting_links_slug ON meeting_links (slug);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);

CREATE INDEX IF NOT EXISTS ix_pipeline_tenant ON pipelines (tenant_id);

CREATE INDEX IF NOT EXISTS ix_price_entries_spare_part_id ON price_entries (spare_part_id);

CREATE INDEX IF NOT EXISTS ix_product_rules_spare_part_id ON product_rules (spare_part_id);

CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions (user_id);

CREATE INDEX IF NOT EXISTS ix_rfd_snapshot_date ON rep_features_daily (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_report_folder_tenant ON report_folders (tenant_id);

CREATE INDEX IF NOT EXISTS ix_saved_views_user_id ON saved_views (user_id);

CREATE INDEX IF NOT EXISTS ix_segments_tenant_id ON segments (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sequences_tenant_id ON sequences (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sharing_rule_tenant ON sharing_rules (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sig_tenant ON signature_requests (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sig_document ON signature_requests (document_type, document_id);

CREATE INDEX IF NOT EXISTS ix_territory_parent ON territories (parent_id);

CREATE INDEX IF NOT EXISTS ix_territory_tenant ON territories (tenant_id);

CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id);

CREATE INDEX IF NOT EXISTS ix_webhook_subscriptions_tenant_id ON webhook_subscriptions (tenant_id);

CREATE INDEX IF NOT EXISTS ix_workflow_rules_tenant_id ON workflow_rules (tenant_id);

CREATE INDEX IF NOT EXISTS ix_approval_assigned_status ON approval_requests (assigned_to, status);

CREATE INDEX IF NOT EXISTS ix_approval_entity ON approval_requests (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_cm_session ON chat_messages (session_id);

CREATE INDEX IF NOT EXISTS ix_chat_messages_tenant_id ON chat_messages (tenant_id);

CREATE INDEX IF NOT EXISTS ix_crm_record_links_external ON crm_record_links (connection_id, external_id);

CREATE INDEX IF NOT EXISTS ix_crm_sync_jobs_conn_started ON crm_sync_jobs (connection_id, started_at);

CREATE INDEX IF NOT EXISTS ix_custom_field_values_custom_field_id ON custom_field_values (custom_field_id);

CREATE INDEX IF NOT EXISTS ix_custom_field_value_entity ON custom_field_values (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_customers_territory_id ON customers (territory_id);

CREATE INDEX IF NOT EXISTS ix_customers_parent_id ON customers (parent_id);

CREATE INDEX IF NOT EXISTS ix_customers_tenant_id ON customers (tenant_id);

CREATE INDEX IF NOT EXISTS ix_playbook_steps_playbook_id ON playbook_steps (playbook_id);

CREATE INDEX IF NOT EXISTS ix_pt_price_entry ON price_tiers (price_entry_id);

CREATE INDEX IF NOT EXISTS ix_report_templates_tenant_id ON report_templates (tenant_id);

CREATE INDEX IF NOT EXISTS ix_ta_territory ON territory_assignments (territory_id);

CREATE INDEX IF NOT EXISTS ix_ta_user ON territory_assignments (user_id);

CREATE INDEX IF NOT EXISTS ix_delivery_tenant ON webhook_deliveries (tenant_id);

CREATE INDEX IF NOT EXISTS ix_delivery_sub_delivered ON webhook_deliveries (subscription_id, delivered_at);

CREATE UNIQUE INDEX IF NOT EXISTS ix_account_enrichments_customer_id ON account_enrichments (customer_id);

CREATE INDEX IF NOT EXISTS ix_afd_snapshot_date ON account_features_daily (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_account_team_tenant ON account_teams (tenant_id);

CREATE INDEX IF NOT EXISTS ix_account_teams_customer_id ON account_teams (customer_id);

CREATE INDEX IF NOT EXISTS ix_account_teams_user_id ON account_teams (user_id);

CREATE INDEX IF NOT EXISTS ix_contacts_account_id ON contacts (account_id);

CREATE INDEX IF NOT EXISTS ix_contacts_email ON contacts (email);

CREATE INDEX IF NOT EXISTS ix_cp_tenant ON customer_pricing (tenant_id);

CREATE INDEX IF NOT EXISTS ix_cp_customer ON customer_pricing (customer_id);

CREATE INDEX IF NOT EXISTS ix_opp_customer ON opportunities (customer_id);

CREATE INDEX IF NOT EXISTS ix_opportunities_territory_id ON opportunities (territory_id);

CREATE INDEX IF NOT EXISTS ix_opp_owner_stage ON opportunities (owner_id, stage);

CREATE INDEX IF NOT EXISTS ix_opportunities_tenant_id ON opportunities (tenant_id);

CREATE INDEX IF NOT EXISTS ix_opportunities_pipeline_id ON opportunities (pipeline_id);

CREATE INDEX IF NOT EXISTS ix_opp_close_date ON opportunities (close_date);

CREATE INDEX IF NOT EXISTS ix_user_customer_pins_user_id ON user_customer_pins (user_id);

CREATE INDEX IF NOT EXISTS ix_action_experiments_opportunity_id ON action_experiments (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_activity_logs_opportunity_id ON activity_logs (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_activity_log_entity ON activity_logs (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_activity_log_created ON activity_logs (created_at);

CREATE INDEX IF NOT EXISTS ix_activity_logs_source_ref ON activity_logs (source_ref);

CREATE INDEX IF NOT EXISTS ix_activity_logs_customer_id ON activity_logs (customer_id);

CREATE INDEX IF NOT EXISTS ix_buyer_state_snapshot_date ON buyer_state_history (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_competitor_mentions_competitor_name ON competitor_mentions (competitor_name);

CREATE INDEX IF NOT EXISTS ix_competitor_mentions_opportunity_id ON competitor_mentions (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_deal_replay_deltas_opp_to_ts ON deal_replay_deltas (opportunity_id, to_ts);

CREATE INDEX IF NOT EXISTS ix_deal_room_opportunity ON deal_rooms (opportunity_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_deal_room_token ON deal_rooms (external_token);

CREATE INDEX IF NOT EXISTS ix_deal_similarity_links_opportunity_id ON deal_similarity_links (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_decision_gaps_opp_type ON decision_gaps (opportunity_id, gap_type);

CREATE INDEX IF NOT EXISTS ix_decision_gaps_opportunity_id ON decision_gaps (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_email_requests_tenant_id ON email_requests (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_email_requests_message_id ON email_requests (message_id);

CREATE INDEX IF NOT EXISTS ix_email_requests_customer_id ON email_requests (customer_id);

CREATE INDEX IF NOT EXISTS ix_email_requests_thread_id ON email_requests (thread_id);

CREATE INDEX IF NOT EXISTS ix_email_requests_status ON email_requests (status);

CREATE INDEX IF NOT EXISTS ix_email_requests_opportunity_id ON email_requests (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_forecast_adj_opportunity ON forecast_adjustments (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_fsd_created ON forecast_snapshot_details (created_at);

CREATE INDEX IF NOT EXISTS ix_fsd_opportunity ON forecast_snapshot_details (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_fsd_snapshot ON forecast_snapshot_details (snapshot_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_email ON leads (email);

CREATE INDEX IF NOT EXISTS ix_lead_owner ON leads (owner_id);

CREATE INDEX IF NOT EXISTS ix_leads_tenant_id ON leads (tenant_id);

CREATE INDEX IF NOT EXISTS ix_lead_score ON leads (lead_score);

CREATE INDEX IF NOT EXISTS ix_lead_status ON leads (status);

CREATE INDEX IF NOT EXISTS ix_meeting_bookings_opportunity_id ON meeting_bookings (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_meeting_bookings_customer_id ON meeting_bookings (customer_id);

CREATE INDEX IF NOT EXISTS ix_meeting_bookings_meeting_link_id ON meeting_bookings (meeting_link_id);

CREATE INDEX IF NOT EXISTS ix_objections_opportunity_id ON objections (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_opportunity_events_opportunity_id ON opportunity_events (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_ofd_snapshot_date ON opportunity_features_daily (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_opportunity_signals_opportunity_id ON opportunity_signals (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_pipeline_review_queue_decided_opp ON pipeline_review_queue (decided_at, opportunity_id);

CREATE INDEX IF NOT EXISTS ix_playbook_adherence_opportunity_id ON playbook_adherence (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_recommended_action_windows_opportunity_id ON recommended_action_windows (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_rs_opp_created ON revenue_signals (opportunity_id, created_at);

CREATE INDEX IF NOT EXISTS ix_revenue_signals_signal_type ON revenue_signals (signal_type);

CREATE INDEX IF NOT EXISTS ix_rs_type_severity ON revenue_signals (signal_type, severity);

CREATE INDEX IF NOT EXISTS ix_rs_owner_created ON revenue_signals (owner_id, created_at);

CREATE INDEX IF NOT EXISTS ix_rs_customer ON revenue_signals (customer_id);

CREATE INDEX IF NOT EXISTS ix_stakeholders_customer_id ON stakeholders (customer_id);

CREATE INDEX IF NOT EXISTS ix_stakeholders_opportunity_id ON stakeholders (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_tasks_owner_id ON tasks (owner_id);

CREATE INDEX IF NOT EXISTS ix_tasks_opportunity_id ON tasks (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_transcripts_opportunity_id ON transcripts (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_transcripts_customer_id ON transcripts (customer_id);

CREATE INDEX IF NOT EXISTS ix_v4_deal_replay_opp_date ON v4_deal_replay_snapshots (opportunity_id, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_v4_sales_dna_opp_date ON v4_sales_dna_snapshots (opportunity_id, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_ai_training_data_email_id ON ai_training_data (email_id);

CREATE INDEX IF NOT EXISTS ix_campaign_member_campaign ON campaign_members (campaign_id);

CREATE INDEX IF NOT EXISTS ix_campaign_member_tenant ON campaign_members (tenant_id);

CREATE INDEX IF NOT EXISTS ix_meeting_auto_links_opp ON meeting_auto_links (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_objection_resolution_actions_objection_id ON objection_resolution_actions (objection_id);

CREATE INDEX IF NOT EXISTS ix_playbook_executions_opportunity_id ON playbook_executions (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_playbook_executions_playbook_id ON playbook_executions (playbook_id);

CREATE INDEX IF NOT EXISTS ix_exec_opp_playbook ON playbook_executions (opportunity_id, playbook_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_quotes_quote_number ON quotes (quote_number);

CREATE INDEX IF NOT EXISTS ix_quotes_opportunity_id ON quotes (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_quotes_status ON quotes (status);

CREATE INDEX IF NOT EXISTS ix_quotes_tenant_id ON quotes (tenant_id);

CREATE INDEX IF NOT EXISTS ix_quotes_email_request_id ON quotes (email_request_id);

CREATE INDEX IF NOT EXISTS ix_quotes_customer_id ON quotes (customer_id);

CREATE INDEX IF NOT EXISTS ix_sequence_enrollments_sequence_id ON sequence_enrollments (sequence_id);

CREATE INDEX IF NOT EXISTS ix_sequence_enrollments_lead_id ON sequence_enrollments (lead_id);

CREATE INDEX IF NOT EXISTS ix_sequence_enrollments_tenant_id ON sequence_enrollments (tenant_id);

CREATE INDEX IF NOT EXISTS ix_sequence_enrollments_opportunity_id ON sequence_enrollments (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_stakeholder_roles_opportunity_id ON stakeholder_roles (opportunity_id);

CREATE INDEX IF NOT EXISTS ix_stakeholder_roles_stakeholder_id ON stakeholder_roles (stakeholder_id);

CREATE INDEX IF NOT EXISTS ix_stakeholder_roles_opp_role ON stakeholder_roles (opportunity_id, role_key);

CREATE INDEX IF NOT EXISTS ix_contracts_quote_id ON contracts (quote_id);

CREATE INDEX IF NOT EXISTS ix_contracts_customer_id ON contracts (customer_id);

CREATE INDEX IF NOT EXISTS ix_contracts_tenant_id ON contracts (tenant_id);

CREATE INDEX IF NOT EXISTS ix_contracts_status ON contracts (status);

CREATE INDEX IF NOT EXISTS ix_quote_items_quote_id ON quote_items (quote_id);

CREATE INDEX IF NOT EXISTS ix_sequence_step_runs_sequence_id ON sequence_step_runs (sequence_id);

CREATE INDEX IF NOT EXISTS ix_sequence_step_runs_enrollment_id ON sequence_step_runs (enrollment_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_shared_documents_tracking_token ON shared_documents (tracking_token);

CREATE INDEX IF NOT EXISTS ix_shared_documents_quote_id ON shared_documents (quote_id);

CREATE INDEX IF NOT EXISTS ix_subscriptions_customer_id ON subscriptions (customer_id);

CREATE INDEX IF NOT EXISTS ix_subscriptions_tenant_id ON subscriptions (tenant_id);

CREATE INDEX IF NOT EXISTS ix_contract_amendments_contract_id ON contract_amendments (contract_id);

CREATE INDEX IF NOT EXISTS ix_invoice_customer ON invoices (customer_id);

CREATE INDEX IF NOT EXISTS ix_invoice_tenant ON invoices (tenant_id);

CREATE INDEX IF NOT EXISTS ix_invoice_status ON invoices (status);

CREATE INDEX IF NOT EXISTS ix_rs_contract ON revenue_schedules (contract_id);

CREATE INDEX IF NOT EXISTS ix_rs_tenant ON revenue_schedules (tenant_id);

CREATE INDEX IF NOT EXISTS ix_rse_schedule ON revenue_schedule_entries (schedule_id);

CREATE INDEX IF NOT EXISTS ix_rse_tenant ON revenue_schedule_entries (tenant_id);
"""


def upgrade() -> None:
    # Widen alembic's own version_num column. Default is VARCHAR(32),
    # but the chain has revision IDs up to 33 chars (e.g.
    # ``20260425_activity_logs_source_ref``). Without this, alembic
    # crashes on the first revision-stamp UPDATE with
    # StringDataRightTruncationError. Idempotent.
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(64)"
    )

    # PostgreSQL does not allow multi-statement DDL inside a single
    # ``execute()`` call when transactional DDL is in play, so split
    # the embedded DDL into individual statements first.
    #
    # Strip line-comments (``-- ...``) before splitting so they don't
    # get glued onto the first statement and cause the whole chunk
    # to be filtered out (round-4 v1.9.14 incident).
    cleaned_lines = [
        line for line in _BOOTSTRAP_DDL.splitlines()
        if not line.lstrip().startswith("--")
    ]
    cleaned = "\n".join(cleaned_lines)
    for stmt in cleaned.split(";\n"):
        stmt = stmt.strip()
        if not stmt:
            continue
        op.execute(stmt + ";")


def downgrade() -> None:
    # Refuse to drop production tables. If you need a clean slate,
    # do it with ``DROP SCHEMA public CASCADE`` outside alembic.
    pass
