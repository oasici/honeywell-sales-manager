# Salesforce AI (Agentforce/Einstein) → Honeywell v2 Mapping

Kaynak: `https://www.salesforce.com/eu/sales/ai/`

Bu doküman, Salesforce’un AI feature başlıklarını Honeywell Sales Suite v2 modüllerine birebir eşler. Amaç **parity** değil, “aynı kullanıcı değerini” kendi domain/entegrasyonlarımızla sağlamak.

## 1) Prospecting
### Salesforce: High-intent account lists + enrichment (Salesforce/Slack)
**Honeywell v2 karşılığı**
- **Modül**: `ProspectingAgent`
- **UI**: `/board` içinde “High Intent Accounts” widget + `/accounts` liste
- **Veri**: web sinyali (3rd-party) + CRM sinyali + email engagement + ürün kullanım (varsa)
- **MVP**: Rule-based scoring + manuel pin/unpin
- **V2.1+**: ML ranking + explainability

## 2) Engagement
### Salesforce: Outreach (web/email/voice) + meeting scheduling + product Q&A
**Honeywell v2 karşılığı**
- **Modül**: `EngagementSequences` + `CalendarIntegration`
- **UI**: Opportunity 360 içinde “Sequence” + “Schedule meeting”
- **MVP**: email template + follow-up tasks (in-app)
- **V2.2+**: calendar scheduling + auto-log meeting
- **Not**: “product Q&A” için company FAQ index + RAG (opsiyonel)

## 3) Pipeline Management
### Salesforce: Automatic consistent updates (stage, next steps) suggestive/auto
**Honeywell v2 karşılığı**
- **Modül**: `PipelineUpdateAssistant`
- **UI**: `/board` kanban kartlarında “AI Suggest” + bulk review
- **MVP**: stage önerisi (rotting + activity) + next step önerisi (rule-based)
- **V2.1+**: LLM öneri + “Apply” audit log + feature-flag ile auto-apply canary

## 4) Account Management
### Salesforce: Account research, strategic POV, account plans, meeting prep, next steps
**Honeywell v2 karşılığı**
- **Modül**: `Account360` + `AccountPlan`
- **UI**: `/accounts/:id` + Opportunity 360 içinde “Meeting Prep”
- **MVP**: internal timeline + open quotes + last touch + risk summary
- **V2.2+**: enrichment (news/website) + plan templates

## 5) Call Insights
### Salesforce: Keywords, objections, competitor mentions, pricing attitudes
**Honeywell v2 karşılığı**
- **Modül**: `ConversationInsights`
- **UI**: Opportunity 360 “Signals” tab
- **MVP**: email metninden keyword/sentiment flags
- **V2.3+**: call transcript ingestion + highlight extraction

## 6) Call Explorer (NL search)
### Salesforce: Natural language search across calls (“which deals mentioned pricing?”)
**Honeywell v2 karşılığı**
- **Modül**: `ConversationSearch`
- **UI**: `/insights` içinde arama barı
- **MVP**: transcript search (BM25/pgvector) + filtre (stage, owner)
- **V2.3+**: NL query → structured filters + answer snippets

## 7) Sales Signals (trends across pipeline)
### Salesforce: Topic clustering across pipeline
**Honeywell v2 karşılığı**
- **Modül**: `SignalsDashboard`
- **UI**: `/insights` trend kartları
- **MVP**: topic counts (pricing/competitor/objection) + impacted opportunities
- **V2.3+**: clustering + anomaly alerts → notifications

## 8) Embedded summarisation
### Salesforce: One-click summaries for account/opportunity/lead/contact
**Honeywell v2 karşılığı**
- **Modül**: `SummaryService`
- **UI**: Opportunity/Account/Quote sayfalarında “Özet” butonu
- **MVP**: kısa özet + kaynak link listesi
- **Güvenlik**: PII guard + max tokens + audit

## 9) AI-driven Deal Insights
### Salesforce: Prioritize critical deals, avoid guesswork
**Honeywell v2 karşılığı**
- **Modül**: `DealHealth`
- **UI**: `/board` “Riskli Deals” + detail’de explainability
- **MVP**: rule-based score (rotting, discount, SLA breach)
- **V2.4+**: predictive risk model

## 10) Predictive Scoring
### Salesforce: Forecast accuracy + visibility into factors
**Honeywell v2 karşılığı**
- **Modül**: `PredictiveScoring`
- **UI**: Opportunity detail “Close probability” + factors
- **MVP**: heuristic probability + factors
- **V2.4+**: ML model + SHAP benzeri açıklama

## 11) Planning (territory/segments/formulas)
### Salesforce: territory optimisation summary + formula/segment generation
**Honeywell v2 karşılığı**
- **Modül**: `PlanningStudio`
- **UI**: `/insights/planning`
- **MVP**: segment builder (rule-based) + saved views
- **V2.5+**: NL → segment rules + formula generator

