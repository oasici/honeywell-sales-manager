# Honeywell Sales Suite v2 — Market Extended Backlog (Salesforce dışı)

Kaynak pattern’lar: Revenue intelligence (Gong/Clari), Sales engagement (Outreach/Salesloft), SMB CRM (HubSpot/Pipedrive), CPQ (DealHub vb.), Microsoft Copilot for Sales.

Bu backlog, v2 için **en az 20** üretim-grade özellik önerir ve fazlara böler.

## Faz 3.0 — Board foundation + pipeline hygiene
1) **Deal rotting per-stage thresholds** (Pipedrive rotting benzeri)  
2) **No-touch alerts → notifications** (per owner)  
3) **Kanban WIP limits** (manager policy)  
4) **Bulk stage update review queue** (suggestive pipeline updates)  
5) **Saved views + sharing** (team views)  
6) **Deal desk approval lane** (yüksek indirim/özel fiyat için)  

## Faz 3.1 — Summaries + CRM update önerileri (Copilot pattern)
7) **Email thread summary** (per opportunity)  
8) **Meeting prep brief** (agenda + last touch + risks)  
9) **Suggested CRM updates cards** (close_date/amount/next_step önerisi)  
10) **Auto-link meetings/emails to opportunity** (integration-driven)  
11) **One-click “log note” + templates**  

## Faz 3.2 — Conversation intelligence (Gong pattern)
12) **Transcript ingestion pipeline** (Teams/Zoom upload + parse)  
13) **Keyword packs** (competitor/pricing/objection configurable)  
14) **Moments timeline** (pricing mention timestamps)  
15) **NL search across transcripts** (“hangi fırsatlar fiyat itirazı?”)  
16) **Coaching scorecards** (rep başına objections handling)  

## Faz 3.3 — Revenue intelligence / forecasting (Clari pattern)
17) **Forecast categories** (commit/best_case/pipeline/omitted)  
18) **Pipeline coverage ratio** (quota hedefi ile)  
19) **Slippage dashboard** (push count + stage regression)  
20) **Risk reasons** (at-risk faktörleri + explainability)  
21) **What changed since last week** (pipeline diff digest)  

## Faz 3.4 — CPQ / quote-to-cash guardrails (DealHub pattern)
22) **Guided selling questions** (ürün konfigürasyonu için)  
23) **Discount guardrails** (threshold → approval routing)  
24) **Versioned quotes under one opportunity** (revizyon ağacı)  
25) **Contract/e-sign integration hook** (DocuSign vb. sadece hook)  

## Faz 3.5 — Data quality + RevOps automation
26) **Data completeness scoring** (required fields)  
27) **Duplicate detection** (account/opportunity/email)  
28) **SLA dashboards** (speed-to-lead / response SLA)  
29) **Automated sequences** (outreach steps)  
30) **Territory/segment planning** (rule-based → NL)  

## Notlar (uygulama ilkeleri)
- Her özellik için: feature-flag, RBAC, audit ve test planı zorunlu.
- Entegrasyonlar opsiyonel: core board, entegrasyon olmadan da değer üretmeli.

