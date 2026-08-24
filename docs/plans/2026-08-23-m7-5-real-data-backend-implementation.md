# M7.5 Real Data Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a raw-first, point-in-time-safe Alpaca + SEC EDGAR + Alpha Vantage ingestion backend for the 11-security Watchlist before M8.

**Architecture:** Keep the existing modular monolith and refactor the current provider code behind one ingestion coordinator. MinIO stores immutable source bytes; PostgreSQL stores durable job/outbox state, lineage, normalized facts, quality observations, and point-in-time query results; Celery/Redis provide at-least-once delivery only.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/TimescaleDB, MinIO, Redis, Celery/Beat, Pytest, Hypothesis, Docker Compose.

---

Implementation authority: `docs/plans/2026-08-23-m7-5-real-data-backend-design.md` and the linked approved Notion page. Execute RDB-1 through RDB-4 strictly in order. For every behavior: write the test, observe the expected failure, add the minimum implementation, run the focused suite, run related integration tests, update `docs/progress.md`, and commit.

## RDB-1 — Canonical ingestion foundation

### Task 1: Freeze domain enums and value objects

**Files:**
- Create: `backend/src/stock_platform/domain/ingestion/models.py`
- Create: `backend/tests/unit/ingestion/test_models.py`
- Modify: `backend/src/stock_platform/infrastructure/providers/base.py`

**Steps:**

1. Write failing parameterized tests for the approved job states, legal transitions, `CANCELLED`, retry classes, data purposes, coverage/session values, aware timestamps, and deterministic request hashes.
2. Run `uv run pytest backend/tests/unit/ingestion/test_models.py -q`; expect import/behavior failures.
3. Implement frozen enums/value objects. Hash canonical JSON with sorted keys; reject naive datetimes and floats in numeric request fields.
4. Run the focused test again; expect PASS.
5. Commit with `git commit -m "feat: define ingestion domain contracts"`.

### Task 2: Add Security master data and migrate Watchlist safely

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Create: `backend/migrations/versions/0025_ingestion_foundation.py`
- Modify: `scripts/seed_demo.py`
- Modify: `backend/src/stock_platform/api/routes/rest.py`
- Modify: `backend/tests/integration/db/test_migrations.py`
- Create: `backend/tests/integration/ingestion/test_security_master.py`
- Modify: `backend/tests/integration/api/test_watchlist.py` (or the existing Watchlist contract file discovered with `rg`)

**Steps:**

1. Add a failing upgrade test that snapshots existing Watchlist rows/configuration at 0024, upgrades to 0025, and proves every row resolves to exactly one `security_id` without changing the REST payload.
2. Add failing seed tests proving the 11 approved securities/identifiers/profiles are inserted once and user-modified Watchlist flags survive repeated seed runs.
3. Run the two focused tests; expect missing-table/column failures.
4. Add `security`, `security_identifier_version`, and `security_profile_version`; use effective and available time ranges plus append-only supersession links.
5. Add nullable `security_id`, backfill by normalized symbol, validate, then make it non-null. Keep `symbol` temporarily as a boundary/cache column if required by existing callers.
6. Resolve symbol to Security inside existing REST handlers; do not change the public OpenAPI contract.
7. Add append-only triggers to identifier/profile history and appropriate unique/PIT indexes.
8. Run migration, seed, Watchlist contract, and OpenAPI drift tests; expect PASS.
9. Commit with `git commit -m "feat: add versioned security master data"`.

### Task 3: Add durable ingestion state, leases, and outbox

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Modify: `backend/migrations/versions/0025_ingestion_foundation.py`
- Create: `backend/src/stock_platform/application/ingestion/jobs.py`
- Create: `backend/src/stock_platform/infrastructure/ingestion/job_store.py`
- Create: `backend/tests/unit/ingestion/test_job_state.py`
- Create: `backend/tests/integration/ingestion/test_job_store.py`

**Steps:**

1. Write failing property tests for every legal/illegal transition and stale lease/generation rejection.
2. Write failing concurrent integration tests proving one normalized request hash creates one active job and only one worker can claim a lease.
3. Run the focused tests; expect missing implementation/tables.
4. Add `ingestion_job`, `ingestion_attempt`, `ingestion_cursor`, `ingestion_dead_letter`, `ingestion_raw_link`, and `normalization_dispatch` with database constraints for states, generations, time order, and uniqueness.
5. Implement compare-and-set claim, heartbeat, completion, retry scheduling, cancellation, dead-letter, and cursor advancement operations as short transactions.
6. Ensure retry scheduling stores `next_attempt_at` and never calls `sleep`.
7. Run unit and PostgreSQL integration tests; expect PASS.
8. Commit with `git commit -m "feat: add durable ingestion job state"`.

### Task 4: Harden raw/normalized persistence and close the dispatch crash gap

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Modify: `backend/migrations/versions/0025_ingestion_foundation.py`
- Modify: `backend/src/stock_platform/infrastructure/providers/persistence.py`
- Create: `backend/src/stock_platform/application/ingestion/raw_writer.py`
- Create: `backend/src/stock_platform/workers/ingestion_tasks.py`
- Modify: `backend/src/stock_platform/workers/celery_app.py`
- Create: `backend/tests/integration/ingestion/test_raw_dispatch.py`
- Modify: `backend/tests/integration/db/test_append_only.py`

**Steps:**

1. Write failing tests for duplicate raw content, duplicate normalized records, UPDATE/DELETE rejection, MinIO-before-DB ordering, and a crash after raw commit but before Celery send.
2. Run the focused tests; verify failures expose current `DO UPDATE` and missing outbox behavior.
3. Add `record_key`, normalization rejection history, append-only triggers, and fact lineage constraints.
4. Replace `on_conflict_do_update` with `on_conflict_do_nothing` followed by deterministic lookup and equality verification; conflicting immutable content is an error.
5. Insert RawDataObject, IngestionRawLink, and NormalizationDispatch in one DB transaction after MinIO succeeds.
6. Add an idempotent dispatcher task that claims pending rows by lease and publishes/retries them; PostgreSQL remains authoritative if Redis restarts.
7. Run focused, append-only, and recovery suites; expect PASS.
8. Commit with `git commit -m "feat: make provider lineage immutable and durable"`.

### Task 5: Enforce both point-in-time predicates

**Files:**
- Modify: `backend/src/stock_platform/application/market_data/repositories.py`
- Modify: `backend/tests/integration/market_data/test_as_of_queries.py`
- Create: `backend/tests/property/test_ingestion_point_in_time.py`

**Steps:**

1. Add a failing example where `available_at <= decision_time` but `event_time > decision_time`; assert the row is invisible.
2. Add a Hypothesis test covering boundaries for both timestamps and revised records.
3. Run the focused tests and confirm current code leaks the future-event row.
4. Add `raw_data_object.event_time <= decision_time` to the repository and deterministic visible-version ordering.
5. Run focused and research/replay integration tests; expect PASS.
6. Commit with `git commit -m "fix: enforce complete point-in-time visibility"`.

### Task 6: RDB-1 acceptance

1. Run `uv run pytest backend/tests/unit/ingestion backend/tests/property/test_ingestion_point_in_time.py -q`.
2. Run `uv run pytest backend/tests/integration/ingestion backend/tests/integration/db backend/tests/integration/market_data -q`.
3. Run `uv run alembic -c backend/alembic.ini upgrade head` on a fresh database and on a 0024 fixture database.
4. Run `make seed` twice and compare Watchlist/security counts and configuration.
5. Run `make verify`.
6. Record exact commands, exits, counts, artifacts, and risks in `docs/progress.md`.
7. Commit with `git commit -m "docs: record RDB-1 verification"`; push and place the Linear issue in In Review, never Done before merge.

## RDB-2 — Alpaca market and news ingestion

### Task 7: Separate transport from persistence

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/providers/base.py`
- Modify: `backend/src/stock_platform/infrastructure/providers/alpaca.py`
- Modify: `backend/src/stock_platform/infrastructure/providers/alpaca_stream.py`
- Create: `backend/src/stock_platform/application/ingestion/coordinator.py`
- Modify: `backend/tests/contract/providers/test_live_adapter_contracts.py`
- Create: `backend/tests/unit/ingestion/test_coordinator.py`

**Steps:**

1. Write failing contract tests showing adapters return raw batches/events, pagination metadata, rate-limit metadata, and typed errors without writing MinIO/PostgreSQL.
2. Run tests; confirm the current adapter performs persistence and blocking retry internally.
3. Introduce the provider-neutral request/batch/event contract and route persistence/retry through the coordinator/job store.
4. Keep a narrow compatibility wrapper for existing fixture tests; do not duplicate HTTP stacks.
5. Parse and honor `Retry-After`; schedule retries instead of sleeping.
6. Run provider contract and fallback-policy tests; expect PASS.
7. Commit with `git commit -m "refactor: separate provider transport from ingestion"`.

### Task 8: Normalize and persist Alpaca bars/news

**Files:**
- Create: `backend/src/stock_platform/application/ingestion/normalizers/alpaca.py`
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Create: `backend/migrations/versions/0026_alpaca_market_news.py`
- Create: `backend/src/stock_platform/infrastructure/ingestion/fact_store.py`
- Create: `backend/tests/contract/providers/fixtures/alpaca/` recorded redacted fixtures
- Create: `backend/tests/contract/providers/test_alpaca_ingestion.py`
- Create: `backend/tests/integration/ingestion/test_alpaca_facts.py`

**Steps:**

1. Add failing recorded-contract tests for REST bars/news and WS bars/updated bars/trades/quotes/status.
2. Add failing lineage and append-only tests for MarketBar and NewsArticle.
3. Add `news_article`; evolve existing `market_bar` to require normalized lineage for new writes while preserving old rows.
4. Normalize Decimal values, aware UTC times, IEX/SIP coverage, sessions, article IDs, publication time, observation time, and `pit_eligible`.
5. Store trade/quote/status source records in Raw/Normalized only; do not add a MarketTrade table.
6. Run focused contract/integration tests; expect PASS.
7. Commit with `git commit -m "feat: ingest versioned Alpaca bars and news"`.

### Task 9: Add backfill, streaming recovery, and entitlement policy

**Files:**
- Modify: `backend/src/stock_platform/workers/schedules.py`
- Modify: `backend/src/stock_platform/workers/ingestion_tasks.py`
- Create: `backend/src/stock_platform/application/market_data/policy.py`
- Create: `backend/tests/unit/ingestion/test_alpaca_policy.py`
- Create: `backend/tests/integration/ingestion/test_alpaca_recovery.py`

**Steps:**

1. Write failing tests for daily/minute/news windows, pagination resume, disconnect recovery, updated-bar versions, market calendar DST/holiday/half-day behavior, and IEX/SIP/overnight separation.
2. Write failing policy tests proving missing SIP entitlement cannot be disguised as SIP and blocks replay/paper execution while research emits a typed gap.
3. Implement bounded low-priority backfill jobs and reconnect REST gap-fill.
4. Add explicit data-purpose routing and recorded entitlement metadata.
5. Run focused and alert/replay integration tests; expect PASS.
6. Commit with `git commit -m "feat: add entitlement-aware Alpaca scheduling"`.

### Task 10: RDB-2 acceptance

1. Run all Alpaca recorded-contract, ingestion, recovery, alert, and replay tests.
2. Run `make verify` and record exact evidence in `docs/progress.md`.
3. If credentials are absent, record the live test as explicitly skipped; never fabricate a result.
4. Commit with `git commit -m "docs: record RDB-2 verification"`; push and place the issue In Review.

## RDB-3 — SEC and Alpha Vantage ingestion

### Task 11: Generalize SEC identities, filings, and raw documents

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/providers/sec.py`
- Create: `backend/src/stock_platform/application/ingestion/normalizers/sec.py`
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Create: `backend/migrations/versions/0027_sec_alpha_facts.py`
- Create: `backend/tests/contract/providers/fixtures/sec/` recorded redacted fixtures
- Create: `backend/tests/contract/providers/test_sec_ingestion.py`
- Create: `backend/tests/integration/ingestion/test_sec_facts.py`

**Steps:**

1. Write failing tests for CIK resolution across all 11 securities and form selection by US/foreign filing regime.
2. Write failing tests for accession deduplication, amendments, acceptance-time availability, raw document lineage, required User-Agent, and a global 5 req/s limiter.
3. Replace the adapter's hard-coded symbol list with Security master lookup.
4. Persist raw submissions/documents and typed SecFiling metadata; do not add SecDocument.
5. Run SEC contract/integration tests; expect PASS.
6. Commit with `git commit -m "feat: ingest versioned SEC filings"`.

### Task 12: Add deterministic financial-fact mapping

**Files:**
- Create: `backend/src/stock_platform/domain/market_data/concepts.py`
- Create: `backend/src/stock_platform/application/ingestion/concept_mapping.py`
- Create: `backend/config/financial_concepts_v1.yaml`
- Create: `backend/tests/unit/ingestion/test_concept_mapping.py`
- Modify: `backend/tests/integration/ingestion/test_sec_facts.py`

**Steps:**

1. Write failing tests for EXACT, DERIVED, UNMAPPED, and AMBIGUOUS US-GAAP/IFRS examples, including provenance for derived inputs.
2. Implement a versioned deterministic mapping loader; prohibit LLM/network calls.
3. Persist FinancialFact versions with taxonomy, unit/currency, period, filing/accession, mapping status/version, normalized lineage, and supersession.
4. Emit EvidenceGap-compatible quality observations for unmapped/ambiguous facts.
5. Run focused and research numeric-verifier tests; expect PASS.
6. Commit with `git commit -m "feat: map SEC financial facts deterministically"`.

### Task 13: Add Alpha Vantage earnings calendar

**Files:**
- Create: `backend/src/stock_platform/infrastructure/providers/alpha_vantage.py`
- Create: `backend/src/stock_platform/application/ingestion/normalizers/alpha_vantage.py`
- Modify: `backend/src/stock_platform/settings.py`
- Modify: `.env.example`
- Modify: `backend/src/stock_platform/workers/schedules.py`
- Create: `backend/tests/contract/providers/fixtures/alpha_vantage/earnings_calendar.csv`
- Create: `backend/tests/contract/providers/test_alpha_vantage_ingestion.py`
- Create: `backend/tests/integration/ingestion/test_earnings_events.py`

**Steps:**

1. Write failing tests for CSV parsing, full-snapshot raw preservation, Watchlist filtering, Decimal estimates, symbol aliases, repeated snapshots, changed dates, and missing credentials.
2. Add `alpha_vantage_api_key` with placeholder-only examples and redaction coverage.
3. Add one daily full-market calendar job; persist versioned EarningsEvent facts linked to normalized records. Do not add an EarningsCalendarSnapshot table.
4. Run focused settings/security/provider/integration tests; expect PASS.
5. Commit with `git commit -m "feat: ingest Alpha earnings events"`.

### Task 14: RDB-3 acceptance

1. Run all SEC/Alpha unit, recorded-contract, integration, security, and research suites.
2. Run `make verify`; record exact evidence in `docs/progress.md`.
3. Run credential-gated live smoke only when explicitly configured; otherwise preserve the skip.
4. Commit with `git commit -m "docs: record RDB-3 verification"`; push and place the issue In Review.

## RDB-4 — Quality, release gates, replay, and operations

### Task 15: Add quality observations and deterministic reconciliation

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Create: `backend/migrations/versions/0028_ingestion_quality.py`
- Create: `backend/src/stock_platform/application/market_data/quality.py`
- Create: `backend/src/stock_platform/application/market_data/reconciliation.py`
- Create: `backend/config/data_quality_v1.yaml`
- Create: `backend/tests/unit/market_data/test_quality.py`
- Create: `backend/tests/unit/market_data/test_reconciliation.py`
- Create: `backend/tests/integration/ingestion/test_quality_history.py`

**Steps:**

1. Write failing tests for freshness, coverage, provider, delay, conflict, heartbeat health, missing interval, duplicate, revision, OHLC, volume, and IEX-vs-SIP non-conflict semantics.
2. Add the append-only DataQualityObservation table and versioned config loader.
3. Implement deterministic checks; no LLM and no persisted A/B/C/D grade.
4. Derive provider health from jobs/cursors/observations/metrics; do not add snapshot/result tables.
5. Run focused and append-only integration tests; expect PASS.
6. Commit with `git commit -m "feat: add deterministic ingestion quality gates"`.

### Task 16: Version corporate actions and ADR handling

**Files:**
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Modify: `backend/migrations/versions/0028_ingestion_quality.py`
- Modify: `backend/src/stock_platform/application/portfolio/corporate_actions.py`
- Create: `backend/tests/integration/ingestion/test_corporate_actions.py`
- Modify: `backend/tests/unit/portfolio/test_execution_timing.py`

**Steps:**

1. Write failing cases for split, cash/stock dividend, spin-off, symbol change, merger/acquisition, ADR ratio, currency preservation, and unsupported adjustment gaps.
2. Extend CorporateAction with normalized lineage and append-only versions without rewriting existing fill/ledger history.
3. Make query/adjustment code choose only actions visible at decision time and refuse implicit FX conversion.
4. Run ingestion and portfolio suites; expect PASS.
5. Commit with `git commit -m "feat: version corporate actions and ADR metadata"`.

### Task 17: Add replay, recovery, metrics, and release gates

**Files:**
- Create: `backend/src/stock_platform/application/ingestion/replay.py`
- Modify: `backend/src/stock_platform/infrastructure/observability/metrics.py`
- Modify: `scripts/recovery_probe.py`
- Create: `scripts/verify-ingestion.sh`
- Create: `backend/tests/integration/ingestion/test_replay.py`
- Create: `backend/tests/integration/ingestion/test_failure_recovery.py`
- Modify: `backend/tests/security/test_secret_redaction.py` (or the existing redaction test found with `rg`)
- Modify: `.github/workflows/weekly.yml`
- Modify: `docs/runbooks/recovery.md` (or the existing recovery runbook discovered with `rg`)

**Steps:**

1. Write failing replay tests proving a new normalizer can rebuild facts from MinIO without provider access and cannot overwrite old versions.
2. Write crash/recovery tests for every boundary: MinIO, raw transaction, outbox publish, normalize, fact insert, quality, and cursor.
3. Add metrics for job lag/state, cursor lag, dispatch backlog, normalization rejection, quality failures, rate-limit responses, and live-smoke skips.
4. Add redaction tests for headers, query keys, URLs, and WebSocket auth payloads.
5. Add opt-in SEC/Alpaca/Alpha live-smoke steps to weekly CI; absence of secrets is an explicit skip.
6. Add the operator verification script and runbook.
7. Run focused recovery/observability/security tests; expect PASS.
8. Commit with `git commit -m "feat: add ingestion replay and operations gates"`.

### Task 18: Final M7.5 acceptance

1. Start clean fixture services: `docker compose up -d --wait postgres redis minio`.
2. Upgrade an empty database to head and verify all migrations.
3. Upgrade a saved 0024 database fixture and prove Watchlist/history preservation.
4. Run `make seed` twice; capture counts and configuration hashes.
5. Run `./scripts/verify-ingestion.sh` twice; capture exit codes and artifacts.
6. Run `make verify` twice; capture exact backend/web pass/fail/skip counts.
7. Run live smoke only for credentials actually present; record provider, entitlement/feed, timestamp, and result without secrets.
8. Update `docs/progress.md` with all commands, exits, reports, skips, risks, commit, and PR.
9. Commit with `git commit -m "docs: record M7.5 acceptance evidence"`.
10. Push, open/reuse the M7.5 PR, perform professional review, wait for CI, and place RDB-4 In Review. Do not mark any issue Done before its merge evidence is attached.

## Final acceptance gate

- All four Linear issues were executed in order and merged/reviewed according to the agreed workflow.
- `make verify` passes twice from the final branch.
- Empty and upgrade migrations pass; seed/replay/verification are idempotent.
- Raw/normalized/fact histories reject UPDATE/DELETE at the database layer.
- Every domain fact traces through NormalizedRecord and RawDataObject to a MinIO object.
- Both point-in-time predicates are enforced and property-tested.
- Missing/invalid credentials, entitlements, provider outages, and schema drift return typed degraded/failure states and never Fixture fallback in API mode.
- No live broker, real-money path, new Agent, new MCP server, or M8 implementation appears in the diff.
- PR/CI/merge evidence is synchronized to Notion and Linear before M7.5 is marked complete.

## Engineering review coverage

### What already exists

- `GovernedHttpProvider`, Alpaca/SEC/FMP adapters, circuit breaking, recorded provider
  contracts, and typed unavailable/not-found semantics: refactor and reuse; do not fork.
- `MinioRawObjectStore` and fixture raw catalog: reuse for content-addressed raw writes
  and offline gates.
- `PostgresProviderRecordStore`, RawDataObject, NormalizedRecord, MarketBar, and
  CorporateAction: migrate and harden rather than recreate.
- Celery/Beat, durable application run state, recovery probes, OTel/Prometheus, and
  redaction: extend with ingestion jobs/outbox/metrics.
- Watchlist GET/POST/PATCH/DELETE: preserve the contract and resolve Security identity at
  the boundary.
- PointInTimeRepository: keep the seam and fix the missing event-time predicate.

### Code-path coverage target

```text
INGESTION CONTROL
[+] Watchlist / Beat -> enqueue(request_hash)
    +-- [TEST] duplicate + concurrent enqueue -> one active job
    +-- [TEST] invalid Security / missing credential -> typed terminal failure
    +-- [TEST] claim / heartbeat / completion -> CAS lease + generation
    +-- [TEST] stale worker -> rejected
    +-- [TEST] retry / Retry-After -> durable schedule, no worker sleep
    `-- [TEST] cancel queued/retry job -> CANCELLED; terminal cannot reopen

RAW-FIRST DELIVERY
[+] Provider -> MinIO -> Raw + Dispatch transaction -> Normalizer
    +-- [TEST] provider timeout/429/5xx -> retryable
    +-- [TEST] 401/403/schema drift -> fail or quarantine with raw retained
    +-- [TEST] MinIO failure -> no DB metadata/dispatch
    +-- [TEST] DB failure after MinIO -> content-addressed retry, orphan reported
    +-- [TEST] crash after DB commit/before Celery -> outbox recovers
    +-- [TEST] duplicate dispatch -> one normalized/fact version
    `-- [TEST] new normalizer -> replay appends, never overwrites

PROVIDER FACTS
[+] Alpaca
    +-- [TEST] REST pagination + WS reconnect/gap fill/updated bars
    +-- [TEST] IEX/SIP/overnight purpose isolation + entitlement absence
    `-- [TEST] historical news without observation time -> pit_eligible=false
[+] SEC
    +-- [TEST] 11-security CIK/form regime + User-Agent/5 req/s
    +-- [TEST] accession/amendment/acceptance-time versions
    `-- [TEST] EXACT/DERIVED/UNMAPPED/AMBIGUOUS fact mapping
[+] Alpha
    `-- [TEST] CSV raw snapshot + Watchlist alias/date revision + Decimal

QUERY / RELEASE
[+] PointInTimeRepository
    +-- [CRITICAL TEST] event_time > decision_time -> invisible
    +-- [CRITICAL TEST] available_at > decision_time -> invisible
    `-- [TEST] revised fact -> latest version visible at cutoff
[+] Quality / reconciliation
    +-- [TEST] gap/duplicate/revision/OHLC/volume + IEX/SIP non-conflict
    +-- [TEST] heartbeat health + versioned SLA configuration
    `-- [TEST] corporate action/ADR/currency without implicit FX
[+] Release
    +-- [TEST] empty + 0024 migration, seed/replay/verify idempotency
    +-- [TEST] secrets absent -> live smoke skipped, recorded contracts pass
    `-- [TEST] API failure/degraded never invokes FixtureAdapter
```

All identified gaps are now explicit tests in RDB-1 through RDB-4. There are no UI/E2E
flows in this backend-only milestone. Existing research/replay/alert/portfolio integration
suites act as downstream regression gates. No prompt or LLM behavior changes are planned,
so no new eval cases are required; the frozen release evaluation still runs via
`make verify`.

### Failure modes

| Path | Production failure | Planned test/error handling | User-visible result |
| --- | --- | --- | --- |
| enqueue/lease | duplicate Beat delivery or stale worker | concurrent/CAS integration tests | one job; stale completion rejected |
| provider | timeout, 429/5xx, invalid auth | contract tests + durable retry classification | Degraded/Unavailable, no fake values |
| raw write | MinIO succeeds but DB fails | crash injection + content-addressed retry | job retries; orphan metric, no normalization |
| dispatch | Redis/Celery unavailable after commit | durable outbox recovery test | backlog/Degraded; no lost raw data |
| normalize | schema drift or mixed numeric types | recorded malformed fixtures + quarantine/replay | typed gap/rejection, raw remains replayable |
| cursor | partial page succeeds before later failure | continuous-range cursor tests | replay resumes before the gap |
| stream | disconnect or silent stale connection | heartbeat/reconnect/gap-fill tests | health Degraded/Unavailable |
| PIT query | future event or late availability leaks | two critical boundary/property tests | future fact is invisible |
| entitlement | IEX mistaken for SIP | purpose-policy contract tests | research gap; replay/execution denied |
| corporate action | incorrect split/ADR/FX adjustment | versioned action/currency tests | explicit gap instead of silent arithmetic |
| credentials | key appears in URL/log/WS auth | security/redaction tests | secret suppressed; smoke skips safely |

No silent failure is left without a planned test and explicit state/error path.

### Review completion summary

- Step 0 Scope Challenge: scope reduced by removing five unconsumed tables and a parallel
  provider stack; durable outbox retained.
- Architecture Review: 5 issues found and incorporated.
- Code Quality Review: 5 issues found and incorporated.
- Test Review: coverage diagram produced; 14 gap categories added to the plan.
- Performance Review: 3 issues found and incorporated (blocking retry, write
  amplification, and unnecessary hot fact tables).
- NOT in scope: documented in the approved design and enforced by final diff checks.
- What already exists: documented above and selected for reuse.
- TODOS.md updates: 0 proposed; deferred FMP removal is intentionally not needed for M7.5.
- Failure modes: 0 unhandled critical gaps after plan amendments.
- Outside voice: skipped; this backend-only review used the approved Notion spec and
  direct repository inspection.
- Lake Score: 27/27 findings resolved into complete plan requirements.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | Backend scope already frozen by Notion approval |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAN | 27 findings incorporated, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | N/A | M7.5 has no UI scope |

- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED — requirements are ready for RDB-1 implementation.
