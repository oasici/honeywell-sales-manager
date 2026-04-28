# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `Unreleased` section accumulates work merged to the deploy branch
since the last tag. The release-please workflow at
`.github/workflows/release-please.yml` opens a release PR that drains
that section into a numbered version when a new release is cut.

## [1.2.0](https://github.com/oasici/honeywell-sales-manager/compare/v1.1.0...v1.2.0) (2026-04-28)


### Added

* **design-system:** Phase 1 — Linear/Stripe-style design system + 6 primitives ([c2747b7](https://github.com/oasici/honeywell-sales-manager/commit/c2747b749acf2a8f951c18f6ff2a9dd212ca5105))
* **design-system:** Phases 2–8 — modernize 60+ surfaces with Linear/Stripe/Apple polish ([0101361](https://github.com/oasici/honeywell-sales-manager/commit/0101361b55fa23fc0deda8742fd850fce416e17b))
* **observability:** emit Sentry metrics for breaker + Claude requests ([8160396](https://github.com/oasici/honeywell-sales-manager/commit/816039630efc8ebc3f621fa2cb90ade4ed6fc162))
* **observability:** wire Sentry source map upload + release tracking ([7c10ccc](https://github.com/oasici/honeywell-sales-manager/commit/7c10cccdeabb44c36b032720aad8672ea1e1a244))
* **v10:** spare parts intelligence layer + PG test DB migration ([9762e7f](https://github.com/oasici/honeywell-sales-manager/commit/9762e7f558846af8f30d2d6af770dec43c034c3c))
* **v11:** Qdrant RAG completion + UAT pass-2 (notification fetch + AI tabs) ([471e377](https://github.com/oasici/honeywell-sales-manager/commit/471e3771c66f3b27b49a459c6bc59e008f303b8c))
* **v12:** close last 2 backlog items — multi-tenant CRM enforcement + transformer sequence embedding ([afd53fc](https://github.com/oasici/honeywell-sales-manager/commit/afd53fc58dffc303b960e314fc5297caf545bb2d))
* **v5:** intelligence platform foundation — objections, timing, benchmarks, DNA, similarity ([35be267](https://github.com/oasici/honeywell-sales-manager/commit/35be267942a7bf05688034a04274817e05adbfa7))
* **v6:** intelligence depth — sequence tokens, 7-state buyer, replay deltas, DNA→playbook, trajectory similarity ([9e66870](https://github.com/oasici/honeywell-sales-manager/commit/9e66870f6b0fe389ac4e21af37fa2f6e61b063bf))
* **v7:** final stretch — LLM-hybrid objections, Bayesian uplift, sequence similarity, tenant boundary ([c6c71ec](https://github.com/oasici/honeywell-sales-manager/commit/c6c71ec55f7d1c7f8d29cd0945c8805b34fe3207))
* **v8:** sequence text embedding + multi-tenant CRM core + comprehensive demo seed ([9789583](https://github.com/oasici/honeywell-sales-manager/commit/978958375faa2ff856a7a61248e3c5384806fa50))
* **v9:** close V2/V3 gaps — CRM sync, calendar OAuth, board UX, NL search, quote revisions, slippage ([9af0221](https://github.com/oasici/honeywell-sales-manager/commit/9af02212a068ed4ab3c8276a651c1c5bc1105c43))


### Fixed

* **activities:** defer source_ref on remaining ActivityLog SELECTs ([19b70ee](https://github.com/oasici/honeywell-sales-manager/commit/19b70ee189aa646faa3784f2467ded983d4f44c1))
* **admin:** cap users dropdown query at the backend's max page_size ([b237b8c](https://github.com/oasici/honeywell-sales-manager/commit/b237b8c187c889bb3fe470c0ce88d502da34402d))
* **alembic:** widen alembic_version.version_num past 32 chars ([0b4ca58](https://github.com/oasici/honeywell-sales-manager/commit/0b4ca58987a7907f17c08cf617c680f31ba9be47))
* **observability:** resolve top Sentry issues — activity feed crash + Claude churn parser ([408d268](https://github.com/oasici/honeywell-sales-manager/commit/408d268de0660cce61aa462c08c10c897e71283c))
* **ops:** use real V4 __tablename__ values in ensure-tables workflow ([7370505](https://github.com/oasici/honeywell-sales-manager/commit/7370505a727812566685bb66545b53f019f9bb5b))
* **uat:** V9 UAT items 4 + 15 — deep i18n on Opportunity/Customer detail pages ([2b33fe9](https://github.com/oasici/honeywell-sales-manager/commit/2b33fe9d25cc685c710e9616d6cbdcb487c02b9d))
* **uat:** V9 UAT pass-1 — seed extension + 3 quick UI removals ([4d4b174](https://github.com/oasici/honeywell-sales-manager/commit/4d4b174886549ccedcc3c867278c52d88b59e8a9))
* **uat:** V9 UAT pass-3 — i18n diacritics + Pipeline key dropdown + Compliance + Sequence template flow + Risk badge fallback ([687f7ac](https://github.com/oasici/honeywell-sales-manager/commit/687f7acd7c3c76c8e7a3f4c33b84f948b99cadb6))


### Security

* **deps:** bump sentry-sdk 2.18.0 → 2.58.0 ([3692757](https://github.com/oasici/honeywell-sales-manager/commit/3692757d1468c979113920c913aea1c98e7160f0))

## [1.1.0](https://github.com/oasici/honeywell-sales-manager/compare/v1.0.0...v1.1.0) (2026-04-25)


### Added

* **v4:** Intelligence Backbone — feature store, sales DNA, deal replay, decision gaps ([6d69592](https://github.com/oasici/honeywell-sales-manager/commit/6d6959211d014551464e4400bdf745b195976762))


### Fixed

* **deploy:** run alembic upgrade head before gunicorn start ([c2b3bd8](https://github.com/oasici/honeywell-sales-manager/commit/c2b3bd823e5ae7f7f3b78785d7b83389008029a5))

## 1.0.0 (2026-04-25)


### Added

* add /api/admin/seed-demo endpoint for Render data seeding ([ff7c335](https://github.com/oasici/honeywell-sales-manager/commit/ff7c335db537b0cd5ffa8da2e5ef71dcd4f3266c))
* add Content-Security-Policy headers + update axios to 1.14.0 ([746c33c](https://github.com/oasici/honeywell-sales-manager/commit/746c33c923e2081da3071c4b85fa17c4e40e7383))
* add receipt-style item summary in quote editor ([8c5978c](https://github.com/oasici/honeywell-sales-manager/commit/8c5978c760f6fbe9eb8c4f26efe57e02830df321))
* add Render Blueprint for one-click deployment ([97678af](https://github.com/oasici/honeywell-sales-manager/commit/97678afa6bf993ff0df7f3571d47a74362735fcd))
* add Vitest test framework + 36 snapshot tests ([fa61a6b](https://github.com/oasici/honeywell-sales-manager/commit/fa61a6be8487ed5ed4d5cfbe45c44f93c3869799))
* AI learning system - user corrections + training data export ([036ce00](https://github.com/oasici/honeywell-sales-manager/commit/036ce00cee0cc7aaa603db37229dffecea7fe176))
* AI pipeline optimization - timeout, config, analytics, JSONL export ([3ea980c](https://github.com/oasici/honeywell-sales-manager/commit/3ea980c7cf7de32d9ac1869a64d65e5a54f182d7))
* auto-quote pipeline from email to Honeywell PDF ([ac90da2](https://github.com/oasici/honeywell-sales-manager/commit/ac90da23d1a5295265aca5498704f823e81cfccf))
* close remaining gaps to 100% — arq queue, OR rules, pg_trgm, Redis cache ([d55a52f](https://github.com/oasici/honeywell-sales-manager/commit/d55a52f17e844b2330c98f730552140ea0077ec6))
* complete all Salesforce-equivalent frontend UIs ([c23f2e8](https://github.com/oasici/honeywell-sales-manager/commit/c23f2e8878183cdd991c20c119b1e4db3777ea11))
* complete engagement layer — transcripts, keywords, sequences, segments, coaching ([c77c826](https://github.com/oasici/honeywell-sales-manager/commit/c77c826cf89f30fb528e9edaf7f26be9835e8d49))
* complete tier-2 hardening — PDF async, audit batch, safe migrations ([1d8acf5](https://github.com/oasici/honeywell-sales-manager/commit/1d8acf5c85cfd6a51cc977308c26cd5f24c57421))
* **compliance:** PR-2.2 backend — audit trail filters + KVKK data export ([7508699](https://github.com/oasici/honeywell-sales-manager/commit/75086998c69bc3a7e4b9b4259e98b5c193470a5a))
* **compliance:** PR-2.2 frontend — audit filters UI + KVKK export page ([6313634](https://github.com/oasici/honeywell-sales-manager/commit/63136347cf62fa5eaa5e870716da6660b26560a1))
* **compliance:** PR-2.3 — KVKK auto-anonymization cron ([2f2b805](https://github.com/oasici/honeywell-sales-manager/commit/2f2b805c62360dd4bef0f29f55943e14646f1dea))
* customer health score system with growth & churn analysis ([867de85](https://github.com/oasici/honeywell-sales-manager/commit/867de8522d037403427e6e52c183304053b1c187))
* dark mode, multi-language support, font size adjustment ([b1443d1](https://github.com/oasici/honeywell-sales-manager/commit/b1443d1866b96dd0889c72665367699c8d61e400))
* **data-safety:** PR-2.1 — monthly DB restore drill (CI cron + script) ([2038fd4](https://github.com/oasici/honeywell-sales-manager/commit/2038fd474e8d6a8af2c55647795d9dc9ccd782af))
* email detail popup, auto-customer creation, review status labels ([aa36886](https://github.com/oasici/honeywell-sales-manager/commit/aa3688621016e34d81d5918221283ff09650038f))
* email mechanism overhaul - SEEN flag, 14-day window, daily limits ([77de7de](https://github.com/oasici/honeywell-sales-manager/commit/77de7de670c902648141633730e3017edf0e6882))
* email read/unread tabs, manual parse cooldown, approval-based customer creation ([ebc931c](https://github.com/oasici/honeywell-sales-manager/commit/ebc931ce1428c574934e034d3fc18bf1d39db74c))
* **frontend:** i18n coverage for UI strings and locale-aware formatting ([0c42f9f](https://github.com/oasici/honeywell-sales-manager/commit/0c42f9fa6dad9d8f6bbe217d78bdbf9302fb8fc3))
* full sandbox deployment — Sprint 0-8 complete ([5acc8ca](https://github.com/oasici/honeywell-sales-manager/commit/5acc8ca12312199a09f04c2b4fdcb04eabcfe6c4))
* implement 5 AI engineering recommendations ([26825e2](https://github.com/oasici/honeywell-sales-manager/commit/26825e2fb385546954c1665f586af572f1783200))
* implement real IMAP email polling in /poll endpoint ([6dbbd54](https://github.com/oasici/honeywell-sales-manager/commit/6dbbd5431672f4b479c01453c0a30f52a61f2ee0))
* integration hooks — calendar auto-link + e-sign contract (30/30 backlog complete) ([5605364](https://github.com/oasici/honeywell-sales-manager/commit/560536409d1570cd96da2746d3c96e2d480ac6af))
* modern chart redesign - gradient areas, rounded bars, vibrant doughnuts ([43e5282](https://github.com/oasici/honeywell-sales-manager/commit/43e52821bacbd4fa60f92412b5044617a25b9f91))
* modern UI overhaul - design system, cards, buttons, login, sidebar ([b95eeb3](https://github.com/oasici/honeywell-sales-manager/commit/b95eeb313aa8e22117fcc75e0c85e026a169a90e))
* modern UI redesign - email detail, product modal, customer cards ([4ff3f75](https://github.com/oasici/honeywell-sales-manager/commit/4ff3f758899bc9568623409b4c485304b911effa))
* **observability:** add Sentry tunnel endpoint for browser telemetry ([bd5246e](https://github.com/oasici/honeywell-sales-manager/commit/bd5246e0be67b65637a338649408a26f55b3aed2))
* **observability:** PR-0.2 structured logging + request_id propagation ([8ed5fdc](https://github.com/oasici/honeywell-sales-manager/commit/8ed5fdcb097d48b702e74b60d1656e14f1ff9851))
* **observability:** wire Sentry for backend + frontend with PII scrubbing ([ba2415b](https://github.com/oasici/honeywell-sales-manager/commit/ba2415b39a8d3b44030d6d0235650f8ae9ab1f2d))
* optimize email parser with AI engineer recommendations ([9ef248f](https://github.com/oasici/honeywell-sales-manager/commit/9ef248f6e31f1fef70815697f550c8a3f93b7dfc))
* PDF import for parts catalog + PDF-to-quote creation ([8f4bc4c](https://github.com/oasici/honeywell-sales-manager/commit/8f4bc4c5938c3f988adc51e7f6e6403d04d62d0e))
* Phase 2 - email sending, mobile, audit, reports, notifications, user mgmt ([c080269](https://github.com/oasici/honeywell-sales-manager/commit/c0802693e549e9354bdc3c126f0f63f58d1fb87f))
* **phase-2:** audit fixes, UI redesign, chart upgrade ([629b374](https://github.com/oasici/honeywell-sales-manager/commit/629b374e54582ec3e1e9fc6bb496b14b55a209ae))
* **phase-3:** 12 market-grade analytics features + ops dashboard ([ca67482](https://github.com/oasici/honeywell-sales-manager/commit/ca67482a1a4412c83e4309089cdf1eecd71526ed))
* premium B2B landing page — conversion-optimized marketing site ([20b16f6](https://github.com/oasici/honeywell-sales-manager/commit/20b16f6907472a6f12b3d2bb419c50161328a87c))
* product intelligence system with Excel import pipeline ([a429a68](https://github.com/oasici/honeywell-sales-manager/commit/a429a6850e23b0db7e700cdeedc8c156379ce679))
* **quality:** PR-3.1 — k6 load test suite + weekly CI run ([e6728cd](https://github.com/oasici/honeywell-sales-manager/commit/e6728cd40f4b9ea2185ea0c80bb414f7e2013aec))
* **quality:** PR-3.2 — Dependabot config + actual security audit gate ([1d89392](https://github.com/oasici/honeywell-sales-manager/commit/1d893926422311867a0a528b7948a2a1cdcdb6e5))
* **quality:** PR-3.4 — backend coverage gate at 45% floor ([0f55791](https://github.com/oasici/honeywell-sales-manager/commit/0f557914580a00be1ed9eee88ce97b7d9ac12ae6))
* **quality:** PR-4.1 — release-please automation + CHANGELOG.md ([923271c](https://github.com/oasici/honeywell-sales-manager/commit/923271c4d61a9d3da3a03f511d00de27497ff30a))
* replace trash icon with +/- row controls in quote items ([69a70ce](https://github.com/oasici/honeywell-sales-manager/commit/69a70ce38773d05b546c1d470ca595a1b9f0bdac))
* **resilience:** PR-1 — circuit breaker, rate limits, DB pool, Redis hardening ([92e65d3](https://github.com/oasici/honeywell-sales-manager/commit/92e65d3b251280d4deeb324d057142a24498197f))
* rewrite PDF template to match official Honeywell quote format ([1cea16e](https://github.com/oasici/honeywell-sales-manager/commit/1cea16ee91dfea0cb76d89b900a49304c07c9944))
* **sandbox:** v3 platform expansion + ERP + insights + hardening ([b0fc471](https://github.com/oasici/honeywell-sales-manager/commit/b0fc47106c81f75a4c92d99d9ccd38d19404550e))
* security hardening - rate limiting, input validation, account lockout ([1d4a8ba](https://github.com/oasici/honeywell-sales-manager/commit/1d4a8ba30116c6987d5023561101057aef5512bf))
* **security:** cookie-first auth + revocation + e2e ([520dfdc](https://github.com/oasici/honeywell-sales-manager/commit/520dfdc91561fc8bd020443e38b3cb8080a3a68c))
* **security:** Faz 1 — Critical + High guvenlik duzeltmeleri ([039f4e4](https://github.com/oasici/honeywell-sales-manager/commit/039f4e430379289ac8eac8a6183978890e1a7ba0))
* **security:** Faz 2 — auth hardening + DDL safety + CSP ([61b274c](https://github.com/oasici/honeywell-sales-manager/commit/61b274c90db80149ad75e124a65ce515cebd9e1f))
* **security:** Faz 3 — HttpOnly cookie auth + CSRF + test suite ([289f790](https://github.com/oasici/honeywell-sales-manager/commit/289f7906931a2b92de8a314071b3b78770f7135b))
* sprint delivery — notifications, health explainability, AI quality, security fixes ([86591d6](https://github.com/oasici/honeywell-sales-manager/commit/86591d668d54582cb76e30adb0ba52b5608e8a02))
* Türkçe karakter desteği + engagement prefix + çoklu iyileştirmeler ([23c8f48](https://github.com/oasici/honeywell-sales-manager/commit/23c8f4899acf6312fd2563388f274144c34e164d))
* upgrade to production-grade — semantic search, extended rules, AI signals, caching ([588c656](https://github.com/oasici/honeywell-sales-manager/commit/588c6569f934b660a7c69a05012a98784564e5e1))
* **users:** admin password reset endpoint ([b2fa6fd](https://github.com/oasici/honeywell-sales-manager/commit/b2fa6fd3921cb69711ba34b6dce24e758e6606e9))
* v2 AI layer + signals + tasks + analytics gaps — Salesforce parity push ([b896246](https://github.com/oasici/honeywell-sales-manager/commit/b89624689ca841a1033bdfbec81b1096278f5ddb))
* v2 architecture hardening — multi-worker, Redis, scheduler isolation ([e6dc6c2](https://github.com/oasici/honeywell-sales-manager/commit/e6dc6c28ddaf1fd4fbf2e919791e10bef3a6f1e1))
* **v3:** opportunities home + territories + integrations + competitive intel ([b87f91d](https://github.com/oasici/honeywell-sales-manager/commit/b87f91d1ccde6d2ddebc585f8ba897361f0efdc5))


### Fixed

* 10 code review fixes - security, performance, UX ([84cb73a](https://github.com/oasici/honeywell-sales-manager/commit/84cb73a9dae2c7871a4cda94c13d6e3b78fbb274))
* 15 code review findings - security, performance, correctness ([7be2b29](https://github.com/oasici/honeywell-sales-manager/commit/7be2b29949132a48ed40631b9ac0af0815152b73))
* 5 code review findings - schema validation, safe JSON, direct config ([d2b3c18](https://github.com/oasici/honeywell-sales-manager/commit/d2b3c1848e3990762db7783801bee8ae2d30840d))
* add customer delete endpoint + aggressive junk customer cleanup ([6dcdcbc](https://github.com/oasici/honeywell-sales-manager/commit/6dcdcbc74066da3bd1aec02ed758dcd51ceda957))
* add datetime import to seed endpoint ([6af285f](https://github.com/oasici/honeywell-sales-manager/commit/6af285f571c14cef390e954588249db1fa9e1d79))
* add null guards and error details for dashboard crash ([26bb3b2](https://github.com/oasici/honeywell-sales-manager/commit/26bb3b2c1905a0eee1a4dcce79f78dd357dc9c4e))
* add SPA fallback route for Render static site ([725f4fa](https://github.com/oasici/honeywell-sales-manager/commit/725f4fad606797b3f70926d91733e1c0d307fd1b))
* add trailing slashes to POST/PUT API endpoints ([b80803d](https://github.com/oasici/honeywell-sales-manager/commit/b80803de2b7696f304fd6a0a5f26c611ec0bac05))
* aggressive chart shrink + page break for print PDF ([b80243f](https://github.com/oasici/honeywell-sales-manager/commit/b80243f9d22b0ace66fa13d7f8fb6eed22e24a39))
* **api:** avoid cross-origin credentialed requests in prod ([cbcaeb0](https://github.com/oasici/honeywell-sales-manager/commit/cbcaeb05025efde65185d66743d7bd0794181d82))
* auto-add missing columns for existing Render DB ([fdbabfa](https://github.com/oasici/honeywell-sales-manager/commit/fdbabfa2211272571399c583ad75816fe7f881ce))
* auto-convert postgresql:// to postgresql+asyncpg:// for Railway ([8753d9a](https://github.com/oasici/honeywell-sales-manager/commit/8753d9a396104fec7c37a3bbbc41a8e7b192deaa))
* auto-migrate DB columns on startup for Railway deployment ([71b8df1](https://github.com/oasici/honeywell-sales-manager/commit/71b8df1dc0ee0e0a3618c8228876413289560359))
* auto-populate unit_price from L.P. when adding part to quote ([fa0eb89](https://github.com/oasici/honeywell-sales-manager/commit/fa0eb89d23fa4e8b537b6bfb0c9a7711915028c3))
* board KPI + badge contrast — visible in both light and dark mode ([5308ff8](https://github.com/oasici/honeywell-sales-manager/commit/5308ff8452c5c6a4411414221dbfd5d15c095a78))
* cast SparePart[] to NoPricePart[] via unknown ([6b97180](https://github.com/oasici/honeywell-sales-manager/commit/6b97180531f71b4afd58f2bd9e0f2408a49043c7))
* cleanup junk customers created by old auto-approve mechanism ([35ba4bb](https://github.com/oasici/honeywell-sales-manager/commit/35ba4bb920f37dfcd8abacb94dda87b1a3fb405e))
* **cockpit:** coerce HealthIndicator score/weight to float ([298f480](https://github.com/oasici/honeywell-sales-manager/commit/298f480fb8c837eea6a492cfa9a624b2e68e2336))
* **cockpit:** skip broken customers in health scoring instead of 500 ([9866a84](https://github.com/oasici/honeywell-sales-manager/commit/9866a8409d213e419e8938e6c7cc3396ff4dfc36))
* dark mode comprehensive upgrade - hover, tooltips, badges, dropdowns ([e07aef5](https://github.com/oasici/honeywell-sales-manager/commit/e07aef580c637c3bf5df35809dfe503f4a64920f))
* dark mode high contrast + font size only affects text not layout ([4f79eef](https://github.com/oasici/honeywell-sales-manager/commit/4f79eef2e1d62689cfda350fa4c4ece0edab61df))
* **deploy:** same-origin API via rewrite + specific CORS origin ([f71e8ed](https://github.com/oasici/honeywell-sales-manager/commit/f71e8ed6dde3bc325821eedff196fcba7682fb16))
* disable redirect_slashes + add trailing slashes to frontend API URLs ([8c196ad](https://github.com/oasici/honeywell-sales-manager/commit/8c196ada80e24d5ef8fea0a4099f9b4daa800269))
* don't cache empty Claude results, force fresh parse ([756ac25](https://github.com/oasici/honeywell-sales-manager/commit/756ac25358990180ab5536eacf482f7d87ca5ac5))
* download PDF via axios with JWT instead of window.open ([8d52e2e](https://github.com/oasici/honeywell-sales-manager/commit/8d52e2ebf47e4449642b8bd2f8f6aec1934f6c78))
* enable Tailwind 4 class-based dark mode — all dark: prefixes now work ([bd36171](https://github.com/oasici/honeywell-sales-manager/commit/bd361719230bc44fc9220a5b221c91f405957023))
* ENABLE_ALL_FEATURES flag + auto-sync all missing DB columns ([dabf03a](https://github.com/oasici/honeywell-sales-manager/commit/dabf03aa7b926a34c4b562916c2efae5067dd076))
* fetch full email detail in popup (body_text + parsed_data) ([ee15b70](https://github.com/oasici/honeywell-sales-manager/commit/ee15b7040d5a75415fa4852b0d9738c7f4ea2578))
* font scaling now works correctly with percentage-based zoom ([86cfc3c](https://github.com/oasici/honeywell-sales-manager/commit/86cfc3cd7013f27f6d18606554919d5a60489e44))
* font size offset targets only text elements, not component layout ([409c8ce](https://github.com/oasici/honeywell-sales-manager/commit/409c8ceb0b1109d5af48fa6a6a8175ce3243967c))
* **frontend:** handle stricter AxiosResponse header types after 1.15 bump ([9559329](https://github.com/oasici/honeywell-sales-manager/commit/9559329bafd4dc6b25c573e948a8a7d993bcfb34))
* graceful fallback for at-risk customers endpoint (500 → empty list) ([2b11ea0](https://github.com/oasici/honeywell-sales-manager/commit/2b11ea0a5478fc8568b333ffb1bc6ea2c12d330c))
* handle HTML email bodies in detail popup + strip tags in IMAP ([b4d5abd](https://github.com/oasici/honeywell-sales-manager/commit/b4d5abd5eb11505536ad76f36d76cef7f8ff5db7))
* harden login error handling + email mechanism overhaul ([439fcb8](https://github.com/oasici/honeywell-sales-manager/commit/439fcb85c8c6cc77b70a9d68d8f5079188374ac2))
* harden startup for Render deploy — prevent worker crash ([c138e04](https://github.com/oasici/honeywell-sales-manager/commit/c138e0438e930f4950f1733ef93c2e3353ddfa6d))
* hide Kaydet button on approved/sent quotes ([001f230](https://github.com/oasici/honeywell-sales-manager/commit/001f230514b52bb8a943346ed87ef8a7c2b7259c))
* improve regex parser to detect EBI-XXX and line-based part formats ([c9d0e20](https://github.com/oasici/honeywell-sales-manager/commit/c9d0e2066736576fa7328fa685b27bef493fe79b))
* invalidate Docker cache + add data/cache dir ([6eaa29d](https://github.com/oasici/honeywell-sales-manager/commit/6eaa29d5d419a8f78e02ceb3bb90176a2012e53f))
* isolate auto-migrations into separate transactions ([b1b50a1](https://github.com/oasici/honeywell-sales-manager/commit/b1b50a12d4b38e8acbf695da305551cb645aaefb))
* label contrast + UAT seed data for all features ([e1ddc75](https://github.com/oasici/honeywell-sales-manager/commit/e1ddc75f3485fd6e4723a0f0741b5e8a48292653))
* lightweight Dockerfile for Railway deploy (remove torch from build) ([9550dcf](https://github.com/oasici/honeywell-sales-manager/commit/9550dcf6ea556f6b57b34d112345aad50ad11d6d))
* limit IMAP poll to recent 2 days + max 5 emails per poll ([70d0be9](https://github.com/oasici/honeywell-sales-manager/commit/70d0be9a5d994a23a5a09a2bf0e8c70b417eb6a9))
* **observability:** accept HEAD on /api/health for UptimeRobot ([b43fa46](https://github.com/oasici/honeywell-sales-manager/commit/b43fa468993c9badbf2cd73142e668eb6b82860c))
* **observability:** add 200 root handler for UptimeRobot domain probe ([e7b6c19](https://github.com/oasici/honeywell-sales-manager/commit/e7b6c193fff6b8bfe52da62a5295ba3eee64a7c9))
* **observability:** downgrade RAG-missing logs from error to warning ([764b031](https://github.com/oasici/honeywell-sales-manager/commit/764b0317f40aca7da73d8e87caae783d039fcab6))
* parse blob error responses in PDF download + show actual error msg ([8dad3d0](https://github.com/oasici/honeywell-sales-manager/commit/8dad3d00fb3180159845b24a87c6fddcd2b669f5))
* PDF table extraction - Turkish char normalization + longest match first ([a044615](https://github.com/oasici/honeywell-sales-manager/commit/a044615af08e529ad654a1a2e93df0487875c03d))
* point frontend API to backend Railway URL via VITE_API_URL ([2de1e2c](https://github.com/oasici/honeywell-sales-manager/commit/2de1e2ceda4d1ba739db0475e399d8f4d34922cf))
* print PDF cuts off report sections - add break-inside-avoid ([40b735d](https://github.com/oasici/honeywell-sales-manager/commit/40b735d9f358c83fc0d1c672dcd07b7c8a909193))
* regenerate PDF on-the-fly if file is missing ([9a22a2b](https://github.com/oasici/honeywell-sales-manager/commit/9a22a2b6cb0c30dceabd9ea3daa7fdad9d00cea0))
* remove broken per-route limiter from login endpoint ([5bc7df3](https://github.com/oasici/honeywell-sales-manager/commit/5bc7df324f36aa4610c8dbe94f7aa7d506937d26))
* remove invalid 'source' field from Opportunity seed ([46607e3](https://github.com/oasici/honeywell-sales-manager/commit/46607e374e86841beef0253a899ceaa848a96e4e))
* remove invalid currency field from Contract seed ([12ae1f1](https://github.com/oasici/honeywell-sales-manager/commit/12ae1f160f36ec457e792e6f981e8787f9e12a0f))
* remove per-route slowapi limiter that broke login endpoint ([bb7e7e5](https://github.com/oasici/honeywell-sales-manager/commit/bb7e7e5be8cbcd4edf1c06a22f0fd248571a9416))
* remove plan field from web services in render.yaml ([38e264d](https://github.com/oasici/honeywell-sales-manager/commit/38e264d317402438a5286c383d9cb5811b3c847a))
* remove unused Cell import ([9a9e8c9](https://github.com/oasici/honeywell-sales-manager/commit/9a9e8c9dadf34acbd4a0bafd689d5ab75b752458))
* remove unused formatDate import in test ([8e4c82c](https://github.com/oasici/honeywell-sales-manager/commit/8e4c82cbd6c5bdf8a6332e9c39993ee44ea7381b))
* remove unused removeLastItem causing TS6133 build error ([6ee0233](https://github.com/oasici/honeywell-sales-manager/commit/6ee0233c21152e8f31720fdcdda4f228c51ef3b7))
* Render deploy — CORS + frontend proxy redirects ([6ad73a7](https://github.com/oasici/honeywell-sales-manager/commit/6ad73a70785fba1b71a1f5379beda110e8466a1e))
* reports charts + parts-without-price logic ([981d8f4](https://github.com/oasici/honeywell-sales-manager/commit/981d8f4f9cbe595f990a7e77a217246dcc0d530b))
* resolve all 13 audit findings (CRITICAL to MEDIUM) ([f3fc127](https://github.com/oasici/honeywell-sales-manager/commit/f3fc127f92bb7ab80d5f05775bd3a1a1be980bfb))
* restore trash icon for per-row item deletion ([a320302](https://github.com/oasici/honeywell-sales-manager/commit/a32030293b938826ebc824fda024fb696aedbefb))
* revert to claude-sonnet-4-20250514 model (confirmed working) ([a362c6d](https://github.com/oasici/honeywell-sales-manager/commit/a362c6d300c651b96de973565463786ef9ee3b06))
* review status based on catalog match, not just confidence ([62d9d0a](https://github.com/oasici/honeywell-sales-manager/commit/62d9d0a55df9c7c485c46363790f0b311f2b59d8))
* safer auto-migration + relaxed production validation ([1817c5b](https://github.com/oasici/honeywell-sales-manager/commit/1817c5b1c1decc304faf8af91926629d4652aee0))
* **security:** async-safe token revocation + single PDF semaphore ([e6f5f49](https://github.com/oasici/honeywell-sales-manager/commit/e6f5f4992cd961449d214ee880c6a4a450aad906))
* **security:** complete remaining audit findings — all severities addressed ([4100ce7](https://github.com/oasici/honeywell-sales-manager/commit/4100ce7122695e98a9f4de6df6cc10f3cfc1e9eb))
* **security:** comprehensive hardening — all audit findings addressed ([012edc1](https://github.com/oasici/honeywell-sales-manager/commit/012edc1ce1dae4d6c47870d03682b25a72e259e1))
* service worker stale cache + chart rendering ([3f54d3b](https://github.com/oasici/honeywell-sales-manager/commit/3f54d3be61a6ea24b0bfb2fbd4ec502fdc3758c4))
* split IMAP FLAGS and BODY.PEEK[] into separate fetch calls ([1ef7fff](https://github.com/oasici/honeywell-sales-manager/commit/1ef7fff7b2f4feebfb161647d0b5eeb353e71898))
* static EXPOSE in frontend Dockerfile for Railway ([43f107a](https://github.com/oasici/honeywell-sales-manager/commit/43f107a75622baf88f16a036585c0e107ff63f84))
* strip &nbsp; entities from all email bodies (not just HTML) ([c2c11ae](https://github.com/oasici/honeywell-sales-manager/commit/c2c11aedae04d3bc3205cf758e3d444b256be639))
* summary layout wrapping + approve uses PATCH not POST ([477596c](https://github.com/oasici/honeywell-sales-manager/commit/477596c829545891cfede9ace65eb52a4dd5737c))
* sync admin password from env on every startup ([aa55850](https://github.com/oasici/honeywell-sales-manager/commit/aa5585098ff2c4850fd9b6d5839d42fdb1c106ff))
* TS build errors - unused imports + queryFn type mismatch ([e1ed623](https://github.com/oasici/honeywell-sales-manager/commit/e1ed6235a879d659005444c6d397028656d25f1f))
* update parts import button label to show PDF support ([b83b563](https://github.com/oasici/honeywell-sales-manager/commit/b83b563bf6e59f5d095c47b21d58f2fc6ed44eda))
* use claude-3-5-sonnet model for email parsing (more widely available) ([b08a4e0](https://github.com/oasici/honeywell-sales-manager/commit/b08a4e02823cd0272a369e576b936119b7206344))
* use serve instead of nginx for Railway frontend deploy ([dc6cae3](https://github.com/oasici/honeywell-sales-manager/commit/dc6cae3caab19a5ddf6ac02ef85ff252895bca25))
* use static EXPOSE port, dynamic PORT only in CMD ([ed5f345](https://github.com/oasici/honeywell-sales-manager/commit/ed5f3456e02f012cb1fe38efdb2ad83d9753b932))
* use static port 8080 for nginx in frontend, remove envsubst ([2b2bddf](https://github.com/oasici/honeywell-sales-manager/commit/2b2bddfb00c0e029f88e5ae971ab4e8ccbe1d2dd))
* wire Claude parsing into manual email and reparse endpoints ([b1a684b](https://github.com/oasici/honeywell-sales-manager/commit/b1a684baeff1618aa17980ef2eee442b22b12d4f))
* wrap seed endpoint in try/except to show actual errors ([7ebb33f](https://github.com/oasici/honeywell-sales-manager/commit/7ebb33fc1e7a87632192da730850632d36bdb791))


### Security

* **deps:** bulk dep upgrade — 22 CVEs → 0 ([4476527](https://github.com/oasici/honeywell-sales-manager/commit/44765278e2d30d7c1097411f7b2b779d83437172))
* fix all 19 audit findings (CRITICAL to LOW) ([c074268](https://github.com/oasici/honeywell-sales-manager/commit/c0742680b0342fd30be32260c7d49c56fa4b5fc6))
* harden uploads, PDF parsing, webhooks, and seed ([c27cf8a](https://github.com/oasici/honeywell-sales-manager/commit/c27cf8af222d6e095d2f82ad846c6114ffc5e818))
* **hardening:** PR-4.2 — tighten CSP + add HSTS preload + COOP/CORP ([c67ea62](https://github.com/oasici/honeywell-sales-manager/commit/c67ea62e23b2d0773f6a4264548a7da48a5d739d))


### Changed

* extract service layer, add enums, encrypt credentials, improve frontend ([d177d86](https://github.com/oasici/honeywell-sales-manager/commit/d177d865f920f580a56f5a35b351700c7f0cf39b))


### Documentation

* complete technical documentation rewrite (3255 lines) ([88d0ac4](https://github.com/oasici/honeywell-sales-manager/commit/88d0ac45637d40553c1aaf0567dce70c0c30ddf0))
* **observability:** publish SLO targets + error budget policy ([ff6dded](https://github.com/oasici/honeywell-sales-manager/commit/ff6ddedd34ec6afde8230e6c80cf55f8b77225b0))
* **quality:** PR-3.3 — Game day runbook with 5 chaos scenarios ([72baae6](https://github.com/oasici/honeywell-sales-manager/commit/72baae6ba25078d3d2e5a7544d7e1a869c5d205a))
* **quality:** PR-4.3 — comprehensive .env.example + feature flag reference ([fe07d81](https://github.com/oasici/honeywell-sales-manager/commit/fe07d815bc7be0a9c172b96259b7a7232d526d5c))
* **quality:** PR-4.4 — single-page on-call playbook ([4db9559](https://github.com/oasici/honeywell-sales-manager/commit/4db9559f97124efb4f6cd9ce9d2a3b425d2da7ce))
* **quality:** PR-4.5 — customer communication templates ([0270918](https://github.com/oasici/honeywell-sales-manager/commit/02709187f4fb18c6c8c35f2a7ea84c123162b778))

## [Unreleased]

### Added — PR-4 Polish
- Comprehensive `.env.example` covering all 110 backend settings and 34
  feature flags, with inline notes on which are REQUIRED. Cross-references
  the auto-generated `docs/feature-flags.md` and the relevant runbooks.
- `docs/feature-flags.md` — auto-generated reference for every
  `FEATURE_*` flag with default, dependencies, consumer features, and
  rollback notes. Generator script at
  `backend/scripts/generate_feature_flags_doc.py`.
- `docs/runbooks/oncall-playbook.md` — single-page operator cheatsheet
  for the engineer paged at 03:00. Includes severity ladder, first-five-
  minutes loop, symptom→action table, and cross-links to the eight
  existing runbooks.
- `docs/customer-comms/` — three Turkish-language templates (incident,
  release, security disclosure) with `[BRACKETED]` slots and per-template
  internal checklists. Security template requires DPO + legal sign-off.

### Added — PR-3 Quality Gates
- k6 load test suite (`load-test/`): smoke / baseline / stress / soak.
  Weekly baseline run on CI against staging via
  `.github/workflows/load-test.yml`.
- Coverage gate at 45% in `backend-test` CI job. Current baseline ~47%.
- Dependabot config (`.github/dependabot.yml`) for pip / npm /
  github-actions with grouped dev-deps and ecosystem bundles.
- `pip-audit` and `npm audit` gates in CI — fail the build on any pip
  vulnerability and on HIGH/CRITICAL npm advisories.
- Game day chaos drill runbook (`docs/runbooks/game-day-scenarios.md`)
  with five staging-only scenarios.

### Added — PR-2 Data Safety
- Monthly DB restore drill GitHub Actions workflow
  (`.github/workflows/restore-drill.yml`) plus the
  `backend/scripts/restore_drill.sh` script. Both refuse to write to any
  URL containing `prod`/`production`.
- KVKK auto-anonymization scheduler task. Gated behind
  `KVKK_AUTO_ANONYMIZE_ENABLED`. Anonymizes EmailRequest PII >2 years
  and dormant Customer PII >3 years. Idempotent, audit-logged.
- Audit endpoint upgrades — `entity_id`, `since`/`until`, `action_prefix`
  filters; CSV export with 10k row cap; `/audit/data-export/{user_id}`
  for KVKK Article 15 right-of-access.
- Admin UI: filter form on `/audit`, new `/kvkk-export` page that lets
  the operator pick a user and download the JSON bundle.

### Added — PR-1 Resilience
- `claude_messages_create` wrapper (`backend/app/core/claude_client.py`)
  routes every Claude API call through `claude_breaker`. 8 service
  files migrated. Breaker fast-fails after 3 consecutive errors with
  30s recovery.
- Circuit breaker state surfaced on `/api/health` under `circuits`.
  Health status flips to `degraded` when any breaker is open.
- AI rate limit (60/min, per-user) and upload rate limit (10/min,
  per-user) sliding-window dependencies, applied to the `/ai` router
  and the four file-upload endpoints.
- Env-driven DB pool tuning (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
  `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`).

### Fixed
- `/api/health` was calling `await get_redis()` on a sync function; the
  surrounding `try/except` masked the resulting `TypeError` as
  `redis: error`. The endpoint now reflects real Redis connectivity.

### Security
- `pip-audit` gate is no longer wrapped in `|| true`. Vulnerable backend
  pins now fail CI; Dependabot opens the patch PRs.
- KVKK auto-anonymization is opt-in per environment and writes a
  `kvkk_*_auto_anonymize` audit row per affected entity.
- Restore drill script refuses to wipe any URL whose hostname or path
  contains `prod` / `production` (case-insensitive).

---

## [Pre-PR-1 baseline] - 2026-04-09

### Production Readiness baseline (before this changelog started)
- Sentry backend + frontend integration with PII scrubbing, Sentry tunnel
  endpoint for browser telemetry.
- Structured logging with `request_id` propagation.
- SLO targets and error budget policy published in `docs/SLO.md`.
- v3 platform expansion: opportunities home, territories, integrations,
  competitive intel.
- Cookie-first authentication with async-safe token revocation,
  single-PDF semaphore, render.yaml CORS hardening.
