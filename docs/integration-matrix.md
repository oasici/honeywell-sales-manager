# Integration Matrix — Cadence Engine Sprints

## Durum Ozeti

| Sprint | Durum | Backend Tests | Frontend TS | Yeni Dosyalar |
|--------|-------|---------------|-------------|---------------|
| 0 | TAMAMLANDI | 13/13 | 0 error | 3 model, 1 service, 1 doc |
| 1 | TAMAMLANDI | 13/13 | 0 error | 1 service (sequence_engine), 4 API endpoint |
| 2 | TAMAMLANDI | 10/10 | 0 error | 1 service (scoring), 4 workflow actions |
| 3 | TAMAMLANDI | 13/13 | 0 error | variant bucketing, branch eval, 1 API endpoint |
| 4 | TAMAMLANDI | — | 0 error | 1 API module (stakeholders), 1 UI component |
| 5 | TAMAMLANDI | — | 0 error | CockpitPage 3-tab, SequencesTab, analytics |
| **TOPLAM** | **36 test** | **36/36 green** | **0 error** | |

## Degisiklik Ozeti

### Yeni Dosyalar
- `backend/app/models/sequence_v2.py` — SequenceStepRun, DomainEvent, Stakeholder
- `backend/app/services/domain_events.py` — Event constants, schemas, emit helper
- `backend/app/services/sequence_engine.py` — V2 engine (idempotent, exit, telemetry, A/B, branch)
- `backend/app/services/scoring_service.py` — Behavioral scoring, auto-enroll
- `backend/app/api/v1/stakeholders.py` — Buyer Relationship Map CRUD + alerts
- `frontend/src/features/opportunities/BuyerRelationshipMap.tsx` — Map UI
- `backend/tests/test_sequence_engine.py` — 13 tests
- `backend/tests/test_scoring_service.py` — 10 tests
- `backend/tests/test_branching_variants.py` — 13 tests
- `docs/integration-matrix.md` — Bu dosya

### Degistirilen Dosyalar
- `backend/app/core/config.py` — +3 feature flags
- `backend/app/models/engagement.py` — +2 additive fields (exit_reason, completed_at)
- `backend/app/models/__init__.py` — +3 model imports
- `backend/app/services/job_queue.py` — V2 engine delegation (flag-gated)
- `backend/app/services/workflow_service.py` — +4 action types
- `backend/app/api/v1/engagement.py` — +5 V2 endpoints
- `backend/app/api/v1/router.py` — +1 router (stakeholders)
- `backend/app/main.py` — +2 event bus wiring blocks
- `frontend/src/lib/types.ts` — +4 interfaces
- `frontend/src/lib/api.ts` — +2 API modules
- `frontend/src/features/cockpit/CockpitPage.tsx` — 3-tab Work Hub
- `frontend/src/features/board/OpportunityDetailPage.tsx` — Buyer Map integration
- `.env.sandbox` — +3 flags

## Sprint 0 — Entegrasyon Sozlesmesi + Telemetry Temeli

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Feature flags | `config.py`: FEATURE_SEQUENCES_V2, FEATURE_BEHAVIORAL_SCORING, FEATURE_BUYER_MAP | — | — | — | N/A (flags themselves) | Flag defaults = False |
| SequenceStepRun model | — | — | — | `sequence_step_runs` (yeni tablo) | FEATURE_SEQUENCES_V2 | Model import + create_all |
| DomainEvent model | — | — | — | `domain_events` (yeni tablo) | Always available | Model import + create_all |
| Stakeholder model | — | — | — | `stakeholders` (yeni tablo) | FEATURE_BUYER_MAP | Model import + create_all |
| SequenceEnrollment ext | — | — | — | `exit_reason`, `completed_at` (additive columns) | FEATURE_SEQUENCES_V2 | Column nullable, backward compat |
| Domain event constants | `services/domain_events.py` | — | Schema: DomainEvents.* | — | — | Payload schema validation |
| emit_domain_event helper | `services/domain_events.py` | — | persist + event_bus.publish | domain_events row | — | Unit: serialization, idempotent |

## Sprint 1 — Sequence v2: Global Exit + Idempotency + StepRun Log

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Idempotent step exec | `services/job_queue.py`: execute_sequence_step | — | — | StepRun uq check | FEATURE_SEQUENCES_V2 | Job retry sim: ayni step 2x calismasin |
| Global exit check | `services/sequence_engine.py`: check_global_exit | — | Checks: lead.status, opp.stage, email_bounced | enrollment.status -> exited, exit_reason set | FEATURE_SEQUENCES_V2 | Exit kosulu: converted lead -> exit |
| StepRun logging | `services/job_queue.py` | — | — | sequence_step_runs INSERT | FEATURE_SEQUENCES_V2 | Her step icin StepRun kaydi |
| Event emission | `services/job_queue.py` | — | `sequence.step_completed`, `sequence.completed`, `sequence.exited` | domain_events INSERT | FEATURE_SEQUENCES_V2 | Event payload dogru |
| Event bus wiring | `main.py` lifespan | — | Subscribe: sequence.* events | — | FEATURE_SEQUENCES_V2 | Handler count artar |
| Step runs API | `api/v1/engagement.py`: GET /sequences/enrollments/{id}/step-runs | SequencesPage (future) | — | sequence_step_runs SELECT | FEATURE_SEQUENCES_V2 | API response shape |
| Enrollment detail API | `api/v1/engagement.py`: GET /sequences/enrollments/{id} | SequencesPage (future) | — | enrollment + step_runs | FEATURE_SEQUENCES_V2 | exit_reason, completed_at gorunur |

## Sprint 2 — Behavioral Scoring + Auto-Enroll/Auto-Exit

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Lead scoring service | `services/scoring_service.py` | — | `lead.score_changed` | leads.lead_score UPDATE | FEATURE_BEHAVIORAL_SCORING | Skor guncelleme deterministik |
| Scoring rules engine | `services/scoring_service.py` | — | Consumes: sequence.step_completed, email.parsed, etc. | — | FEATURE_BEHAVIORAL_SCORING | Kural bazli v1 |
| Auto-enroll genisletme | `services/sequence_engine.py` | — | `sequence.enrolled_auto` | — | FEATURE_BEHAVIORAL_SCORING | Dogru lead seti secimi |
| Workflow actions ext | `services/workflow_service.py` | — | Actions: enroll_sequence, pause_sequence, exit_sequence | — | FEATURE_SEQUENCES_V2 + FEATURE_WORKFLOW_RULES | Idempotent enroll/exit |
| Score change -> re-priority | — | CockpitPage (future) | `lead.score_changed` | — | FEATURE_BEHAVIORAL_SCORING | Work hub siralamasini etkiler |

## Sprint 3 — Branching + A/B Variants

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Step schema v2 parser | `services/sequence_engine.py` | SequenceBuilderPage (future) | — | steps_json v2 format | FEATURE_SEQUENCES_V2 | Backward compat: eski steps_json calisir |
| Variant bucketing | `services/sequence_engine.py` | — | — | step_runs.variant_key | FEATURE_SEQUENCES_V2 | Hash-based deterministik atama |
| Branch evaluation | `services/sequence_engine.py` | — | — | branch_rules in steps_json | FEATURE_SEQUENCES_V2 | Branch rule: opened/clicked/replied |
| Variant metrics API | `api/v1/engagement.py` | DashboardEditorPage (future) | — | Aggregated step_runs | FEATURE_SEQUENCES_V2 | Varyant bazinda rapor |

## Sprint 4 — Buyer Relationship Map v1

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Stakeholder CRUD | `api/v1/stakeholders.py` | — | — | stakeholders CRUD | FEATURE_BUYER_MAP | RBAC, additive migration |
| Relationship map UI | — | OpportunityDetail (yeni tab) | — | — | FEATURE_BUYER_MAP | UI smoke |
| Coverage gap alerts | `api/v1/stakeholders.py`: GET /alerts | — | — | stakeholders SELECT | FEATURE_BUYER_MAP | DM yok, departman eksik |
| Transcript enrichment | `services/stakeholder_enrichment.py` | — | `transcript.created` | stakeholders INSERT (is_auto_detected) | FEATURE_BUYER_MAP | Participant parse -> oneri |

## Sprint 5 — Work Hub v2 + Analytics

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Cockpit 3-tab | — | CockpitPage v2 | — | — | FEATURE_SEQUENCES_V2 | Tab navigation |
| Completion analytics | `api/v1/engagement.py`: GET /sequences/analytics | CockpitPage | — | step_runs aggregation | FEATURE_SEQUENCES_V2 | Tamamlama nedeni, temas/hedef |
| Manager dashboard | `api/v1/engagement.py`: GET /sequences/performance | CockpitPage, SequencesPage | — | step_runs + enrollments | FEATURE_SEQUENCES_V2 | `pytest` `test_sequence_performance_*` |
| E2E tests | — | — | — | — | — | Playwright: role-based + cockpit |

## Product Sprint 4 — Prospecting + Engagement (pipeline)

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| ProspectingAgent (facade) | `services/prospecting_agent.py` → `HighIntentService` | — | — | customers + emails + activities | — | `pytest` `test_prospecting_agent_facade` |
| High-intent + pin | `api/v1/customers.py`: high-intent, pin | Board, HighIntentAccountsPage, CustomerDetail | — | pins + scoring | — | mevcut |
| Email template library in sequences | `email_templates` + `SequenceBuilderPage` | SequenceBuilder | — | steps_json `email_template_id` | — | UI smoke |
| Calendar adapter stub | `services/calendar_adapter.py` | — | — | — | — | import |
| Schedule meeting placeholder | `api/v1/meetings.py`: POST `/schedule-placeholder` | OpportunityDetailPage | activity log | activity_logs | — | `pytest` `test_schedule_meeting_placeholder` |

## Product Sprint 5 — Signals + Insights + Search

| Teslimat | Backend | Frontend | Event/Trigger | Data | Gating | Test |
|----------|---------|----------|---------------|------|--------|------|
| Signals trend series | `api/v1/insights.py`: GET `/signals/trends` | InsightsPage (Recharts) | — | opportunity_signals | FEATURE_V2_BOARD | `pytest` trends |
| Conversation keyword insights | `api/v1/insights.py`: GET `/conversation-insights` | InsightsPage | — | transcripts ILIKE buckets | FEATURE_V2_BOARD | — |
| Unified conversation search | `api/v1/insights.py`: GET `/conversation-search` | InsightsPage | — | transcripts + email_requests + opportunity_events | FEATURE_V2_BOARD | `pytest` conversation_search_* |
| Filters stage / signal / owner | `conversation_insights_service.py` | InsightsPage selects | — | opportunity joins | FEATURE_V2_BOARD | manager: owner filter |
