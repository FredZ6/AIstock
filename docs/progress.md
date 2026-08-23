# Progress

## M0 Foundation

Authoritative sources: Notion design baseline v0.2 and Codex executable engineering spec,
read on 2026-08-17. Linear milestone: M0 Foundation (FRE-5, FRE-6, FRE-7).

### Task 1 — complete; awaiting human review

- RED: `uv run pytest backend/tests/unit/test_settings.py -q` — exit 2; expected import failure
  because `stock_platform.settings` did not exist.
- RED: `CI=true pnpm --dir web test -- --run web/tests/home.test.tsx` — exit 1; expected
  import failure because `web/app/page.tsx` did not exist.
- GREEN: `uv run pytest backend/tests/unit/test_settings.py -q` — exit 0; 3 passed.
- GREEN: `CI=true pnpm --dir web test -- --run web/tests/home.test.tsx` — exit 0;
  1 passed.
- Integration: `make bootstrap` — exit 0; Python and pnpm lockfiles resolved with no provider
  credentials.
- Verification: `make verify` — exit 0; Ruff format/lint, Mypy, 3 backend tests, TypeScript,
  ESLint, 1 Vitest test, and Next.js production build passed.
- Report: this file (`docs/progress.md`).
- Risks: Docker/database verification is intentionally deferred to Task 3; no provider or live
  brokerage integration exists.

### Task 2 — complete; awaiting human review

- RED: `uv run pytest backend/tests/unit/domain/common -q` — exit 2; two expected import
  errors because the common domain package did not exist.
- GREEN: `uv run pytest backend/tests/unit/domain/common -q` — exit 0; 15 passed, including
  Hypothesis timezone/visibility and Decimal arithmetic properties.
- Integration: `make verify` — exit 0; Ruff format/lint, Mypy, 18 backend tests, TypeScript,
  ESLint, 1 Vitest test, and Next.js production build passed.
- Report: this file (`docs/progress.md`).
- Risks: monetary scale/rounding belongs to later instrument and ledger policies; the M0 value
  object preserves arbitrary exact Decimal values and rejects float input.

### Task 3 — complete; awaiting human review

- RED: `docker compose up -d postgres` initially exited 1 because local port 5432 was occupied;
  root cause was an existing system PostgreSQL, so the project mapping was isolated to 55432.
- RED: `uv run pytest backend/tests/integration/db -q` — exit 1; 9 expected failures for
  missing tables, enums, foreign keys, hypertables, and append-only triggers.
- Migration: `uv run alembic -c backend/alembic.ini upgrade head` — exit 0; applied
  `0001_core_schema` and `0002_timescale_hypertables`.
- GREEN: `uv run pytest backend/tests/integration/db -q` — exit 0; 9 passed.
- Empty-database rebuild: created dedicated `stock_platform_m0_verify`, upgraded from empty to
  head, ran database tests (9 passed), and upgraded to head again — combined exit 0.
- Idempotency: two consecutive `make seed` calls, two consecutive Alembic upgrades, and two
  consecutive `make verify` calls all exited 0.
- Final acceptance sequence: `make bootstrap; make seed; make verify; make verify` — exit 0.
  Each verify run passed Ruff format/lint, Mypy, 27 backend tests, TypeScript, ESLint, 1 Vitest
  test, and the Next.js production build. No tests failed or skipped.
- Report: this file (`docs/progress.md`).
- Risks: the M0 schema is intentionally foundational; business repositories, fixture datasets,
  provider adapters, and point-in-time query APIs begin at Task 4 and were not implemented.

#### M0 re-acceptance remediation — 2026-08-18

- SQLAlchemy metadata RED: `pytest -q backend/tests/unit/infrastructure/db/test_models.py` —
  exit 1 because `Base.metadata` contained zero tables. GREEN: exit 0; all canonical tables are
  now represented in `infrastructure/db/models/tables.py` and imported by Alembic.
- Metadata integration: `alembic check` against a freshly migrated database — exit 0; `No new
  upgrade operations detected`. The same check is now part of `make verify`.
- Append-only idempotency RED: the regression test observed all seven protected tables changing
  from 0 to 1 row. GREEN: writes now run inside a rolled-back outer transaction with savepoints
  around rejected mutations; the database test suite ran twice with 11 passed each time and all
  seven tables remained at 0 rows.
- Deterministic DecisionDiff RED: two tests failed with `NotImplementedError`. GREEN: 2 passed;
  `build_decision_diff` emits only changed fields in stable sorted order without an LLM path.
- External provenance RED: `market_bar` and `option_snapshot` lacked five required columns.
  GREEN: migration `0003_market_data_provenance` adds `raw_data_object_id`, `provider`,
  `feed_type`, `content_hash`, `raw_object_key`, point-in-time checks, and raw-data foreign keys;
  the focused integration test passed.
- Empty database: `alembic upgrade head` — exit 0; migrations 0001, 0002, and 0003 applied.
  Repeating `upgrade head` — exit 0.
- Isolated database validation: `alembic check` — exit 0; database tests run twice — exit 0,
  11 passed each; protected-table row counts remained zero.
- Final validation: two consecutive `make verify` runs — exit 0 each; Ruff format/lint, strict
  Mypy, Alembic drift check, 32 backend tests, TypeScript, ESLint, 1 Vitest test, and Next.js
  production build passed. Development database protected-table counts remained 6 before and
  after the second run; these six rows predate this remediation and were preserved because the
  tables are append-only.
- Installation and fixtures: `make bootstrap`, two consecutive `make seed`, and `make smoke` —
  exit 0 for every command; no provider credentials or live-broker configuration were used.

#### M0 second review remediation — 2026-08-18

- Non-empty migration RED: a real isolated database upgraded to 0002, inserted existing
  `market_bar` and `option_snapshot` fixture rows, then failed upgrading to head with
  `NotNullViolation` — exit 1.
- Non-empty migration GREEN: 0003 now adds nullable provenance columns, requires exactly one
  timestamp/feed-type-matched `RawDataObject`, copies its real provenance, and only then applies
  foreign keys and `NOT NULL`. The automated 0002→head regression test exits 0 with 1 passed and
  deletes its randomly named temporary database.
- DecisionDiff RED: explicit-null addition/removal tests failed because missing keys and `None`
  both used `Mapping.get()` — 3 failed. GREEN: each change now records `before_present` and
  `after_present`; 3 passed, including add-null and remove-null cases.
- Final validation: two consecutive `make verify` runs — exit 0 each; Ruff format/lint, strict
  Mypy, Alembic drift check, 34 backend tests, TypeScript, ESLint, 1 Vitest test, and Next.js
  production build passed with no failed or skipped tests.
- Idempotency evidence: protected-table counts remained 6 before and after the second full run;
  leaked `stock_platform_migration_*` databases remained 0.

## M1 Data Plane

Authoritative sources: Notion design baseline v0.2 and Codex executable engineering spec,
re-read on 2026-08-18. Linear milestone: M1 Data Plane (FRE-8, FRE-9, FRE-10).

### Task 4 — complete; awaiting human review

- RED: `uv run pytest backend/tests/contract/providers backend/tests/integration/market_data -q`
  — exit 2; expected import failures because the provider contracts and application repository
  did not exist.
- Fixture GREEN: `uv run pytest backend/tests/contract/providers/test_fixture_contracts.py -q`
  — exit 0; 5 passed, covering manifest licensing/provenance, five-symbol/scenario coverage,
  deterministic SHA-256 hashes, point-in-time fixture access, explicit missingness, and MinIO keys.
- Integration GREEN: `uv run pytest backend/tests/contract/providers
  backend/tests/integration/market_data -q` — exit 0; 8 passed. Late NVDA news remains invisible
  until `available_at`, naive `as_of` is rejected, and raw lineage is preserved.
- Related integration: `uv run pytest backend/tests/integration/db
  backend/tests/integration/market_data backend/tests/contract/providers -q` — exit 0; 20 passed.
- MinIO/PostgreSQL seed: first `make seed` — exit 0; 31 raw objects and 30 normalized records.
  Second `make seed` — exit 0; the same 31 object keys were written idempotently and 0 new
  normalized records were inserted.
- Full verification: `make verify` — exit 0; Ruff format/lint, strict Mypy, Alembic drift check,
  42 backend tests, TypeScript, ESLint, 1 Vitest test, and Next.js production build passed.
- Fixture data is synthetic and explicitly licensed/provenanced; it is not live market data or
  investment advice. No provider credentials or live-broker surface was added.

### Task 5 — complete; awaiting human review

- RED: `uv run pytest backend/tests/unit/market_data/test_fallback_policy.py
  backend/tests/contract/providers/test_live_adapter_contracts.py -q` — exit 2; expected import
  failures because the fallback policy and SEC/Alpaca/FMP adapters did not exist.
- Fallback GREEN: `uv run pytest backend/tests/unit/market_data/test_fallback_policy.py -q`
  — exit 0; 6 passed. Covered primary success, timeout fallback, stale fallback rejection,
  deterministic circuit opening, SEC-preferred conflict marking, and distinct not-found /
  not-supported / unavailable semantics.
- Provider contracts: `uv run pytest backend/tests/contract/providers -q` — exit 0;
  17 passed and 3 skipped. Mocked SEC/Alpaca/FMP contracts cover fixed read-only endpoints,
  bounded timeout/concurrency configuration, SEC User-Agent, conditional requests, raw-first
  persistence, exponential backoff with injected jitter, normalization failure, and adapter-to-
  fallback timeout flow. Three opt-in live tests skipped because `LIVE_PROVIDER_TESTS=1` was not
  set; each test names its credential/network requirement.
- Full verification: `make verify` — exit 0; Ruff format/lint, strict Mypy, Alembic drift check,
  60 backend tests passed, 3 live tests skipped, TypeScript, ESLint, 1 Vitest test, and Next.js
  production build passed.
- No live-broker endpoint, order path, trading credential, arbitrary URL, or fabricated zero value
  was added. Optional credentials are market/research-data-only and default to absent.

### Task 6 — complete; awaiting human review

- RED: `uv run pytest backend/tests/contract/mcp
  backend/tests/security/test_mcp_permissions.py -q` — exit 2; expected import failures because
  the MCP server packages did not exist.
- GREEN: the same command with `PYTHONWARNINGS=error` — exit 0; 11 passed. Tests cover the exact
  3/3/2 tool allowlists, required `symbol`/`as_of`, rejection of extra inputs, strict output
  schemas, read-only annotations, common structured envelope, lineage/citations, trace IDs,
  redacted repository errors, and denial of mutation/URL/SQL/shell capabilities.
- Contract drift: `python scripts/export_mcp_contracts.py --check` — exit 0. Frozen snapshots are
  stored in `contracts/mcp/{sec,market,analyst}.json` and checked by `make verify`.
- Official MCP Inspector 2.2.0 over Streamable HTTP:
  - SEC `tools/list` — exit 0 — only `get_company_facts`, `get_filings`,
    `get_filing_sections`.
  - Market `tools/list` — exit 0 — only `get_price_bars`, `get_company_news`,
    `get_option_aggregates`.
  - Analyst `tools/list` — exit 0 — only `get_estimates`, `get_target_consensus`.
  - Market `tools/call get_price_bars` for NVDA at `2026-08-16T00:00:00Z` — exit 0,
    `isError=false`; structured output returned three records whose newest `available_at` was
    before the cutoff, plus raw keys, hashes, citations, freshness, and trace ID.
  - Full evidence: `docs/testing/m1-mcp-inspector.md`.
- Full verification: `make verify` — exit 0; Ruff format/lint (including MCP servers), strict
  Mypy, MCP contract drift, Alembic drift, 71 backend tests passed, 3 opt-in live tests skipped,
  TypeScript, ESLint, 1 Vitest test, and Next.js production build passed.

### M1 final acceptance remediation — 2026-08-18

- Fixture collision RED: two valid analyst targets (AAPL and AMZN) shared the same payload-only
  hash, so MinIO held 31 objects while PostgreSQL held only 30 RawDataObject/NormalizedRecord
  rows. New tests failed with 2 failures and proved the raw objects omitted symbol/feed context.
- Fixture collision GREEN: fixture raw bytes and SHA-256 now cover `symbol`, `feed_type`, and
  payload. Seed reconciliation safely updated existing mutable raw/normalized fixture rows and
  inserted the missing AMZN record. First remediation seed — exit 0, 1 new normalized record;
  second seed — exit 0, 0 new records. Read-only counts now agree: MinIO 31, RawDataObject 31,
  NormalizedRecord 31. An empty-fixture-partition transaction proves first seed 31, second 0.
- Point-in-time fallback RED: a provider fallback whose `available_at` was one second after the
  decision cutoff was accepted. GREEN: it is now rejected as `future_fallback_rejected`; focused
  fallback tests exit 0 with 7 passed.
- MCP strictness RED: generated symbol schemas lacked the domain pattern. GREEN: every tool now
  publishes `^[A-Z.]{1,10}$`, still rejects extra properties, and contract snapshots were
  regenerated. Unused Python `mcp[cli]` extras were removed; core MCP runtime/HTTP behavior is
  unchanged.
- Focused final acceptance:
  - Task 4 command — exit 0; 21 passed, 3 opt-in live skipped.
  - Task 5 command — exit 0; 24 passed, 3 opt-in live skipped.
  - Task 6 command with warnings-as-errors — exit 0; 11 passed.
  - MCP contract drift check — exit 0.
- Official Inspector 2.2.0 was rerun after remediation: `get_price_bars` — exit 0,
  `isError=false`, status `ok`, 3 records, 3 hashes, latest `available_at` before cutoff, and a
  32-character trace ID.
- Final idempotency: two consecutive `make verify` runs — exit 0 each; Ruff format/lint, strict
  Mypy, Alembic and MCP contract drift checks, 73 backend tests passed, 3 opt-in live tests skipped,
  TypeScript, ESLint, 1 Vitest test, and Next.js production build passed.

### M1 independent-review remediation — 2026-08-18

- Point-in-time/provider RED: focused tests reproduced live records with `available_at` after the
  requested cutoff, future comparison leakage, FMP future estimate timestamps, SEC unknown-symbol
  exceptions, and the unsupported synthetic filing-section URL. GREEN: future primary/comparison
  records are rejected, FMP records use ingestion time plus `source_timestamp_unavailable`, SEC
  unknown symbols return typed `NOT_FOUND`, and live filing sections return `NOT_SUPPORTED`.
- Durable lineage RED: live adapters only wrote raw MinIO bytes. GREEN: every successful live
  response requires both raw-object and normalized-record persistence; migration
  `0004_normalization_version` adds the non-null normalization version and a versioned uniqueness
  constraint. Focused provider/schema/persistence suite — exit 0; 34 passed, 3 opt-in live skipped.
- MCP RED: `records` allowed arbitrary object properties and denied calls had no durable audit.
  GREEN: the envelope uses a closed union of nine strict record schemas, all nested objects reject
  extras, and completed/denied calls write append-only ToolCall/AgentEvent entries containing only
  tool name, outcome, and a SHA-256 request fingerprint. Focused MCP suite — exit 0; 12 passed.
- Locked layout/packaging: MCP servers now live under `backend/src/stock_platform/mcp_servers` and
  fallback policy under `application/market_data`. `uv build --wheel --out-dir
  /tmp/aistock-m1-remediation-dist` — exit 0; the wheel contains both locked package paths.
- Provider health: deterministic fallback/circuit snapshots are available from
  `FallbackPolicy.health()`. The HTTP route remains explicitly deferred to Task 14, so M1 does not
  start the control-plane/API scope early.
- Empty database: isolated PostgreSQL database upgraded through 0001→0004 — exit 0; repeated
  `upgrade head` — exit 0; `alembic check` — exit 0 with no migration drift. The isolated database
  was then dropped.
- Seed idempotency: two consecutive `make seed` runs — exit 0 each; PostgreSQL contains 31
  RawDataObject and 31 NormalizedRecord rows with one pinned version, `fixture-m1-v1`.
- Authority commands: Task 4 — exit 0, 26 passed/3 skipped; Task 5 — exit 0, 24 passed/3 skipped;
  Task 6 — exit 0, 11 passed. The exact optional-live command now exits 0 with 3 credential-gated
  skips and 15 deselected tests instead of pytest exit 5.
- Official Inspector 2.2.0: SEC/Market/Analyst `tools/list` each exited 0 with only the approved
  3/3/2 tools; every input and output object is strict. Market `get_price_bars` exited 0 with three
  cutoff-safe records. A request with a forbidden `sql` field was rejected (Inspector exit 5) and
  produced `mcp.tool.denied`; the stored audit leaked none of `symbol`, `as_of`, or `sql`.
- First complete verification after remediation: `make verify` — exit 0; Ruff format/lint, strict
  Mypy (56 source files), Alembic and MCP contract drift checks, 81 backend tests passed, 3
  credential-gated live tests skipped, TypeScript, ESLint, 1 Vitest test, and Next.js production
  build passed.
- Second consecutive `make verify` after recording evidence — exit 0 with the same 81 passed / 3
  skipped backend result and all Web checks/build passing, confirming the final verification loop is
  repeatable.

## M2 Agent Core

Authoritative sources: Notion design baseline v0.2 and Codex executable engineering spec,
re-read on 2026-08-18. Linear milestone: M2 Agent Core (FRE-11, FRE-12, FRE-13). Branch:
`feature/m2-agent-core`, created from `main@42a4eee53c0249074cf8cedf8112d3e1a139b095` in an
isolated worktree.

### Task 7 — complete; awaiting human review

- Baseline: `make bootstrap` and `make verify` — exit 0 after rerunning with the required sandbox
  network/localhost permissions; baseline verification passed 81 backend tests with 3 explicit
  credential-gated skips, 1 Vitest test, and the Next.js production build.
- RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest backend/tests/unit/agents/harness
  backend/tests/security/test_prompt_injection.py -q` — exit 2; 6 expected collection errors
  because `stock_platform.agents` did not exist. An earlier invocation without the local cache
  override exited 2 before collection due sandbox denial of the global uv cache and is not counted
  as behavioral RED evidence.
- GREEN: the same focused command — exit 0; 16 passed. Coverage includes immutable task scope and
  six pinned versions, aware cutoffs, tool/LLM/token/time/reflection budgets, repeated-action and
  no-progress termination, checkpoint recovery, monotonic/redacted event contracts, failure
  classification, human-only approval, completion verification, and prompt-injection quarantine.
- Related security integration: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest
  backend/tests/unit/agents/harness backend/tests/security -q` — exit 0; 18 passed.
- Full verification initially stopped at formatting (exit 2), then import sorting (exit 2), then a
  missing `jsonschema` typing stub (exit 2). Ruff formatting/import fixes and one precise
  `import-untyped` test-only annotation resolved those gate failures without changing behavior.
- Final verification: `make verify` — exit 0; Ruff format/lint, strict Mypy over 73 source files,
  Alembic drift check, 97 backend tests passed, 3 credential-gated live tests skipped, 1 Vitest
  test passed, and the Next.js production build passed.
- The Harness exposes only policy-controlled research tools. Retrieved text remains untrusted and
  cannot add order, notification, SQL, shell, URL, or credential capabilities. Task 7 adds no
  business graph and no live-trading path.

### Task 8 — complete; awaiting human review

- RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest backend/tests/unit/agents/research
  backend/tests/integration/research/test_daily_research.py -q` — exit 2; 4 expected collection
  errors because the Research Graph, research domain models, and persistence service did not exist.
- Implementation: added a compiled LangGraph 1.2.11 route for `Preflight → Planner → Parallel
  Collection → Normalize/Freshness/Lineage → Parallel Analysts → Evidence Judge → Reflect once →
  Deterministic Score & Confidence → InvestmentThesis → ResearchOpinion/ABSTAIN → Writer →
  CitationVerifier → DecisionDiff → Persist`. State reducers append Evidence, Claims, Gaps,
  Conflicts, Warnings, and route events without mutating prior state.
- First GREEN attempt — exit 1; 5 passed / 3 failed because the persistence-node delta overwrote
  the accumulated route in the stored result. Correcting the snapshot merge order produced 8
  passed.
- Persistence integration writes version-pinned Thesis, normalized ThesisEvidenceLink rows,
  ResearchOpinion, deterministic DecisionDiff, DecisionSnapshot, Claims, Gaps, and AgentEvents.
  The PostgreSQL integration join proves `Decision → Thesis → Claim → Evidence → DerivedMetric →
  NormalizedRecord → RawDataObject`, with every source record cutoff-safe.
- Stable-evidence idempotency RED: a second distinct Research Run over the same fixture failed with
  `UniqueViolation` on the deterministic Evidence ID. GREEN: existing immutable Evidence/Claim
  facts are reused without UPDATE or duplicate DerivedMetric rows; the focused regression exited 0
  with 1 passed.
- Final focused verification: the authority command above — exit 0; 9 passed, including exact-one
  Reflection, provider fallback, missing-data ABSTAIN, cancellation, same-run recovery, full DB
  lineage, AgentEvent sequencing, and cross-run Evidence reuse.
- Full verification initially stopped at formatter/lint/type gates while new files were normalized;
  after precise fixes, final `make verify` — exit 0: Ruff format/lint, strict Mypy over 87 source
  files, Alembic drift check, 106 backend tests passed, 3 credential-gated live tests skipped, 1
  Vitest test passed, and the Next.js production build passed.
- The research layer emits only ResearchOpinion and never PortfolioAction, OrderIntent, notification,
  or execution calls. Numeric scoring/confidence and DecisionDiff are deterministic and versioned.

### Task 9 — complete; awaiting human review

- RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest backend/tests/unit/research
  backend/tests/integration/research -q` — exit 2; three expected collection errors because the
  citation verifier, numeric verifier, and deterministic report renderer did not exist. An earlier
  online invocation was blocked by sandbox DNS before collection and is not counted as behavioral
  RED evidence.
- Implementation: material claims now carry optional Decimal-only numeric source metadata.
  `CitationVerifier` deterministically rejects unsupported, wrong-symbol, after-cutoff, stale, and
  conflicted citations. `NumericVerifier` recomputes cited values with explicit units and tolerances,
  including distinct percent and percentage-point semantics. `ReportRenderer` emits structured
  evidence relations, gaps, invalidation conditions, source provenance, deterministic DecisionDiff,
  all six pinned policy/model/prompt versions, and the paper-research product boundary.
- Safety gate: a report with any material citation or numeric failure is deterministically forced to
  `ResearchOpinion.ABSTAIN`; the graph persists it as `COMPLETED_WITH_LIMITATIONS`. No
  `PortfolioAction`, order, notification, live-broker, or policy-activation path was added.
- Focused GREEN: the authority command above — exit 0; 11 passed. Combined research unit command —
  exit 0; 14 passed. Full Agent Core unit/integration command — exit 0; 18 passed. Coverage includes
  freshness/cutoff, evidence conflict, wrong symbol, missing citation, Decimal-only values, explicit
  tolerance and units, unsupported fluent prose, complete report sections, and graph-level ABSTAIN.
- The first full verification stopped at Ruff formatting — exit 2; the second stopped at four
  fixable import-order/location findings — exit 2. Applying only Ruff's target-file formatting and
  import fixes resolved both non-behavioral failures.
- Final repeatability: two consecutive `make verify` runs — exit 0 each; 99 files formatted, Ruff
  lint passed, strict Mypy passed over 93 source files, Alembic reported no drift, 115 backend tests
  passed with 3 explicit credential-gated live-provider skips, 1 Vitest test passed, and TypeScript,
  ESLint, and the Next.js production build passed.
- Residual risk: verifier freshness limits and unit mappings are intentionally small deterministic
  v0.2 policy tables. Expanding them requires a later versioned-policy change; real-provider
  credential tests remain opt-in and are not required for Fixture Mode acceptance.

## M3 Alerts

Authoritative sources: Notion design baseline v0.2 and Codex executable engineering spec,
re-read on 2026-08-20. Linear milestone: M3 Alerts (FRE-14). Branch: `codex/m3-alerts`, created
from the merged and pushed `main@22aafcaf1e412a69ec4f682bc4c4810f88e0d262` in an isolated
worktree.

### Task 10 — complete; awaiting human review

- Baseline: `make bootstrap` — exit 0. Baseline `make verify` — exit 0 with 115 backend tests
  passed, 3 explicit credential-gated provider tests skipped, 1 Vitest test passed, and the Next.js
  production build passed.
- RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest backend/tests/unit/alerting
  backend/tests/integration/alerting -q` — exit 2 with 7 expected collection errors because the
  alerting services, stream/provider adapters, worker, and replay test surface did not exist. A
  prior invocation using the sandbox-denied global uv cache failed before collection and is not
  counted as behavioral RED evidence.
- Deterministic pipeline: added Decimal-only five-minute return, relative volume, Return Z,
  Volume Z, volatility Z, gap, breakout, and raw freshness/coverage/provider/delay/conflict
  features. A versioned multi-condition rule fires before any LLM use; cooldown-bucket UUIDv5
  identities keep alert IDs and metrics stable across replay.
- Durable delivery: Alpaca minute bars normalize into strict UTC/Decimal records, Redis Streams
  consumer groups carry events, and the worker ACKs only after PostgreSQL persistence. Migration
  `0005_alerts_and_outbox` adds AlertEvent, AlertThesisLink, AlertExplanation, a transactional
  NotificationOutbox, alert metrics, stream bar values, constraints, and deduplication indexes.
  One outbox row exists per alert key, with independent Telegram/Feishu/email retry state.
- Safety and resilience: duplicate and out-of-order data are idempotent, future-available data is
  rejected by the feature boundary, an active frozen Thesis/invalidation condition is linked to
  every alert, and LLM-disabled/timeout/error states remain visible without suppressing alert
  persistence or notification delivery. No brokerage, real-order, or live-funds surface was added.
- Systematic-debugging evidence: the first quality-gate inspection found only Ruff formatting,
  strict-Mypy narrowing/Redis typing, and two missing metadata index declarations. After minimal
  fixes, Ruff passed, strict Mypy passed over 110 source files, and `alembic check` reported no
  schema drift.
- Focused GREEN: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/unit/alerting backend/tests/integration/alerting -q` — exit 0; 14 passed. Coverage
  includes stable replay IDs/metrics, cooldown/deduplication, out-of-order events, duplicate
  delivery, Redis pending/ACK behavior, PostgreSQL outbox uniqueness, three-channel retry, and
  explanation disabled/timeout behavior.
- Full acceptance: `make verify` — exit 0; 117 files formatted, Ruff lint passed, strict Mypy
  passed over 110 source files, Alembic reported no drift, 129 backend tests passed with 3 explicit
  credential-gated provider skips, 1 Vitest test passed, TypeScript and ESLint passed, and the
  Next.js production build passed.
- Test report: this section is the durable command/exit-code report. Residual risk: real Alpaca
  stream and external Telegram/Feishu/email endpoints are intentionally not exercised without
  credentials; fixture replay and adapter retry contracts are authoritative for M3 acceptance.

### Task 10 independent-review remediation — 2026-08-20

- Durable ACK RED: the focused commit-order test exited 1 because Redis ACK occurred with no
  outer PostgreSQL commit. GREEN: `AlertWorker` now commits the complete bar/alert/explanation/
  outbox transaction before ACK and rolls back processing failures; a second database connection
  verifies the alert is visible before the message is considered complete. Outbox delivery-state
  RED also exited 1 with no commit event; the dispatcher now commits each saved channel result and
  rolls back persistence errors.
- Pending recovery RED: a replacement Redis consumer could only read `>` and the crashed
  consumer's entry remained pending. GREEN: `RedisMarketStream.read` first uses `XAUTOCLAIM` after
  the configured idle threshold, and the integration test proves ownership transfer followed by
  ACK reduces pending count from one to zero.
- Point-in-time RED: `recent_bars` accepted no evaluation cutoff and could include a record whose
  `available_at` was later than the decision context. GREEN: callers must supply `available_by`,
  the SQL applies `market_bar.available_at <= available_by`, and a future-available fixture is
  excluded.
- Explanation deadline RED: a blocking explainer held the worker for about 0.25 seconds despite a
  0.01-second budget. GREEN: the non-authoritative explainer runs behind a hard worker deadline;
  timeout returns in under 0.1 seconds, records `FAILED/TIMEOUT`, preserves the deterministic alert,
  commits, and ACKs.
- Focused remediation suite: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/unit/alerting backend/tests/integration/alerting -q` — exit 0; 19 passed. The same
  command inside the restricted sandbox first reported 3 localhost-permission setup errors after
  16 unit tests passed; rerunning unchanged with local PostgreSQL/Redis permission passed all 19.
- Static gates: Ruff format check, Ruff lint, and strict Mypy — exit 0; 110 source files checked.
  Alembic `upgrade head` executed twice — exit 0 both times; `alembic check` — exit 0 with no drift.
- Final acceptance: `make verify` — exit 0; 117 files formatted, Ruff lint passed, strict Mypy
  passed over 110 source files, Alembic and MCP contract drift checks passed, 134 backend tests
  passed with 3 explicit credential-gated provider skips, TypeScript and ESLint passed, 1 Vitest
  test passed, and the Next.js production build passed.
- Residual risk: real Alpaca streaming and external notification endpoints remain intentionally
  credential-gated. Python cannot forcibly terminate an arbitrary blocked explainer thread; the
  worker deadline prevents pipeline blocking, while provider-side cancellation remains the
  explainer adapter's responsibility.

### Task 10 final P1 merge-gate remediation — 2026-08-21

- Raw-first Alpaca ingestion RED: the focused normalizer suite exited 1 with 3 failures because
  the normalizer had no required object-store boundary and rejected Alpaca updated-bar messages
  (`T=u`). GREEN: `AlpacaStreamNormalizer` now requires a `RawObjectStore`, writes the exact source
  bytes before returning a publishable bar, and accepts only bar/update messages; 3 tests passed.
- Corrected-market-data RED: the real PostgreSQL/MinIO probe exited 1 with 2 failures / 1 pass:
  same-event-time revisions both appeared in the feature window, `conflict=True` returned as false,
  and an out-of-order record had no database lineage. GREEN: migration
  `0006_alert_market_bar_hardening` adds the non-null conflict fact and canonical-revision index;
  cutoff-safe SQL selects one deterministic latest-available revision per event time, while every
  distinct raw/update/out-of-order payload persists RawDataObject → NormalizedRecord → MarketBar.
  The corrected-bar, lineage, and exact MinIO-byte tests then passed 3/3.
- Session gap RED: the PostgreSQL test exited 1 because the store exposed no gap context. GREEN:
  gap is calculated only from the actual 09:30 America/New_York minute open and the latest available
  prior regular-session 15:59 close; a truncated six-bar intraday window cannot invent a gap. The
  focused database test and four Decimal feature tests passed.
- Thesis/Evidence RED: the focused test exited 4 at collection because no concrete resolver
  existed. GREEN: `PostgresAlertContextResolver` chooses the latest matching Thesis with linked
  Evidence whose complete RawDataObject → NormalizedRecord → DerivedMetric → Evidence chain is
  available and created by the decision cutoff. Future and wrong-symbol contexts are excluded; the
  focused PostgreSQL test passed. A worker RED test also proved it previously resolved at event time;
  GREEN resolves at the ingestion/decision cutoff and the worker suite passed 4/4.
- Concurrent delivery RED: two dispatchers on separate PostgreSQL connections both sent the same
  pending outbox row (2 calls; focused test exit 1). GREEN: due rows are transactionally claimed with
  `FOR UPDATE SKIP LOCKED`; the same two-connection test exits 0 with one delivered result and one
  adapter call. The stable alert key remains in the payload for downstream idempotency.
- Combined alerting regression: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest -q
  backend/tests/unit/alerting backend/tests/integration/alerting/test_market_replay.py` — exit 0;
  27 passed against real PostgreSQL, Redis, and MinIO.
- Migration repeatability: `uv run alembic -c backend/alembic.ini upgrade head` from 0005 — exit 0;
  the identical command at head — exit 0. `alembic check` inside verification reported no drift.
- Complete acceptance: `make verify` — exit 0; 118 files formatted, Ruff lint passed, strict Mypy
  passed over 110 source files, Alembic and MCP contract drift checks passed, 142 backend tests
  passed with 3 explicit credential-gated provider tests skipped, TypeScript and ESLint passed,
  1 Vitest test passed, and the Next.js production build completed successfully.
- Remaining external boundary: real Alpaca and Telegram/Feishu/email credential tests remain
  intentionally opt-in. Fixture Mode, the real local PostgreSQL/Redis/MinIO pipeline, deterministic
  alert generation, point-in-time lineage, and concurrent outbox claiming satisfy the M3 merge gate;
  no live-broker or real-money path exists.

### Task 10 P2 explainer-output remediation — 2026-08-21

- Runtime-validation RED: the focused worker command exited 1 with 6 failures. `None` produced a
  generic explanation error, while a non-string, empty text, whitespace-only text, over-4000-character
  text, and untrimmed valid text could cross the explainer boundary without the required validation.
- GREEN: the explainer boundary now requires a real string, trims surrounding whitespace, rejects
  empty output, and enforces a 4000-character normalized limit. Invalid output is durably classified
  as `FAILED/INVALID_OUTPUT`; it cannot suppress the deterministic alert, transaction commit, or
  stream ACK. Focused output tests — exit 0; 6 passed / 4 deselected.
- Alerting regression: strict Mypy and Ruff — exit 0; full alerting unit plus real
  PostgreSQL/Redis/MinIO integration command — exit 0; 33 passed.
- Complete acceptance: `make verify` — exit 0; Ruff format/lint, strict Mypy, Alembic and MCP
  contract drift checks passed, 148 backend tests passed with 3 explicit credential-gated provider
  tests skipped, TypeScript and ESLint passed, 1 Vitest test passed, and the Next.js production build
  completed successfully.

## M4 Portfolio

Authoritative sources: Notion design baseline v0.2 and Codex executable engineering spec,
re-read on 2026-08-21. Linear milestone: M4 Portfolio (FRE-15, FRE-16). Branch:
`codex/m4-portfolio`, created from synchronized `main@aae517091aa1052559154cb46d5481ce8660f7dd`
in an isolated worktree. Scope in this record is Task 11 only; Task 12 has not started.

### Task 11 — complete; awaiting human review

- M3 closure: FRE-14 was marked Done, Linear M3 Alerts reached 100%, and Notion received PR #2 / final
  merge commit `aae5170` / final verification evidence before M4 began.
- Bootstrap: the first `make bootstrap` exited 2 after creating `.venv` because the restricted sandbox
  could not resolve `files.pythonhosted.org`; the unchanged command with dependency-network permission
  exited 0 and installed the pinned Python and pnpm lockfiles.
- Baseline: `make verify` — exit 0; 148 backend tests passed with 3 explicit credential-gated provider
  skips, and all Python, database, contract, Web, and production-build gates passed.
- Unit RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest backend/tests/unit/portfolio -q`
  — exit 2 with two expected collection errors because the portfolio application/domain packages did
  not exist. Minimal domain implementation then made the same command exit 0 with 9 passed, including
  Hypothesis ledger and fill-timing properties.
- Integration RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/integration/portfolio -q` — exit 2 with two expected collection errors because the
  Corporate Action service and PostgreSQL accounting store did not exist. After migration/service
  implementation, the first run had 3 passed / 1 fixture failure: the fixture omitted `ingested_at`
  and correctly violated `available_at <= ingested_at`. Explicit UTC ingestion time produced 4 passed.
- Paper execution: a pinned `ExecutionPolicyVersion` deterministically controls half-spread, slippage,
  per-share/minimum fees, next-eligible-bar timing, and available-volume participation. Replays sort and
  deduplicate bars, generate stable UUIDv5 fills, reject unapproved orders, and only fill bars strictly
  later than the aware UTC decision time. All quantities, prices, fees, ratios, and NAV values use
  `Decimal`; binary float and naive time are rejected.
- Accounting: each funding, fill, dividend, and correction produces balanced debit/credit journal
  entries. Application persistence rejects an unbalanced journal before any write, duplicate fills and
  entries are idempotent, buys cannot make cash negative, and positions/NAV rebuild only from immutable
  PaperFill and CashLedger facts. Corrections append an inverse Fill and inverse entries without updating
  history.
- Reversal RED/GREEN: the PostgreSQL test initially exited 1 because the normal fill trigger rejected a
  valid opposite-side reversal. Migration `0008_paper_fill_reversals` validates the original immutable
  fill, exact inverse identity, zero reversal fee, and later timestamp; the focused test then exited 0
  with 1 passed. A separate store-boundary RED proved unbalanced entries were accepted; the minimal
  pre-write balance check made the same focused test pass.
- Corporate Actions: `corporate_action` stores raw-object lineage and provider/feed/time/hash/key facts.
  Queries require `effective_at <= as_of` and `available_at <= as_of`; split ratios adjust derived
  positions and cash dividends append idempotent balanced entries. Naive cutoffs are rejected.
- Database migrations: `0007_paper_execution_ledger` adds OrderIntent, PaperOrder, hardened PaperFill,
  double-entry CashLedger fields, CorporateAction lineage, constraints, and a database trigger rejecting
  unapproved or non-future fills. It safely backfills legacy append-only rows. `0008` adds strictly
  validated reversal fills. Two consecutive `alembic upgrade head` calls and `alembic check` exited 0
  with no drift.
- Migration regression: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/integration/db/test_migrations.py -q` — exit 0; 2 passed. It covers isolated empty/legacy
  upgrade paths, 0006→head backfill, repeated head, and retained append-only rejection. The combined Task
  11 command over unit, portfolio integration, and migration tests exited 0 with 15 passed.
- Full verification remediation: the first `make verify` exited 2 on one Ruff formatting difference.
  The second passed format/lint, strict Mypy over 124 source files, and Alembic drift, then exited 2 with
  160 passed / 3 skipped / 2 failed because the M0 append-only test still inserted newly hardened facts
  with `DEFAULT VALUES`. Replacing that obsolete setup with valid approved-order and balanced-ledger
  fixtures made the focused append-only suite exit 0 with 3 passed.
- Complete acceptance: `make verify` — exit 0; 134 files formatted, Ruff lint passed, strict Mypy passed
  over 124 source files, Alembic and MCP contract drift checks passed, 162 backend tests passed with 3
  explicit credential-gated provider tests skipped, TypeScript and ESLint passed, 1 Vitest test passed,
  and the Next.js production build completed successfully.
- Safety boundary: this is deterministic local paper simulation only. No live-broker endpoint,
  credential, switch, real order, real funds, LLM execution, or Task 12 portfolio-decision path was
  introduced. Real research-provider credentials remain optional and unrelated to Task 11 acceptance.

### Task 11 independent-review P1 remediation — 2026-08-21

- Incremental fills RED: the focused unit test exited 1 because `execute` accepted no prior-fill
  state; the reproduced 10-share order filled 3 shares and then another 10 from an incremental bar.
  GREEN: callers provide immutable prior fills, consumed revisions are skipped, and only the true
  remainder can fill. Database migration `0009_paper_fill_quantity_guard` serializes inserts on the
  PaperOrder row and rejects net cumulative quantity above the order quantity.
- Rejected-intent bypass RED: PostgreSQL accepted a PaperOrder that changed a rejected OrderIntent
  into an approved order. Migration `0010_paper_order_intent_guard` requires all duplicated order
  facts and risk approval to match on INSERT/UPDATE and enforces status consistency.
- Reversal RED: application code and PostgreSQL allowed a second timestamped reversal of the same
  Fill. Application accounting now rejects a different second reversal while preserving exact
  redelivery idempotency; migration `0011_unique_paper_fill_reversal` adds a partial unique index on
  non-null `reversal_of_id`.
- Split/NAV RED: replaying one split on an already adjusted Position doubled the quantity again, and
  NAV rebuilt a 2-for-1 fixture as 1500 instead of 2000. Positions now retain applied split IDs;
  point-in-time reconstruction orders visible Fill and split facts deterministically, excludes
  reversed Fill pairs, and applies each split once. The corrected fixture rebuilds cash 1000 plus
  positions 1000 for NAV 2000.
- Portfolio isolation RED: NAV accepted a Fill from another portfolio and inflated a 2000 fixture to
  12000. NAV now rejects any visible Fill whose `portfolio_id` differs from the authoritative Ledger.
- Revision determinism RED: two Bar revisions with identical event/availability times produced the
  same Fill ID but prices 100 versus 101 when input order changed. `ExecutionBar` now requires a
  normalized content hash; canonical revision selection and Fill identity include that stable hash,
  while conflicting facts under one revision identity are rejected.
- Trigger interaction debugging: the first combined portfolio run exited 1 after 20 passes because
  PostgreSQL executes the cumulative BEFORE INSERT trigger before `ON CONFLICT DO NOTHING`, causing
  exact redelivery to look like an overfill. Migration `0012_idempotent_fill_guard` first validates an
  existing idempotency key against every immutable Fill fact; exact matches reach unique-key dedup,
  while collisions with different facts fail. The complete portfolio suite then exited 0 with 21
  passed.
- Migration and append-only acceptance: isolated migration regression exited 0 with 2 passed;
  consecutive `alembic upgrade head` calls and `alembic check` exited 0 with no drift. The combined
  portfolio, migration, and append-only command exited 0 with 26 passed.
- First complete regression: `make verify` exited 0; 138 files passed Ruff formatting, Ruff lint and
  strict Mypy passed over 124 source files, Alembic/MCP drift checks passed, backend reported 170
  passed / 3 explicit credential-gated skips, TypeScript/ESLint passed, Vitest reported 1 passed, and
  the Next.js production build completed successfully.
- Completion-gate repeat: a second unchanged `make verify` exited 0 with the same 170 backend passed /
  3 explicit credential-gated skips, 1 Vitest passed, and all format, lint, type, migration, contract,
  and Next.js production-build gates green.
- Scope remains Task 11 only. No Task 12 agent/risk/benchmark implementation, Live Broker surface,
  real-funds path, or LLM execution authority was added.

### Task 11 P2 order-status remediation — 2026-08-21

- Incremental persistence RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/integration/portfolio/test_paper_accounting_store.py::test_incremental_fills_advance_persisted_order_status
  -q` — exit 1; after persisting a 3-share partial fill and a later 7-share fill for a 10-share order,
  PostgreSQL still reported `PARTIALLY_FILLED` instead of `FILLED`.
- GREEN: `PostgresPaperAccountingStore.persist` now recomputes PaperOrder status in the same transaction
  from the authoritative persisted net quantity: ordinary immutable fills add quantity and reversal
  fills subtract it. Exact redelivery remains idempotent, and a fully reversed order returns to
  `PENDING` without mutating fill history. The focused command exited 0 with 1 passed.
- Related regression: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest
  backend/tests/unit/portfolio backend/tests/integration/portfolio
  backend/tests/integration/db/test_migrations.py backend/tests/integration/db/test_append_only.py -q`
  — exit 0; 27 passed, including a persisted-status assertion that a complete fill reversal returns the
  order to `PENDING` without changing immutable history.
- Complete acceptance: `make verify` — exit 0; 138 files passed Ruff formatting, Ruff lint and strict
  Mypy passed over 124 source files, Alembic/MCP drift checks passed, backend reported 171 passed / 3
  explicit credential-gated skips, TypeScript/ESLint passed, Vitest reported 1 passed, and the Next.js
  production build completed successfully.

### FRE-15 acceptance and Task 12 portfolio decision graph — 2026-08-21

- FRE-15 independent acceptance: a fresh `make verify` exited 0 with 171 backend tests passed and 3
  explicit credential-gated provider skips; all Python format/lint/type, Alembic/MCP drift, Web
  type/lint/Vitest, and Next.js production-build gates passed. Linear FRE-15 was moved to Done with
  commit `a92824277c180dcb50b3b4bcb42c4dac1eb41deb` and its verification evidence; FRE-16 was then moved
  to In Progress before Task 12 implementation began.
- Portfolio module RED: the authoritative Task 12 unit/integration selection initially exited 2 during
  collection because allocation, benchmarks, metrics, risk, and the portfolio agent graph did not yet
  exist. The minimal implementation separates ResearchOpinion from PortfolioAction, freezes research
  inputs, constructs deterministic target proposals, runs a no-tool risk gateway, creates only approved
  pending paper orders, executes at the next eligible bar, and rebuilds ledger/NAV plus Cash, QQQ,
  equal-weight, and momentum benchmark returns under the same cost convention.
- Deterministic risk gateway: policy-version-pinned decisions enforce position, gross exposure, cash
  reserve, daily turnover, stale research, missing prices, earnings blackout, drawdown, duplicate
  intents, and incomplete evidence. Model output is only a proposal: it cannot create a Fill unless a
  deterministic approved/clipped RiskDecision exists. The graph permits zero external tool calls, at
  most three LLM calls, and at most 60 seconds.
- Risk-state propagation RED/GREEN: the focused rebalance test first exited 1 because
  `PortfolioDecisionGraph.run` did not accept `daily_turnover` or `drawdown`. Adding Decimal-validated
  state fields and passing them to `PortfolioRiskSnapshot` made the unchanged command exit 0 with 1
  passed. The portfolio suite initially reported 30 passed / 9 infrastructure failures because the
  restricted sandbox blocked localhost PostgreSQL; the identical database-enabled command exited 0
  with 39 passed.
- Risk audit migration: `0013_risk_decision_audit` adds append-only RiskDecision facts, policy/research
  lineage, reason codes, and a non-null unique OrderIntent foreign key. A database trigger rejects an
  order whose portfolio, symbol, decision time, or approval does not match its deterministic risk
  decision. Migration `0014_risk_constraint_names` normalizes generated constraint names so Alembic
  detects no drift while preserving safe legacy backfill.
- Metrics and benchmarks: Decimal-only implementations cover return, CAGR, volatility, Sharpe,
  Sortino, maximum drawdown, Calmar, turnover, beta, and information ratio. Benchmark fixtures cover
  Cash, QQQ, equal-weight, and momentum with aligned timing and explicit transaction costs; aware UTC
  timestamps and finite positive price/NAV inputs are required.
- Local gates: Ruff formatting and lint exited 0; focused strict Mypy exited 0 over 90 source files.
  Two consecutive `alembic upgrade head` calls and `alembic check` exited 0 with no new operations.
  The combined migration, schema, append-only, portfolio unit, and portfolio integration selection
  exited 0 with 53 passed.
- Initial Task 12 verification: `make verify` exited 0; 151 files passed Ruff formatting, Ruff lint
  passed, strict Mypy passed over 135 source files, Alembic/MCP drift checks passed, backend reported
  188 passed / 3 explicit credential-gated provider skips, TypeScript and ESLint passed, Vitest
  reported 1 passed, and the Next.js production build completed successfully.
- Pre-commit review found that sequential proposals did not decrement remaining cash, constrained
  allocations depended on input order, RiskDecision did not bind exact order economics, benchmarks
  hardcoded zero costs, post-fill NAV reused the decision mark, frozen research/context pins were not
  enforced end-to-end, and metrics could accept misaligned observations. Focused RED tests reproduced
  each path before remediation.
- Review remediation: the Risk Gateway now canonicalizes proposals and decrements cash/gross/turnover;
  immutable RiskDecision facts bind current/approved weights, signed delta, reference NAV/price,
  maximum quantity, risk policy, research DecisionSnapshot, and MarketContextSnapshot. Runtime,
  application persistence, and PostgreSQL triggers all reject unauthorized quantity/side changes.
  Market context is point-in-time persisted, frozen research verifies all policy/prompt/model/data-cutoff
  pins, benchmarks apply the execution spread/slippage/fee model on actual strategy turnover, and NAV
  uses the point-in-time market-bar mark visible at its timestamp while retaining execution costs.
- Migrations `0015`–`0018` safely backfill legacy orders, add market-context and exact-order lineage,
  and reject contradictory append-only risk facts. The first `0017` upgrade correctly rolled back with
  exit 1 because its revision identifier exceeded Alembic's 32-character storage limit; shortening only
  the identifier made upgrade/check exit 0. The combined portfolio/migration/schema/append-only suite
  then exited 0 with 60 passed.
- Final pre-commit verification: `make verify` exited 0; 154 files passed Ruff formatting, Ruff lint
  passed, strict Mypy passed over 135 source files, Alembic/MCP drift checks passed, backend reported
  195 passed / 3 explicit credential-gated provider skips, TypeScript and ESLint passed, Vitest
  reported 1 passed, and the Next.js production build completed successfully.
- Second independent-review remediation removes caller-supplied cash/weights/prices/turnover from the
  graph boundary and derives them from immutable Ledger, Fill, and point-in-time Bar facts. Post-fill
  NAV now exposes spread/slippage loss against the market mark. PostgreSQL additionally pins each order
  to the execution policy frozen by its DecisionSnapshot. Legacy migrations preserve unknown weights,
  NAV, prices, and market inputs as explicit `LEGACY_BACKFILL` / `UNKNOWN` facts instead of inventing
  100% weights or zero-valued observations; an empty database receives no synthetic context row.
- Final acceptance rerun: two consecutive `alembic upgrade head` commands exited 0; the migration,
  rebalance, and accounting integration selection exited 0 with 16 passed. Ruff format/check, strict
  Mypy over 136 source files, and Alembic drift check all exited 0.
- Final independent review found and the implementation fixed four remaining edge cases: a fully
  invested zero-cash portfolio now uses reconstructed decision NAV without division; benchmark fees
  use that same pre-trade NAV; valuation rejects conflicting immutable Bar revision identities in
  either input order; and daily turnover uses UTC day boundaries. The focused regression command
  exited 0 with 18 passed / 1 database test deselected, and the full Task 12 unit/database/integration
  selection exited 0 with 67 passed. The reviewer reported no remaining P1/P2 blockers and returned a
  ready verdict.
- Completion-gate `make verify` exited 0: 156 files passed Ruff formatting, Ruff lint passed, strict
  Mypy passed over 136 source files, Alembic/MCP drift checks passed, backend reported 202 passed / 3
  explicit credential-gated provider skips, TypeScript/ESLint passed, Vitest reported 1 passed, and
  the Next.js production build completed successfully.
- Scope remains Task 12. No Task 13 implementation, live-broker endpoint, real-funds path, provider
  credential field, external portfolio-graph tool, or LLM execution authority was introduced.

### Task 13 weekly attribution and controlled learning — 2026-08-21

- M4 closure and M5 start: Notion's engineering specification now records PR #3 and merge commit
  `063835edf9e0ce3ef1e1f81c3df16ab5483dfa66`. Linear FRE-15 received the missing merge evidence,
  the M4 milestone received a superseding 100%-complete record, and FRE-17 moved from Backlog to
  In Progress. Local `main` fast-forwarded cleanly from `aae5170` to `063835e`; the isolated
  `codex/m5-learning` worktree was then created from that exact base.
- Clean baseline: `make verify` exited 0 before Task 13 edits; 156 Python files were formatted, Ruff
  and strict Mypy over 136 source files passed, Alembic reported no drift, backend reported 202 passed /
  3 explicit credential-gated provider skips, Web Vitest reported 1 passed, and the Next.js production
  build completed.
- Initial RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run --offline pytest backend/tests/unit/learning
  backend/tests/integration/learning backend/tests/security/test_policy_promotion.py -q` exited 2
  with seven collection errors, all caused by the intentionally absent learning domain, application,
  and weekly-review modules.
- Outcome and attribution GREEN: UTC-aware maturity gates cover 1/5/20/60-day horizons. Decimal-only
  outcome code computes point-in-time returns, QQQ excess return, MFE, MAE, risk-adjusted return, and
  calibration error while rejecting unavailable future observations, floats, and naive datetimes.
  Attribution uses the frozen v0.2 taxonomy and prioritizes missing, stale, and conflicting evidence
  before thesis-direction errors.
- Controlled learning: Candidate Lessons retain scope, evidence, counter-evidence, confidence, replay
  delta, creator, status, and a normalized duplicate key. Historical replay enforces the strict
  `lesson.created_at < decision.decision_time` boundary, so a lesson cannot affect its own or an earlier
  decision. The weekly graph processes only matured decisions, exposes immature IDs as pending,
  checkpoints after Weekly Outcome, and enforces the 8 LLM / 8 tool / 1 reflection / 10 minute bounds.
- Human policy gate: approval, rejection, activation, and rollback use a locked compare-and-swap
  revision. Only an authenticated human actor may act; unauthenticated agents and authenticated
  non-human automation receive a 403-equivalent exception and a denial audit. Illegal reapproval or
  rejection of an active policy is rejected, rollback restores the pinned base version, and an in-memory
  two-thread regression permits exactly one concurrent approval winner. PostgreSQL persists the active
  version pointer and revision in `policy_control`; row locking, the candidate transition, pointer CAS,
  and append-only audit insert share one transaction, while denial audit uses an independent transaction
  so a caller's business rollback cannot erase the 403 fact.
- Persistence and migration: `0019_controlled_learning` adds `weekly_review_run`, `decision_outcome`,
  `error_attribution`, `candidate_lesson`, normalized `lesson_attribution_link`, `lesson_approval`,
  `policy_candidate`, `replay_run`, and `policy_promotion_audit`, plus the internal mutable
  `policy_control` CAS pointer. Weekly runs pin all four policy versions plus Prompt, Model, decision
  time, and data cutoff. The Postgres store atomically persists the Run → Outcome → Attribution → Lesson
  → Replay chain, freezes a run key's decision set, and treats semantic retries idempotently. Eight
  historical learning tables have database-level append-only triggers; policy candidates retain a
  revision for controlled CAS transitions.
- Systematic debugging evidence: an attempted worktree-local `docker compose up -d postgres` exited 1
  because the shared test database already owned port 55432; verification safely reused the existing
  container without deleting a volume. The first Alembic drift check exited 255 because raw migration
  constraint names received duplicate naming-convention prefixes; after confirming all new tables
  contained zero rows, only uncommitted `0019` was replayed using `op.f(...)`, and drift exited 0. A
  later combined test exited 1 because its append-only fixture omitted the new non-null `run_key`; the
  corrected fixture then passed. The first final `make verify` exited 2 on one Ruff formatting change;
  formatting that file and rerunning the entire command passed. During persistent CAS hardening, the
  first compatibility downgrade exited 1 because the older applied `0019` did not yet contain
  `policy_control`; PostgreSQL rolled the downgrade back atomically. Making that one internal drop
  conditional allowed downgrade/upgrade and the persistent promotion regression to exit 0.
- Pre-delivery independent review found seven P1 gaps and blocked publication. TDD remediation now
  excludes pre-decision observations from MFE/MAE and uses the latest decision-time benchmark base;
  consolidates duplicate lessons across decisions; makes freshly recomputed semantic retries reuse and
  validate Outcome, Attribution, Lesson, and Replay natural keys; preserves forbidden audits outside the
  rolled-back business transaction; requires every Policy lesson to exist, have an APPROVE fact, and
  have a ReplayRun; routes real missing/stale/conflicted inputs into attribution; and executes a real
  reflection node plus a checkpoint write through the existing checkpoint store.
- A second independent production review found additional replay and governance gaps. Remediation makes
  new Lessons wait for future eligible decisions; computes replay delta with deterministic abstention
  counterfactual code instead of trusting a declared delta; persists forward replay only for an existing
  Lesson; omits QQQ excess return unless both benchmark base and target exist; rejects run-key retries
  with a changed decision set; requires the latest Lesson disposition to be APPROVE plus a non-empty
  ReplayRun at approval and activation; rejects rollback after a newer policy version is active; retains
  every deduplicated Lesson-to-Attribution lineage link; rejects blank audit identities; and proves the
  PostgreSQL row-lock CAS with two concurrent transactions in an isolated migrated database.
- The final review pass additionally froze the complete weekly input decision set—including immature
  pending decisions—in `weekly_review_run.decision_ids`, and made forbidden audit reconstruction read
  the existing `policy_control` row without requiring callers to repeat bootstrap configuration.
- Final PR human review found one remaining point-in-time invariant gap: Task 13's `PriceObservation`
  accepted `available_at < event_time`, unlike the platform's canonical market facts. The regression
  test first exited 1 because no exception was raised; the minimal UTC time-order guard then made the
  complete outcome unit module exit 0 with 8 passed. An initial focused rerun was blocked by sandbox
  localhost policy (`Operation not permitted`, exit 1; 26 passed before database setup failures); the
  identical command with authorized local PostgreSQL access exited 0.
- Focused acceptance: the authoritative Task 13 command exited 0 with 43 passed. Two consecutive
  `alembic upgrade head` commands exited 0, `alembic check` exited 0 with no new operations, and the
  migration/schema/append-only regression command exited 0 with 16 passed.
- Completion gate: `make verify` exited 0; 178 files passed Ruff formatting, Ruff lint passed, strict
  Mypy passed over 157 source files, Alembic/MCP drift checks passed, backend reported 245 passed / 3
  explicit credential-gated provider skips, TypeScript/ESLint passed, Vitest reported 1 passed, and
  the Next.js production build completed successfully.
- Final-gate debugging evidence: pre-success runs exited 2 for Ruff formatting, import order, and strict
  Mypy test typing findings; after the last two P1 regressions, one independent rerun found one additional
  Ruff formatting delta. Each issue was corrected at its source and the entire `make verify` command was
  rerun; the final authoritative run exited 0 with the counts above.
- Scope remains FRE-17 / Task 13. No Task 14 implementation, online Prompt mutation, automatic Policy
  activation, Live Broker surface, real-funds path, provider credential field, or LLM execution
  authority was added.

### Task 14 control plane, scheduling, and durable SSE — started 2026-08-21

- Authority and scope: reread the complete Notion v0.2 design baseline and executable Task 14
  specification, then confirmed Linear FRE-18 is the first M6 Product issue and is unblocked by the
  completed FRE-17. Task 15 remains out of scope.
- Isolated delivery branch: created `codex/m6-control-plane` in
  `/private/tmp/aistock-m6-control-plane` from exact base
  `main@31a27a337a871468406df25101203ea00c72b5a8`. The existing main-worktree stash was preserved.
- Clean baseline: `make verify` exited 0 before behavior changes; Ruff formatting/lint, strict Mypy,
  Alembic and MCP contract drift checks passed, backend reported 245 passed / 3 explicit
  credential-gated provider skips, Web Vitest reported 1 passed, and TypeScript, ESLint, and Next.js
  production build passed.
- Environment diagnosis: an attempted worktree-local PostgreSQL start exited 1 because port 55432 was
  already owned by the healthy main-project PostgreSQL container. Verification reused that existing
  test service without deleting or changing its data volume.
- First TDD slice: the health/error-envelope contract command initially exited 2 because
  `stock_platform.api` did not exist. The minimal FastAPI implementation now reports Fixture Mode and
  the paper-only boundary and emits the locked structured 404 envelope; the identical command exits 0
  with 2 passed.
- Collaboration: FRE-18 moved from Backlog to In Progress with base, branch, baseline counts, scope,
  and safety boundaries recorded. The Notion engineering specification received a non-destructive
  Task 14 implementation-start record.
- REST contract RED/GREEN: the initial full-surface test exited 2 because the API dependency module
  did not exist. The next run exposed four behavior failures in validation serialization and admission
  isolation; after fixing the shared sources, the locked REST surface, normalized Watchlist CRUD,
  provider health, read views, research/portfolio Run creation, cancellation, and structured missing
  resources pass runtime contract tests.
- Durable idempotency and admission: migration `0020_api_control_plane` adds `agent_run` with a unique
  idempotency key, canonical request hash, frozen request payload and cutoff, durable status, and an
  active-status index; it also adds `watchlist_item` and durable Alert acknowledgement fields. A
  PostgreSQL transaction advisory lock serializes the existing-key check and active-run count. Equal
  retries return the same Run, changed payloads return 409, and exceeding the typed default limit of
  two returns retryable 429. Cancellation changes durable state to `CANCELLED` and releases capacity.
- Concurrency evidence: an isolated migrated PostgreSQL test races two different requests at a limit
  of one and observes exactly one 202 plus one 429. Racing the same idempotency key returns two 202
  responses with one shared Run and exactly one database row.
- Approval boundary RED/GREEN: a regression first observed self-asserted JSON identity reaching the
  resource layer and returning 404. The production dependency now rejects all untrusted mutation
  identities with 403; Alert acknowledgement, Lesson approval/rejection, and Policy
  activation/rollback require a trusted authentication layer to inject an authenticated `HumanActor`.
  Actor identity is no longer accepted from the request body.
- Contract artifact: `scripts/export_openapi.py` uses only the standard library and emits deterministic
  JSON-compatible YAML at `docs/api/openapi.yaml`; generation followed by `--check` exits 0. The full
  locked REST list is asserted and any live-broker path is prohibited.
- Related acceptance: Ruff formatting/lint exited 0; strict Mypy exited 0 over 169 source files;
  Alembic reported no migration drift; OpenAPI check exited 0; API contract, concurrent admission,
  migration/schema, and settings regressions exited 0 with 33 passed. The only warning is the installed
  FastAPI TestClient's upstream Starlette deprecation notice for `httpx` compatibility.
- Full regression checkpoint: `make verify` exited 0; Ruff, strict Mypy, Alembic drift, MCP/OpenAPI
  contract checks, TypeScript, ESLint, Vitest, and Next.js production build passed. Backend reported
  259 passed / 3 explicit credential-gated skips; Web reported 1 passed. Task 14 remains In Progress:
  Celery/Beat scheduling and durable SSE are intentionally not claimed by this REST checkpoint.
- Celery/Beat TDD: the first worker tests failed because Celery and the scheduling modules did not
  exist. Celery 5.6 is now a locked dependency configured for UTC, late acknowledgement,
  worker-loss rejection, and no result backend. Beat registers daily research, intraday monitoring,
  portfolio cutoff, weekly review, and queued-run recovery. PostgreSQL admission advisory locks plus
  stable cutoff/symbol idempotency keys ensure repeated Beat delivery creates one `agent_run` and
  dispatches it once; queued state remains recoverable after worker or broker restart.
- Market-time review fix: a completion review found the initial 20:xx UTC cron would run an hour
  early during New York standard time. A failing DST regression was observed before the fix. Beat
  now wakes at both 20:xx and 21:xx UTC, while deterministic `America/New_York` 16:15 research and
  16:30 portfolio cutoff guards admit exactly the valid occurrence; the intraday window includes the
  winter-time 21:xx UTC hour. The focused worker/scheduling command exited 0 with 5 passed.
- Durable SSE TDD: the initial integration command returned 404 for both replay cases. The first
  implementation then passed ordered PostgreSQL replay, recursive secret redaction, cross-run cursor
  rejection, and `Last-Event-ID` recovery with Redis intentionally unreachable. A second failing
  regression exposed premature stream closure; the stream now polls PostgreSQL until the run reaches
  `COMPLETED`, `FAILED`, or `CANCELLED`, then closes after emitting the terminal batch. Redis is not
  consulted for replay or live tail. Research persistence now emits the locked `node.completed`
  event name with the node in its payload.
- Task 14 focused acceptance: `uv run pytest backend/tests/contract/api backend/tests/integration/api
  -q` exited 0 with 18 passed; `PYTHONPATH=backend/src uv run python scripts/export_openapi.py
  --check` exited 0; `uv run alembic -c backend/alembic.ini check` exited 0 with no new operations.
  The final expanded API/worker command exited 0 with 22 passed. The only warning is the installed
  FastAPI TestClient's upstream Starlette/httpx deprecation notice.
- Task 14 full acceptance: `make verify` exited 0. Ruff format/lint, strict Mypy over 181 source
  files, Alembic and MCP/OpenAPI drift checks, TypeScript, ESLint, Vitest, and Next.js production
  build passed. Backend reported 267 passed / 3 explicit credential-gated provider skips; Web
  reported 1 passed. No live-broker endpoint, credential, configuration flag, or Task 15 UI was
  added.
- Product decision and migration closure: the owner approved one explicitly persisted Paper Portfolio
  with `100000` USD initial cash. Migration `0021_single_paper_portfolio` creates and seeds the
  append-only `default-paper` configuration. A completion review then proved that a differently named
  second row was still insertable; the RED test exited 1, and forward migration
  `0022_single_portfolio_guard` now fixes the singleton UUID at the database boundary. The first 0022
  attempt rolled back transactionally because its revision identifier exceeded Alembic's 32-character
  column; the shortened revision upgraded cleanly. The local database is at
  `0022_single_portfolio_guard (head)`.
- Worker TDD and recovery: initial collection runs failed because the execution helpers did not exist.
  `execute_run` now locks the authoritative `agent_run`, changes `QUEUED` to `RUNNING`, appends ordered
  lifecycle events, executes graph work and marks `COMPLETED` in one PostgreSQL transaction. A raised
  exception rolls the entire transaction back to durable `QUEUED`; duplicate Celery delivery observes
  the terminal status and returns without repeating facts. Late acknowledgement and worker-loss
  rejection remain enabled at the Celery boundary.
- Real consumer wiring: Research hydrates the frozen fixture catalog and executes the existing daily
  LangGraph with complete decision lineage. Portfolio loads the singleton configuration, visible
  MarketContext, latest frozen Research decisions, policy pins, point-in-time fixture bars and prior
  ledger/fills before executing the existing Portfolio graph; the initial balanced ledger uses exactly
  `100000` USD. Weekly Review loads cutoff-visible frozen decisions and price observations, executes the
  existing bounded review graph, and persists the review history. Intraday monitor records a durable
  point-in-time scan fact instead of echoing a run ID. Every route emits ordered `node.completed` or
  `monitor.completed` events for durable SSE.
- Cross-task Portfolio correction: the first regression correctly failed because Portfolio required a
  16:15 Research cutoff to equal its 16:30 cutoff and also required Research Prompt/Model pins to equal
  Portfolio Prompt/Model pins. The graph now requires the four governed policy versions to match,
  accepts only Research cutoff `<=` Portfolio cutoff, and still rejects a mismatched Risk Policy. The
  positive and negative regression nodes exited 0 with 2 passed.
- Persistence hardening: rejected deterministic RiskDecisions can now be stored without manufacturing an
  OrderIntent, and balanced ledger persistence is independently idempotent. An authoritative Research
  `ABSTAIN` remains `NO_ACTION`: the Portfolio worker persists its `100000` USD funding and route but does
  not invent a risk decision, order, or fill.
- Focused evidence: Worker PostgreSQL integration exited 0 with 7 passed; API/SSE/scheduling plus
  Research, Portfolio, Weekly and worker regressions exited 0 with 72 passed; migration/schema/
  append-only/worker integration exited 0 with 23 passed. Strict Mypy exited 0 over 182 source files.
  The post-singleton test node exited 0 with 1 passed. All commands used real exit codes; failed RED and
  debugging runs above are intentionally retained.
- Full acceptance before the final singleton review: `make verify` exited 0; Ruff format/lint, strict
  Mypy over 182 source files, Alembic and MCP/OpenAPI drift checks, TypeScript, ESLint, Vitest, and
  Next.js production build passed. Backend reported 275 passed / 3 explicit credential-gated provider
  skips; Web reported 1 passed.
- Final acceptance after singleton closure: the first post-0022 `make verify` exited 2 at Alembic drift
  detection because the naming convention had prefixed and truncated the new check-constraint name.
  Since 0022 was local and unpublished, only that additive constraint migration was downgraded; the
  0021 table and `100000` USD row remained intact. Marking the intended name with `op.f(...)`, then
  upgrading 0022 again made standalone `alembic check` exit 0 with no new operations. The complete
  `make verify` was then rerun from the start and exited 0: 207 files formatted, Ruff lint passed,
  strict Mypy passed over 182 source files, Alembic/MCP/OpenAPI drift checks passed, backend reported
  275 passed / 3 credential-gated skips / 1 upstream deprecation warning, Web Vitest reported 1 passed,
  and TypeScript, ESLint, and the Next.js production build passed.
- Residual boundaries: Fixture Mode remains the credential-free authoritative demo path; no Provider
  credential was fabricated. Portfolio execution intentionally fails and transactionally remains
  `QUEUED` when no point-in-time MarketContext or frozen Research decision exists. The upstream
  Starlette/httpx deprecation warning remains non-blocking. No live-broker endpoint, credential,
  configuration flag, real-funds path, automatic Policy activation, or Task 15 UI was added.
- Final-review P1 closure (2026-08-22): six merge blockers were reproduced before repair. Migration
  `0023_run_execution_guards` adds explicit Decision availability, bounded attempts, a 15-minute
  worker lease, redacted terminal error state, and immutable Run pins for all four Policy versions,
  Prompt, and Model. The migration temporarily disables only the existing DecisionSnapshot
  append-only UPDATE trigger while backfilling `available_at = created_at`, immediately re-enables it,
  and leaves the table append-only after upgrade.
- Run execution no longer holds the `agent_run` row lock for the graph duration. Claim/start commits
  first; each Research, Portfolio, and Weekly graph node writes a separately committed durable event
  and checks cancellation; business facts plus the conditional `RUNNING -> COMPLETED` transition
  remain atomic. Concurrent cancellation therefore responds without waiting and rolls back unfinished
  business facts at the next node boundary. Runtime failures are retried only to the persisted maximum
  of three attempts, then become `FAILED`; permanent validation failures become `FAILED` immediately;
  expired `RUNNING` leases are returned to `QUEUED` by recovery without resetting the attempt count.
- Point-in-time and execution-pin closure: Research persists DecisionSnapshot availability from the
  admitted Run's creation time. Portfolio and Weekly require both `available_at <= data_cutoff` and
  the existing decision-time/cutoff predicates, preventing a later-created historical decision from
  leaking into replay. API and Beat admission freeze type-specific Prompt/Model pins plus the four
  governed Policy versions; a database trigger rejects pin updates. Portfolio now selects the pinned
  PolicyVersion rows and constructs Risk/Execution policies from their persisted JSON content instead
  of hard-coded runtime parameters. This remains durable even when ABSTAIN/NO_ACTION creates no order.
- RED/GREEN evidence: the new execution tests first failed four times because `execute_run` had no
  RunControl boundary; after the state-machine change they exited 0 with 4 passed. Expired-lease
  recovery first failed with an unsupported `now` argument, then passed. Pin immutability first failed
  because UPDATE succeeded, and Portfolio admission first exposed `prompt-v1`/`fixture-v1`; both now
  pass with database rejection and `portfolio-prompt-v1`/`fixture-proposer-v1`. The first related suite
  also exposed a Decimal-to-timedelta type error and a legacy direct Decision insert without
  availability; integer duration hydration and the conservative `now()` availability default fixed
  those shared sources.
- Migration debugging evidence: the first persistent 0023 upgrade exited 1 because the existing
  append-only trigger correctly rejected the backfill UPDATE; PostgreSQL rolled the migration back.
  The protected disable/backfill/re-enable sequence then upgraded to
  `0023_run_execution_guards (head)` with exit 0. `alembic check` exited 0 with no new upgrade
  operations. The focused API/worker/PIT/pin suite exited 0 with 13 passed; the expanded API,
  scheduling, Research, Portfolio, and Weekly suite exited 0 with 55 passed.
- Final acceptance after all six P1 fixes: the first `make verify` exited 2 on one Ruff formatting
  delta, before tests ran. After correcting the exact metadata line, the full command was rerun from
  the beginning and exited 0: Ruff format checked 208 files, Ruff lint passed, strict Mypy passed over
  182 source files, Alembic/MCP/OpenAPI drift checks passed, backend reported 279 passed / 3 explicit
  credential-gated skips / 1 upstream Starlette-httpx deprecation warning, Web Vitest reported 1
  passed, and TypeScript, ESLint, and the Next.js production build completed successfully.
- Post-gate incremental review found four further P1s and one P2. RED regressions proved that an
  exhausted worker lease remained RUNNING, a normal Portfolio input race became terminal, active
  `policy_control` versions were ignored, legacy placeholder Risk/Execution JSON could not hydrate,
  type-specific historical Run pins were backfilled incorrectly, and a QUEUED cancellation produced
  no SSE fact. Recovery now marks an exhausted lease FAILED with a redacted WorkerLost error and
  durable event; `RunInputUnavailable` retries missing frozen inputs and succeeds after they arrive;
  admission snapshots any human-activated four-policy pointer; 0023 upgrades placeholder policy JSON
  and backfills Prompt/Model by Run type before installing the immutability trigger; and API
  cancellation writes `run.cancelled` in the same transaction. Production Research availability now
  defaults to actual persistence time; the optional completion clock exists only for deterministic
  tests, preventing delayed historical work from leaking into point-in-time replay.
- Post-review evidence: the targeted five-fix suite exited 0 with 25 passed; the expanded Task 14 API,
  worker, SSE, scheduling, Research, Portfolio, and Weekly suite exited 0 with 69 passed. The final
  authoritative `make verify` was rerun from the beginning and exited 0: 208 files passed Ruff format,
  Ruff lint passed, strict Mypy passed over 182 source files, Alembic/MCP/OpenAPI drift checks passed,
  backend reported 280 passed / 3 explicit credential-gated skips / 1 upstream deprecation warning,
  Web Vitest reported 1 passed, and TypeScript, ESLint, and Next.js production build passed.
- Final crash-window review proved that status-only completion was not sufficient fencing: after A's
  lease expired and B reclaimed the Run, stale A could still observe B's RUNNING status and commit.
  The A/B interleaving regression first failed with A returning True. Claim now returns a persisted
  attempt generation; every separately committed node event, completion CAS, and failure transition
  must match both RUNNING and that exact generation. A generation mismatch is `RunLeaseLost`, rolls
  back stale business work, does not mutate B, and never writes a false cancellation event. Both stale
  A-success and stale A-failure interleavings now pass while B remains RUNNING attempt 2 and completes.
  Retry classification is also explicit: only `RetryableRunError` subclasses such as
  `RunInputUnavailable` requeue; generic validation/programming failures are terminal.
- Authoritative post-fencing evidence: the expanded focused suite exited 0 with 71 passed. The complete
  `make verify` was rerun again from the beginning and exited 0: 208 files passed Ruff format, Ruff
  lint passed, strict Mypy passed over 182 source files, Alembic/MCP/OpenAPI drift checks passed,
  backend reported 282 passed / 3 credential-gated skips / 1 upstream deprecation warning, Web Vitest
  reported 1 passed, and TypeScript, ESLint, and the Next.js production build passed.

## GitHub Actions verification gate (2026-08-22)

- Design baseline: one least-privilege Ubuntu `verify` job mirrors the authoritative local
  `make verify` gate for pull requests and pushes to `main`; it uses only Fixture Mode and the
  repository's local Docker Compose PostgreSQL, Redis, and MinIO credentials.
- RED environment diagnosis: the first focused test command exited 2 before collection because `uv`
  attempted to initialize `/Users/fredz/.cache/uv`, which is outside the worktree sandbox. Re-running
  with the repository-local `UV_CACHE_DIR` used by `scripts/verify.sh` reached the intended test.
- RED: `UV_CACHE_DIR=/private/tmp/aistock-m6-control-plane/.uv-cache uv run pytest
  backend/tests/contract/ci/test_github_actions.py -q` exited 1 with 3 failed. Every failure was the
  expected `FileNotFoundError` for the not-yet-created `.github/workflows/ci.yml`.
- GREEN: after adding the single-job workflow, the same focused command exited 0 with 3 passed. The
  workflow pins Checkout, setup-python, setup-node, setup-uv, and pnpm setup to full immutable commit
  SHAs while retaining human-readable release comments; it grants only `contents: read`.
- Related-contract debugging: the first `backend/tests/contract` run was sandboxed from
  `localhost:55432`, producing 10 setup errors and one MCP audit failure after 34 tests had passed.
  The identical command with local-service access exited 0 with 45 passed / 3 explicit
  credential-gated skips / 1 existing upstream Starlette/httpx warning.
- Completion gate: the first `make verify` exited 2 before tests because Ruff required one fewer blank
  line after the new test file's import block. Ruff's exact diff was applied; the focused Ruff check
  and 3 CI tests then exited 0. A complete from-the-start `make verify` exited 0: 209 files passed Ruff
  format, Ruff lint passed, strict Mypy passed over 183 source files, Alembic/MCP/OpenAPI drift checks
  passed, backend reported 285 passed / 3 credential-gated skips / 1 existing upstream warning, Web
  Vitest reported 1 passed, and TypeScript, ESLint, and the Next.js production build passed.
- CI scope and residual risk: PR-to-main, push-to-main, and manual triggers share per-ref concurrency
  cancellation. A fresh database is upgraded to Alembic head before `make verify`; Docker service
  state and logs are emitted on failure, and volumes are always removed. No provider secret, Live
  Broker setting, real-money path, or automatic policy activation was added. The remaining acceptance
  step is the first real GitHub-hosted `Verify` run on PR #5.
- First hosted run: GitHub Actions run `32511069888` parsed and started correctly but exited 1 in
  `Set up pnpm`. Its log proved two competing version sources: workflow input `version: 11` and the
  repository's exact `packageManager: pnpm@11.19.0`. No dependency installation, service startup, or
  test command ran before the action rejected the ambiguity.
- Hosted-failure RED/GREEN: the revised contract first exited 1 with 1 failed / 2 passed by requiring
  the workflow to omit `version: 11` and to preserve the exact root package-manager pin. Removing only
  that redundant action input made Ruff and the focused suite exit 0 with 3 passed.
- Post-fix local gate: a fresh complete `make verify` exited 0 with the same authoritative results:
  209 files passed Ruff format, Ruff lint passed, strict Mypy passed over 183 source files,
  Alembic/MCP/OpenAPI drift checks passed, backend reported 285 passed / 3 explicit credential-gated
  skips / 1 existing upstream warning, Web Vitest reported 1 passed, and TypeScript, ESLint, and the
  Next.js production build passed. The next hosted run must pass before CI configuration is accepted.
- Second hosted run: GitHub Actions run `32514219465` passed setup, locked dependency installation,
  PostgreSQL/Redis/MinIO health, and a fresh Alembic upgrade, then reported 37 failed / 248 passed / 3
  skipped inside `make verify`. Root-cause tracing showed the Job-level `DATABASE_URL` overrode every
  explicit isolated-database URL inside Alembic `env.py`, so migration fixtures upgraded the shared
  database while their newly created databases remained empty.
- Isolation RED/GREEN: the CI contract first exited 1 with 1 failed / 2 passed when it required no
  Job-level `DATABASE_URL`. Removing that single override lets the repository's identical locked
  default reach Compose while preserving test-supplied Alembic URLs. Ruff and the focused 3-test suite
  exited 0. A fresh complete local `make verify` then exited 0 again with 285 passed / 3 skips and all
  Python/Web/static/build gates green. Hosted verification remains required.
- Third hosted run: GitHub Actions run `32515250076` reached the authoritative `make verify` gate and
  reported 6 failed / 279 passed / 3 skipped. All failures were test-fixture foreign-key violations:
  two integration fixtures hard-coded the legacy market-context sentinel from migration 0016, while
  migration 0018 intentionally removes that row when no legacy RiskDecision references it. The local
  long-lived database masked that invalid dependency.
- Fresh-database regression fix: the accounting helper and append-only test now create and reference
  their own explicit `market_context_snapshot` facts. The focused existing-database suite exited 0
  with 9 passed. An explicitly empty temporary PostgreSQL database then upgraded through Alembic 0023
  with exit 0, and the same focused suite against it exited 0 with 9 passed; both temporary databases
  created during diagnosis were removed afterward.
- Post-fix local completion gate: a complete from-the-start `make verify` exited 0. Ruff format checked
  209 files, Ruff lint passed, strict Mypy passed over 183 source files, Alembic/MCP/OpenAPI drift
  checks passed, backend reported 285 passed / 3 explicit credential-gated skips / 1 existing
  upstream warning, Web Vitest reported 1 passed, and TypeScript, ESLint, and the Next.js production
  build passed. A green hosted rerun remains the final merge condition.
- Final hosted gate: GitHub Actions run `32515964511` completed the fresh-service and fresh-database
  workflow in 2m19s with `Verify` passing. This closes the required independent hosted acceptance gate
  for Task 14 and PR #5.

## Task 15 product interface start (2026-08-22)

- Linear: FRE-19 moved from Backlog to In Progress after FRE-18 reached Done.
- Branch / base: `codex/m6-product-ui` from synchronized `main@8db13b87fa534c32923819fabd20026750c93bbc`.
- Authoritative scope read: Notion v0.2 design baseline plus the complete Task 15 section and Linear
  issue. The locked information architecture is Today, Watchlist, Stock Research, Research Run, AI
  Portfolio, Alerts, Weekly Review, and Eval & Admin; Task 16 remains out of scope.
- First TDD RED: `pnpm --dir web test -- --run` exited 1 with the expected unresolved
  `components/layout/app-shell` import after the new worktree's locked dependencies were installed.
- Minimal GREEN: added the semantic eight-destination product shell, current-page state, skip link,
  and visible Paper Trading / not-investment-advice boundary. The focused command exited 0 with 3
  passed; `pnpm --dir web typecheck`, `pnpm --dir web lint`, and the Next.js production build each
  exited 0.
- Next TDD slice: shared Loading/Empty/Stale/Degraded/Failure/Success states and the Today page data
  contract. No Task 16 evaluation implementation, Live Broker surface, or real-funds path has begun.

## Task 15 Today states and contract checkpoint (2026-08-22)

- Remote delivery resumed: `git -c http.version=HTTP/1.1 push -u origin codex/m6-product-ui`
  exited 0 and established the upstream branch after the earlier network failure.
- Shared-state RED/GREEN: six semantic state tests first failed on the intentionally missing
  `components/states/state-boundary` module. The minimal discriminated state boundary then passed all
  six Loading, Empty, Stale, Degraded, Failure, and Success cases. Non-blocking Degraded state keeps
  known-good content visible; Failure exposes an alert and recovery action; Stale includes an
  explicit timestamp.
- Runtime-contract RED/GREEN: four tests first failed on the missing `lib/api` module. The parser now
  rejects naive datetimes, numeric Money, invalid progress, and any ResearchOpinion/PortfolioAction
  enum mixing. The Today snapshot keeps raw freshness, coverage, provider, delay, and conflict facts,
  uses decimal strings for Money, and has only `fixture` or `read_only` provider modes.
- Today-page RED/GREEN: three page tests first failed because the Today implementation did not exist.
  The page now renders a frozen market regime, USD 100,000 paper-portfolio baseline, Cash/QQQ/equal
  weight/momentum comparisons, dual New York/Shanghai times, a semantic watchlist table with separate
  opinion/action columns, provider degradation, alerts, and active-run progress. The fixture is
  visibly labelled frozen synthetic data rather than current market data.
- Apple design review: retained information density while establishing one dominant Today hierarchy,
  system typography, restrained warm-amber chrome, 44px interaction targets, text-backed status
  signals, visible keyboard focus, instantaneous pressed feedback, and responsive tables/navigation.
  Reduced-motion, reduced-transparency, and increased-contrast preferences are honored. The compact
  degraded banner no longer displaces core facts; mobile navigation has an overflow affordance.
- Browser evidence: Playwright visual inspection covered 1440px desktop and 390px mobile layouts.
  After adding the app icon, the final reload reported 0 console errors and 0 warnings. Generated
  browser artifacts are ignored and not committed.
- Fresh checkpoint gate: `pnpm --dir web test -- --run` exited 0 with 5 files and 16/16 tests passing;
  `pnpm --dir web typecheck` exited 0; `pnpm --dir web lint` exited 0; and
  `pnpm --dir web build` exited 0 with the Today route statically generated. Task 15 remains In
  Progress for the remaining locked pages; no Task 16 work, live-broker configuration, or real-money
  path was added.
- Delivery status: a local checkpoint commit was created after the gate. Two push attempts did not update
  the remote branch: the sandboxed attempt could not resolve GitHub, and the authorized attempt hung
  until interrupted. Read-only diagnosis then found both an invalid GitHub CLI token and a 15-second
  HTTPS timeout to github.com. Re-authentication plus restored GitHub connectivity is required before
  the checkpoint can be pushed; no remote-delivery success is claimed.

## Task 15 eight-page product interface completion (2026-08-22)

- Authoritative scope: re-read the complete Notion Task 15 section and selective v0.2 UI override
  before continuing. Delivered the locked Today, Watchlist, Stock Research, Research Run, AI
  Portfolio, Alerts, Weekly Review, and Eval & Admin information architecture. Task 16 remains
  explicitly unstarted on the Eval page.
- Page TDD batch one: three tests first failed on the missing Watchlist, Research, and Run Trace
  modules. The GREEN implementation provides a semantic five-symbol table; separate
  ResearchOpinion and PortfolioAction; Thesis, invalidation conditions, Evidence relations/gaps,
  deterministic DecisionDiff, frozen policy/model/prompt pins; Claim → Evidence → ToolCall → provider
  → available-at traceability; and a durable ordered event trace with budgets, retry, fallback,
  checkpoint, cost, and `Last-Event-ID`. The focused suite then passed with 19/19 total Web tests.
- Page TDD batch two: the new Partial state and Portfolio, Alerts, Weekly Review, and Eval & Admin
  tests first failed because behavior/modules were absent. GREEN adds Partial retention of verified
  content, Cash/QQQ/equal-weight/momentum benchmark summary, Paper positions and execution/ledger
  facts, deterministic alert lineage with visible explanation failure, outcome/error attribution,
  Point-in-Time replay, Candidate Lesson consequences, and read-only Policy controls. Human Lesson
  approval is explicitly distinct from Policy activation; automatic activation is disabled.
- Durable SSE TDD: three tests first failed on the missing `lib/sse` module. The minimal store now
  builds a reconnect request with `Last-Event-ID`, suppresses duplicate durable event IDs, orders by
  authoritative sequence, and rejects cross-Run events, naive event times, invalid sequence values,
  and same-sequence/different-ID protocol collisions.
- Browser TDD: the first Playwright run could not launch because its private Chromium was absent; the
  suite was configured to use the installed system Chrome and to start Next.js on `127.0.0.1`. The
  sandboxed server then correctly failed with EPERM, while the authorized local run reached the app.
  Its first behavioral run passed 4/6 and exposed only an over-broad safety-copy selector; scoping the
  assertion to the semantic footer produced 6/6 at 1440×900 and 393×852. The flow visits all eight
  routes, checks one H1, navigation and safety copy, traces Today → NVDA Research → Claim → Evidence
  → Provider/ToolCall/timestamp → durable Run event, verifies keyboard focus, and rejects document
  overflow.
- Apple-design review: interactive desktop/mobile review covered Research, Portfolio, Alerts, Weekly
  Review, and the shared shell. The implementation uses platform typography, restrained warm-amber
  decision accents, immediate pressed/focus feedback, translucent structural chrome, semantic and
  horizontally contained tables, non-color-only signals, dual time zones, reduced-motion,
  reduced-transparency, and increased-contrast modes. Mobile now exposes `Current · <page>` without
  reordering keyboard navigation. Final browser inspection reported 0 console errors / 0 warnings.
- Accuracy regression: visual/code review found that dynamic symbol and Run routes could substitute
  the NVDA/latest Fixture for an unknown identifier. A three-test RED reproduced the unsafe
  substitution. GREEN routes only NVDA and the frozen latest Run to their facts; unknown identifiers
  receive an explicit Empty state and return path. Vitest was also hardened to exclude Playwright
  specs so each test runner owns one suite.
- Fresh Task 15 gate: `pnpm --dir web test -- --run` exited 0 with 9 files / 30 tests passed;
  `pnpm --dir web exec playwright test e2e/happy-path.spec.ts` exited 0 with 6/6 passed across desktop
  and mobile Chrome. The authoritative `make verify` then exited 0 from the beginning: 209 files
  passed Ruff format, Ruff lint passed, strict Mypy passed over 183 source files, Alembic/MCP/OpenAPI
  drift checks passed, backend reported 285 passed / 3 explicit credential-gated skips / 1 existing
  Starlette-httpx deprecation warning, Web reported 30/30, TypeScript and ESLint passed, and Next.js
  generated all ten application routes successfully.
- Safety and residuals: all displayed market/research values are frozen, visibly labelled synthetic
  Fixtures. Money remains decimal-string formatted; timestamps are aware and converted only at the
  presentation boundary. No Provider credential, real-funds path, live-broker configuration,
  automatic Policy activation, or Task 16 evaluation metric was added. Real-provider UI integration
  remains credential-gated and outside this Fixture acceptance.

## Task 15 TradingView market-reference checkpoint (2026-08-22)

- TDD RED/GREEN: the focused page suites first exited 1 with four expected missing-region failures
  for the homepage ticker, NVDA overview, Watchlist mini charts, and Portfolio mini charts. The shared
  implementation then passed 10/10 focused tests. A dark-theme contrast regression first failed
  1/3 because `isTransparent` was true; the corrected official theme background passed 3/3.
- Product placement: Today renders a compact six-symbol Ticker Tape directly below navigation;
  `/research/NVDA` renders the requested Symbol Overview after the immutable AI thesis and before
  evidence lineage; Watchlist and Paper Portfolio render lightweight Mini Charts. Each chart is
  labelled `Current market reference` and `Not decision-time evidence`, and TradingView attribution
  remains visible. External market widgets do not enter Evidence, Decision, replay, or backend data.
- Theme race regression: a saved-dark-theme test first failed because the external light script was
  injected before theme restoration. Theme context plus deferred injection now starts only the final
  theme script. A real dark-mode reload previously produced five TradingView `querySelector` errors;
  the same reload after the fix reported no console errors and rendered high-contrast dark widgets.
- Browser evidence: official widgets loaded with current delayed-market labels at 1440px and 393px.
  Visual checks covered the compact Today tape, rounded desktop/mobile Symbol Overview, Watchlist
  Mini Chart, and dark theme. No npm dependency or provider credential was added.
- Fresh verification: focused Vitest exited 0 with 11/11. The first sandboxed `make verify` could not
  access local PostgreSQL; the authorized rerun then exposed and fixed nullable `aria-pressed` typing.
  The final complete `make verify` exited 0: Ruff format/lint, strict Mypy over 183 files, Alembic drift,
  285 backend passed / 3 credential-gated skipped / 1 existing warning, 34/34 Web tests, TypeScript,
  ESLint, and all ten Next.js routes passed. Final Playwright exited 0 with 6/6 desktop/mobile tests.

## Task 15 portfolio performance and Framer dark-theme checkpoint (2026-08-23)

- TDD RED/GREEN: the focused Portfolio and shell suites first exited 1 with two expected failures:
  the new Portfolio performance figure did not exist and the obsolete Today Ticker Tape was still
  rendered. The minimal implementation then exited 0 with 2 files / 7 tests passing. Regression
  coverage verifies the three independent metrics, default 30-day state, 7-day range switching,
  Drawdown switching, accessible SVG history labels, frozen-data disclosure, and absence of the
  homepage ticker.
- Portfolio overview: Net asset value, Day return, and Current drawdown now sit above a dependency-free
  responsive SVG line/area chart. Users can select 7/30/90-day or all-history ranges and switch among
  Net asset value, Cumulative return, and Drawdown. The 16-point Fixture history keeps aware timestamps
  and decimal strings as source facts; numeric conversion is isolated to SVG pixel placement.
- UI revision: dark mode follows the supplied Framer design reference with a `#090909` canvas,
  `#141414`/`#1c1c1c` surfaces, `#262626` hairlines, white/gray typography, `#0099ff` signal blue,
  20px cards, compact 15px rhythm, and white selected pills. Finance risk semantics remain text-backed,
  and the light theme remains available. The homepage TradingView Ticker Tape and its caption were
  removed; symbol-detail and lightweight holding/watchlist market references remain explicitly
  separated from decision-time evidence.
- Browser evidence: Playwright inspected desktop and 393×852 dark layouts, verified Drawdown plus
  Last 7 days yields an Aug 15–Aug 21 accessible history, confirmed the Today DOM has no current-market
  ticker, and reported 0 console errors / 0 warnings. Generated screenshots were deleted after review.
- Fresh gate: `make verify` exited 0: 209 files passed Ruff format, Ruff lint passed, strict Mypy passed
  over 183 source files, Alembic drift checks passed, backend reported 285 passed / 3 explicit
  credential-gated skips / 1 existing Starlette-httpx deprecation warning, Web reported 9 files /
  33 tests passed, TypeScript and ESLint passed, and Next.js generated all ten routes. The separate
  `pnpm exec playwright test e2e/happy-path.spec.ts` run exited 0 with 6/6 desktop/mobile tests.

## Task 15 Today portfolio-chart checkpoint (2026-08-23)

- TDD RED/GREEN: the new Today regression first exited 1 because no figure named `Paper portfolio
  performance` existed. GREEN reuses the Portfolio performance component through a compact variant;
  the focused Today suite exited 0 with 6/6 tests. Related Today contract, shell, and Portfolio suites
  then exited 0 with 4 files / 18 tests.
- The Today Paper portfolio now presents Net asset value, Day return, Current drawdown, a frozen
  30-day net-asset-value line/area chart, all four locked benchmark comparisons, and an `Open portfolio`
  route. Full range and metric controls remain on `/portfolio` so the Today card stays efficient.
- The Today contract now carries an explicit performance history. Every point validates aware time,
  Decimal-string NAV, cumulative return, and drawdown; new contract tests reject naive history times
  and numeric money. The chart converts strings to numbers only for SVG presentation coordinates.
- Browser review covered dark desktop and 393×852 mobile layouts. Both retained clear hierarchy and
  responsive stacking, and the console reported 0 errors / 0 warnings. Generated screenshots were
  deleted after inspection.
- Fresh gate: `make verify` exited 0 with 209 Ruff-formatted files, Ruff lint, strict Mypy over 183
  files, clean Alembic drift, 285 backend passed / 3 credential-gated skipped / 1 existing warning,
  9 Web files / 35 tests passed, TypeScript, ESLint, and all ten Next.js routes. The separate full
  Playwright run exited 0 with 6/6 desktop/mobile tests.

## Task 15 Notion acceptance-blocker closure (2026-08-23)

- Re-audited FRE-19 against the complete Notion v0.2 page contract and closed every reported P1/P2
  gap. Watchlist now has a validated add-symbol session draft, per-symbol daily-research and intraday
  monitoring controls, Decimal-string thresholds, and an aware earnings date. Stock Research now
  exposes Fundamentals, Earnings, News, Options, Analyst Targets, and immutable Decision History.
  Run Trace records and renders per-step duration alongside node/tool/token/cost/retry/fallback and
  checkpoint facts.
- Portfolio now exposes derived cash, position unrealized P&L, accepted/rejected RiskDecision facts,
  append-only PaperFill rows, and CashLedger rows rather than relying on a ledger-status sentence.
  Weekly Review adds Thesis hit outcomes and descriptive confidence buckets while leaving formal
  Brier/ECE gates to Task 16. Alerts now use the locked PRICE, VOLUME, OPTIONS, EARNINGS, NEWS,
  ANALYST_TARGET, and PORTFOLIO_RISK category union. Today uses a responsive, non-color-only
  Watchlist heatmap instead of a table.
- Accessibility TDD added `@axe-core/playwright@4.10.2`. Initial scans correctly failed on missing
  document title, light-theme navigation contrast, small tertiary text contrast, and keyboard access
  to horizontally scrollable tables; each owned-DOM defect was fixed. The scan covers all eight
  routes at desktop and mobile viewports and fails on serious/critical WCAG 2 A/AA violations.
  Cross-origin TradingView iframe internals are explicitly excluded because they are third-party;
  the owned widget host remains labelled and covered.
- Final repository gate: authorized `make verify` exited 0. Ruff format/lint, strict Mypy over 183
  source files, Alembic/MCP/OpenAPI drift checks, and the production Next.js build passed. Backend:
  285 passed, 3 credential-gated skips, 1 existing Starlette/httpx deprecation warning. Web: 9 files,
  37/37 tests passed. Final `pnpm exec playwright test --reporter=line` exited 0 with 8/8 tests across
  desktop and mobile Chrome, including both eight-route Axe scans. `git diff --check` exited 0.
- Safety boundary: all new values are visibly frozen synthetic fixtures; Money stays as Decimal
  strings, timestamps are aware, ResearchOpinion remains distinct from PortfolioAction, and no live
  broker, real-funds path, provider credential, automatic policy activation, or Task 16 metric was
  added.
- Final review follow-up: inputs and keyboard-scrollable tables now share the visible focus-ring
  contract. Playwright also aborts TradingView network requests during owned-DOM checks so the gate
  does not hang on a third-party service; the application integration itself is unchanged. On the
  final revision, `make verify` exited 0 with the same 285 passed / 3 skipped backend and 37/37 Web
  results, and the separate desktop/mobile Playwright plus Axe run exited 0 with 8/8 tests.

## Task 15 pre-merge human-review closure (2026-08-23)

- A two-axis review against `main@8db13b8`, Notion v0.2, and repository invariants found five
  actionable P1 defects: binary-float NAV chart projection, presentation paths accepting naive
  datetimes, a missing Report step in the UI trace, alerts without invalidation-condition IDs, and
  an incomplete paper-fill/CashLedger fixture that could not reconstruct current cash. It also found
  README status drift and a duplicated Today `Signal` component.
- TDD RED exited 1 with exactly five expected failures. GREEN exited 0 with 10 files / 40 tests:
  chart coordinates retain cent-level distinctions beyond JavaScript Number precision, naive times
  are rejected, the trace includes `report-nvda-v3`, alerts expose their invalidation condition, and
  opening cash plus NVDA/MSFT fills reconcile exactly to USD 74,699.58.
- `normalizeDecimalSeries` converts Decimal strings to scaled BigInt values and converts only the
  final dimensionless 0–1 ratio to Number for SVG coordinates. `parseAwareInstant` is now the shared
  presentation boundary for chart, watchlist, and dual-zone time rendering. Today reuses the shared
  `Signal`, and README now reports M6 Task 15 accurately.
- The review also questioned static Fixture route data. Re-reading the authoritative task text showed
  Task 15 explicitly requires the eight page/state contracts and SSE recovery tests, while Task 18
  owns the clean-room end-to-end demo. Fixture Mode therefore remains an explicit, non-live boundary;
  connecting every product view to enriched control-plane view models remains integration debt, not
  a Task 15 merge blocker.
- Final gate on the reviewed revision: `make verify` exited 0 with 285 backend passed / 3 skipped,
  10 Web files / 40 passed, clean Ruff/Mypy/Alembic/API drift checks, and a successful ten-route
  production build. The parallel browser run completed all assertions but intermittently stalled
  during dev-server teardown; the diagnostic single-worker run
  `pnpm --dir web exec playwright test --reporter=line --workers=1` exited 0 with 8/8 desktop/mobile
  tests and the same Axe coverage.
- Final standards follow-up added a sixth regression: the shared stale-state boundary now rejects a
  naive `lastUpdatedAt` before rendering. Its focused RED run exited 1 with the expected single
  failure; GREEN exited 0 with 8/8 state tests. The fresh repository gate then exited 0 with 285
  backend passed / 3 skipped and 10 Web files / 41 passed; the single-worker desktop/mobile
  Playwright plus Axe run again exited 0 with 8/8 tests.

## M7 Quality

Authoritative sources: Notion v0.2 design baseline and the complete Task 16 specification, re-read
on 2026-08-23. Linear milestone: M7 Quality (FRE-20, FRE-21).

### Task 16 — local implementation complete; awaiting PR review

- Domain-contract RED: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest
  backend/tests/unit/evaluation/test_cases.py -q` exited 2 with the expected missing evaluation
  package. GREEN exited 0 with 7 passed, covering aware UTC time, strict Decimal-string cost,
  L0–L7/category enums, pinned versions/seed, canonical SHA-256, duplicate IDs, and unknown fields.
- Metric RED/GREEN: the first focused run exited 2 on the absent application package; the minimal
  deterministic Decimal implementation then passed 4/4 worked examples for precision/recall/F1,
  schema/task/evidence/citation/conflict/numeric quality, Directional Accuracy, Thesis Hit Rate,
  Brier/ECE/reliability, Abstain Accuracy, safety/recovery/audit/accounting/learning, latency P95,
  and non-gating portfolio measurements.
- Gate RED/GREEN: unit and integration tests first exited 2 because the policy module was absent.
  `evaluation-gates-v0.2` now encodes all 18 exact hard boundaries. A review-found over-broad test
  selector was corrected to distinguish non-blocking investment metrics from the required portfolio
  decision latency gate; the combined slice passed 32/32.
- Runner RED/GREEN: the runner test first exited 2 on the missing module. The completed suite has
  exactly 200 deterministic cases (40 tool, 40 research, 30 evidence, 30 security, 20 alert,
  20 portfolio, 20 learning) across L0–L7, each pinned to dataset/model/prompt/four policy versions,
  seed, raw output, trace, latency, token usage, Decimal-string cost, verdict, and case hash. It
  emits byte-reproducible `summary.json`, `cases.jsonl`, `junit.xml`, and escaped `report.html`;
  injected schema failure returns exit 1. Generator output is independently idempotent.
- CI RED/GREEN: workflow contracts first exited 1 with 3 expected missing-file failures. PR,
  nightly, and weekly workflows now use SHA-pinned Actions and read-only permissions. PR evaluation
  has a ten-minute timeout, nightly executes three fixture runs, and weekly provider smoke is
  credential-detected and step-scoped; no live-broker field/path exists. The focused workflow suite
  exited 0 with 4 passed.
- Authoritative focused gate: `UV_CACHE_DIR=$PWD/.uv-cache uv run pytest
  backend/tests/unit/evaluation backend/tests/integration/evaluation/test_release_gates.py -q` —
  exit 0; 40 passed. `PYTHONPATH=$PWD/backend/src UV_CACHE_DIR=$PWD/.uv-cache uv run python
  scripts/generate_eval_datasets.py --output evals/datasets` — exit 0. The corresponding
  `scripts/run_offline_eval.py --dataset evals/datasets --output evals/reports/latest` — exit 0,
  `offline evaluation: PASS`; 37 metrics and all 18 hard gates passed. `git diff --check` — exit 0.
- Full repository gate: the first sandboxed `make verify` exited 1 only because policy denied local
  PostgreSQL access after Ruff and Mypy passed. The authorized rerun of the identical command exited
  0: 225 files formatted, Ruff lint clean, strict Mypy clean over 197 source files, Alembic/MCP/
  OpenAPI drift clean, backend 325 passed / 3 explicit credential-gated skips / 1 existing
  Starlette-httpx deprecation warning, Web 10 files / 41 passed, TypeScript/ESLint clean, and all ten
  Next.js routes built.
- Reproducibility evidence: dataset SHA-256 values are `afa4d74a…` alert, `57d0bcd5…` evidence,
  `138ba530…` learning, `d5729c92…` portfolio, `7ee7a6f4…` research, `b384f499…` security, and
  `6c834178…` tool. Manifest SHA-256 is `a921172f…`, baseline SHA-256 is `8d6970b1…`, and the latest
  summary SHA-256 is `7a4eac0a…`; generated reports are ignored local/
  CI artifacts while their frozen source datasets and manifest are versioned.
- Scope and residuals: all observations are explicitly synthetic Fixture data, not current market
  data or investment performance claims. Investment return, alpha, Sharpe, and win rate remain
  descriptive and never block software release. Optional weekly live-provider smoke remains skipped
  without real read-only Provider credentials. No live trading, automatic Policy activation, Task 17
  observability/recovery implementation, or Task 18 clean-room demo was added.

#### Task 16 pre-PR review remediation

- Two-axis review reproduced four release-evidence blockers. A hand-selected seven-case corpus could
  pass, offset timestamps produced mismatched stored/emitted hashes, nested raw outputs remained
  mutable after hashing, and artifact upload was skipped on gate failure. It also found that leakage
  and conflict recall trusted ambiguous booleans rather than their underlying facts.
- Corpus-integrity RED/GREEN: the public runner now requires the versioned manifest, exact 200-case
  distribution, complete L0–L7 coverage, seven exact filenames, every file SHA-256, and one corpus
  digest. Missing, shortened, modified, version-mixed, or manifest-divergent corpora fail before gate
  evaluation. Dataset generation writes the same manifest idempotently.
- Evidence-integrity RED/GREEN: canonical hashing normalizes aware offsets to UTC before hashing;
  report case hashes now equal summary evidence hashes after round-trip load. Raw output and trace
  structures are recursively immutable. Judge kind/version are explicit; deterministic cases cannot
  claim LLM calibration, and a calibrated-LLM judge requires a calibration version.
- Metric-correctness RED/GREEN: point-in-time leakage is computed from each aware `available_at`
  against case `as_of`; a one-second future record fails the hard gate. Conflict recall considers only
  expected-conflict cases. Freshness compliance is a separate measured metric. The result corpus
  remains a frozen raw-output evaluation input as required by Task 16; Task 18, not this runner,
  owns clean-room execution of the complete product scenario.
- Baseline comparison: `eval-baseline-v0.2.0` contains only metrics measured from the synthetic
  Fixture corpus. Every report compares all 38 current metrics with that versioned baseline; the
  accepted corpus has zero deltas. No live-market, Provider, benchmark, or resume value was invented.
- CI evidence retention: PR and weekly artifacts upload with `always()`; nightly executes all three
  runs even after one failure, uploads every report, then enforces their combined outcome. The
  existing `ci.yml` remains the full PR `make verify` gate while `pr.yml` owns the under-ten-minute
  offline-evaluation layer, avoiding duplicate full repository jobs.
- Corrected focused gate: `uv run pytest backend/tests/unit/evaluation
  backend/tests/integration/evaluation/test_release_gates.py -q` — exit 0; 51 passed. Corrected
  offline CLI with explicit dataset/baseline/output — exit 0; `offline evaluation: PASS`, 38 metrics,
  18 hard gates, zero baseline deltas. Corrected authorized `make verify` — exit 0: 226 files format
  clean, Ruff clean, strict Mypy clean over 198 files, Alembic/MCP/OpenAPI drift clean, backend
  336 passed / 3 credential-gated skips / 1 existing warning, Web 10 files / 41 passed, TypeScript/
  ESLint clean, and all ten Next.js routes built. `git diff --check` — exit 0.
- Second review pass added six citation-negative and five alert-negative cases without changing the
  locked 200-case total. An injected always-cite result now measures precision `0.8` and fails the
  citation hard gate; an always-trigger alert result measures precision `0.75`. Explicit optional
  `null` is canonicalized out before hashing, all four Policy pins reject empty strings, and the
  Fixture manifest rejects any calibrated-LLM judge even if all hashes are resealed. The final
  focused and full-gate counts above include these regressions.

### Task 17 — local implementation complete; awaiting PR review

- Baseline: `make bootstrap` initially exited 2 because sandbox DNS blocked the locked wheel download;
  the authorized identical rerun exited 0. The untouched `make verify` then exited 0 with 336 backend
  passed / 3 credential-gated skipped and 41 Web tests, establishing a clean `main@2e84e21` baseline.
- Security/context RED: the first focused collection exited 2 because the observability and recovery
  modules did not exist. GREEN exited 0 with 10 tests for recursive credential/prompt/address/provider
  text redaction, validated UUID correlation headers, all eight required low-cardinality Prometheus
  families, explicit rejection of symbol/run labels, bounded worker recovery, and provider circuit
  opening/recovery.
- Correlation RED/GREEN: HTTP/log/span tests first exited 2 on the absent telemetry module, then passed
  8/8. The PostgreSQL/SSE test first exited 1 because run admission had no correlation pin; migration
  `0024_observability_correlation` now persists and indexes one ID across AgentRun, AgentEvent,
  ToolCall, and AlertEvent. A worker/graph test then failed because the context was not restored and
  passed after `execute_run` installed the persisted context around graph work.
- Recovery: a real Redis stream was deleted to simulate transient loss; PostgreSQL AgentEvent and its
  correlation ID remained authoritative, the expired non-exhausted worker lease requeued exactly one
  task, and existing idempotency/append-only fill and ledger guards remained covered by the full suite.
  The recovery directory passed 5/5 after an actual Redis container replacement.
- Operations assets RED/GREEN: the contract first failed 3/3 on absent Compose services, dashboard,
  security guide, and runbooks. OTel Collector 0.132.0, Prometheus 3.5.0, and authenticated Grafana
  12.1.0 are now provisioned with eight SLO/failure panels. Provider outage, stuck run, Redis loss,
  database restore, and human-only policy rollback runbooks contain exact commands and RPO/RTO.
- Security remediation: an initial anonymous-Grafana proposal was rejected before any write. The
  accepted configuration keeps login enabled and binds Grafana, Prometheus, OTel, PostgreSQL, Redis,
  and MinIO only to `127.0.0.1`. The focused test first failed on the legacy `0.0.0.0` bindings and
  passed after hardening. All six services then ran successfully; Prometheus and Grafana health
  endpoints succeeded and OTel reported ready.
- Migration/idempotency: applying `alembic upgrade head` twice and `alembic current` exited 0 at
  `0024_observability_correlation`. The first post-migration repository gate exposed four metadata-
  missing indexes; after declaring them, `alembic check` reported no operations and the focused DB
  migration/schema/model suite passed 14/14.
- Locked Task 17 gate: `pytest backend/tests/security backend/tests/integration/observability
  backend/tests/integration/recovery -q --junitxml=reports/verification/task17-focused.xml` exited 0,
  24 passed / 0 failed / 0 skipped with one existing Starlette-httpx warning. Report:
  `reports/verification/task17-focused.xml`.
- Full repository gate: final `make verify` exited 0. Ruff format/lint and strict Mypy over 208 files,
  Alembic/MCP/OpenAPI drift checks, and Next.js production build passed. Backend: 354 passed / 3
  credential-gated skipped / 1 existing warning. Web: 10 files / 41 passed. No live broker, real-money
  execution, automatic policy activation, naive datetime, binary-float money, or Task 18 work was
  added.

#### Task 17 pre-PR review remediation

- The first two-axis standards/specification review found release blockers in generic secret
  redaction, historical correlation backfill, production OTel export/log wiring, runtime metric call
  sites, authenticated human policy rollback, exact recovery commands, and real recovery evidence.
  Each behavior was covered by a failing regression before the minimal correction.
- Redaction once again covers generic `key` and `private_key` fields. Migration 0024 now backfills
  AgentEvent and ToolCall from their owning AgentRun while temporarily disabling and restoring the
  append-only trigger; the 0023-to-head historical migration regression passed and the local database
  reports zero correlation mismatches for both tables.
- OTel uses an opt-in, loopback-only OTLP/HTTP exporter and structured correlated JSON logs. HTTP,
  worker, MCP, Provider, DB-audit, graph, alert, queue, cost, and evaluation paths now invoke the
  shared low-cardinality observability boundary. A real local export produced one collector resource
  span and one `m7.acceptance` span.
- Human policy actions require a constant-time checked bearer token and a fixed server-configured
  human actor; partial configuration and request-supplied identity are rejected. No Provider or live
  broker credential/path was introduced.
- `scripts/verify-recovery.sh` performs a full TimescaleDB custom-format backup/restore into an
  isolated temporary database, Alembic drift validation, a real Redis restart, bounded worker
  recovery, and append-only PaperFill/CashLedger idempotency tests. The first real run exited 1 and
  exposed missing Timescale pre/post-restore state. Its RED regression failed as expected; adding
  `timescaledb_pre_restore()` and `timescaledb_post_restore()` fixed the root cause. The corrected
  real run exited 0 with 7 passed and cleaned its temporary database.
- Corrected focused gate: `pytest backend/tests/security backend/tests/integration/observability
  backend/tests/integration/recovery -q --junitxml=reports/verification/task17-focused.xml` exited 0,
  29 passed / 0 failed / 0 skipped with the existing Starlette-httpx warning. The first corrected
  full gate then exited 2 solely because the newly explicit Authorization header made the locked
  OpenAPI artifact stale; the generated diff contained only those five human-only endpoints. After
  deterministic regeneration, `make verify` exited 0: 237 files format clean, Ruff clean, strict
  Mypy clean over 208 files, Alembic/MCP/OpenAPI drift clean, backend 359 passed / 3 explicit
  credential-gated skips / 1 existing warning, Web 10 files / 41 passed, TypeScript/ESLint clean,
  and the ten-route Next.js production build passed.

#### Task 17 second-review remediation

- The second standards/specification pass found disconnected runtime correlation, a production
  Provider circuit that was not yet wired, recovery checks that did not span worker/Redis restart,
  process-local-only metrics, an INFO logger that could drop JSON, a dynamic alert-rule label, and
  unredacted span attributes. RED tests reproduced all owned behaviors; the real worker regression
  additionally exposed and prevented an advisory-lock deadlock between MCP audit and graph events.
- Research workers now pass every allowed feed through `McpProviderGateway`; ToolCall and
  `mcp.tool.completed` AgentEvent rows carry both the owning run ID and its correlation ID, and the
  worker uses the existing independent `RunControl.emit` persistence boundary. A complete
  HTTP-admission → worker → Research Graph → MCP gateway → Fixture Provider → PostgreSQL → durable
  SSE test passed with one correlation ID, five audited tools, contiguous event sequences, and
  idempotent second execution.
- `GovernedHttpProvider` now owns the bounded circuit breaker. Two terminal upstream failures open
  it, subsequent calls skip transport with `circuit_open`, and a request is retried after the aware
  recovery timeout. The production adapter contract passed. Alert metrics accept only the locked
  bounded rule set, and span attributes pass through the same recursive redaction boundary as logs.
- Operational JSON writes directly and synchronously to stderr, so container collection does not
  depend on Python logger levels or third-party `logging.disable` state. A real FastAPI request
  regression verifies its event and correlation. Prometheus uses the official multiprocess file
  collector when every API/Celery/MCP process inherits one deployment-local
  `PROMETHEUS_MULTIPROC_DIR`; two independent producer processes aggregate to one API scrape value.
- The recovery gate snapshots AgentEvent and PaperFill counts in the restored database, starts a
  real named Celery worker, restarts Redis, stops and restarts the worker under a fresh node name,
  compares durable counts, and then runs bounded recovery plus append-only fill/ledger replay tests.
  A `pipefail`/early-exit readiness false negative was diagnosed and fixed by consuming the complete
  Celery inspect output. Final `scripts/verify-recovery.sh` exited 0; Timescale pre/post restore and
  Alembic drift passed, both workers answered ping, Redis returned PONG, counts matched, and 7/7
  recovery/idempotency tests passed.
- Final locked Task 17 command exited 0 with 34 passed / 0 failed / 0 skipped and one existing
  warning; JUnit: `reports/verification/task17-focused.xml`. The expanded affected suite passed 59
  with three credential-gated provider skips. Final `make verify` exited 0: 237 files format clean,
  Ruff clean, strict Mypy clean over 208 files, Alembic/MCP/OpenAPI drift clean, backend 367 passed /
  3 explicit credential-gated skips / 1 existing warning, Web 10 files / 41 passed, TypeScript/
  ESLint clean, and all ten Next.js routes built.

#### Task 17 final-review closure

- The third specification review cleared all P0/P1/P2 findings. The standards review retained one
  P1: ToolCall could roll back with the Research business transaction while its independently
  committed MCP AgentEvent survived; and one P2: the service restart gate could pass without work
  crossing the broker/worker boundary. Both findings were reproduced and corrected before delivery.
- MCP ToolCall and its durable AgentEvent now commit together through one independent
  `EngineMcpAuditSink` transaction. Research business persistence remains separate, so a later graph
  failure cannot erase the already-authoritative tool audit pair. The new failure-path regression
  intentionally raises after a successful tool audit and proves exactly one ToolCall and one matching
  append-only event remain.
- `scripts/recovery_probe.py` admits a frozen, cutoff-safe Research run in the isolated restored
  database and waits on its durable status. The recovery script starts a real solo Celery worker,
  dispatches `stock_platform.workers.research_tasks.run_research`, asserts non-zero run events and
  tool calls, snapshots non-zero AgentEvent/PaperFill totals, restarts Redis and the worker, and then
  redispatches the same completed run. Queue drain plus exact before/after run-event, ToolCall,
  AgentEvent, and PaperFill counts prove the replay is a no-op rather than a duplicate execution.
- The first final recovery run exited 2 because Celery 5.6 `call` has no `--id` option. Local CLI
  help confirmed the contract; removing the unsupported flag retained application-level run
  idempotency. The corrected full recovery command exited 0: Timescale pre/post restore and Alembic
  drift passed, the real Research task completed, Redis and worker restarted, replay counts stayed
  identical, and the seven focused recovery/accounting tests passed.
- Fresh final gates: the locked Task 17 command exited 0 with 35 passed / 0 failed / 0 skipped and one
  existing warning; JUnit: `reports/verification/task17-focused.xml`. `make verify` exited 0 with 238
  files format clean, Ruff clean, strict Mypy clean over 208 files, Alembic/MCP/OpenAPI drift clean,
  backend 368 passed / 3 explicit credential-gated skips / 1 existing warning, Web 10 files / 41
  passed, TypeScript/ESLint clean, and all ten Next.js routes built.

#### Task 17 non-vacuous fill-recovery closure

- A final standards review identified that the recovery gate's global non-zero PaperFill assertion
  depended on ambient restored data and did not prove that the fill under test survived restart and
  replay. A RED integration test first failed because no scoped durable fill probe existed.
- `persist_paper_fill_probe` now uses fixed paper-only identities, aware UTC timestamps, Decimal
  economics, a deterministic approved RiskDecision, frozen MarketContextSnapshot, and the existing
  `PostgresPaperAccountingStore`. Repeating the probe persists exactly one PaperFill and exactly
  three fill-sourced CashLedger entries; it cannot create a live order or contact a broker.
- `scripts/verify-recovery.sh` runs that probe before Redis/worker restart and again afterward, then
  checks the same fill ID still has count 1 and the same source ID still has ledger count 3. The
  ambient `paper_fill > 0` precondition was removed. The real backup/restore/restart/replay command
  exited 0, including 8/8 focused recovery/accounting tests.
- Fresh locked Task 17 gate exited 0 with 36 passed / 0 failed / 0 skipped and one existing warning;
  JUnit: `reports/verification/task17-focused.xml`. Fresh `make verify` exited 0: 239 files format
  clean, Ruff clean, strict Mypy clean over 209 files, Alembic/MCP/OpenAPI drift clean, backend 369
  passed / 3 explicit credential-gated skips / 1 existing warning, Web 10 files / 41 passed,
  TypeScript/ESLint clean, and all ten Next.js routes built.

### M7 post-merge warning cleanup — 2026-08-23

- Starlette 1.6 deprecated its legacy `httpx` TestClient fallback. A RED dependency contract first
  failed because `httpx2>=2,<3` was absent; the locked dev environment now uses `httpx2 2.12.0`.
  The resulting strict-Mypy RED exposed one test helper nominally tied to `httpx.Response`; its
  actual `.json()` boundary is now represented by a small structural Protocol. The API contract
  passed 11/11 with `StarletteDeprecationWarning` promoted to an error.
- Docker Compose now has the fixed project name `aistock`. Prometheus and Grafana use project-scoped
  volumes instead of cross-project hard-coded names, eliminating ownership warnings across worktree
  paths. The new volumes have `project=aistock` labels; both old `ai_stock_m7_*` volumes were retained
  unchanged for recovery. Prometheus readiness and Grafana database health both returned success.
- Fresh `make verify` exited 0: Ruff clean, strict Mypy clean over 209 files, Alembic/MCP/OpenAPI
  drift clean, backend 370 passed / 3 explicit credential-gated skips with no warning, Web 10 files /
  41 passed, TypeScript/ESLint clean, and all ten Next.js routes built.

### Watchlist persisted API vertical slice — 2026-08-23

- Scope: connected only the Watchlist page to the existing FastAPI GET/POST/PATCH/DELETE contract.
  `WEB_DATA_MODE=api` is fail-closed: unavailable, timed-out, non-success, invalid-JSON, or invalid-
  contract responses render explicit Failure and never load Fixture data. Valid persisted Watchlist
  configuration with unavailable market/research/earnings/quality enrichment renders Degraded and
  labels each missing fact `Unavailable`; no zero price, ABSTAIN, NO_ACTION, or TradingView chart is
  fabricated. No Provider ingestion, new public endpoint, live broker, or real-money path was added.
- TDD unit/component evidence: parser RED failed because `watchlist-contract` was absent; client RED
  failed because the server modules were absent; mutation RED failed eight tests because the locked
  write functions were absent; route RED showed the fixture-only page; configuration RED failed two
  tests because `readWebDataConfig` was absent. Final focused Web command exited 0 with 14 files and
  91 tests passed. TypeScript and ESLint each exited 0.
- Real persistence RED: `WEB_DATA_MODE=api API_BASE_URL=http://127.0.0.1:8000 pnpm --dir web exec
  playwright test e2e/watchlist-api.spec.ts --project=desktop-chrome` initially exited 1 because the
  Playwright web-server command hard-coded Fixture mode. The corrected config passes the caller's
  explicit server-only mode and URL to Next.js.
- Real persistence GREEN: with local FastAPI on `127.0.0.1:8000` and healthy PostgreSQL on
  `127.0.0.1:55432`, the desktop Playwright run on port 3100 exited 0: 1 passed / 1 controlled-failure
  case skipped. It added only `QAWEBAPI`, persisted schedule controls and Decimal threshold `0.031`,
  proved both after page reload, deleted the row, and performed exact-symbol cleanup.
- Fail-closed browser GREEN: the same test file with `API_BASE_URL=http://127.0.0.1:9`,
  `EXPECT_API_FAILURE=1`, and web port 3101 exited 0: 1 Failure-path case passed / 1 persistence case
  skipped. The page contained no Fixture notice, fixture provider, or fixture Watchlist table.
- Backend focused evidence: the first command exited 2 because the sandbox denied the default uv
  cache; the repository-cache retry exited 1 because the sandbox denied localhost PostgreSQL. The
  authorized identical test with repository cache exited 0: 1 passed / 10 deselected in 0.49s.
- Full repository gate: `make verify` exited 0. Ruff format/lint, strict Mypy over 209 files,
  Alembic/MCP/OpenAPI drift checks, TypeScript, ESLint, and the Next.js production build passed.
  Backend: 370 passed / 3 credential-gated skipped. Web: 14 files / 91 passed. Node emitted the same
  environment-level `--localstorage-file` warning seen in the untouched worktree baseline; there
  were no assertion, build, Python, Starlette/httpx, or Docker ownership warnings.

#### Watchlist API final-review closure

- Final code review found one contract gap: only `thresholds.return_5m` was validated, so another
  persisted threshold could carry a JSON number and bypass the Decimal-string invariant. A new
  regression first failed 1/12 because `{ "volume_ratio": 2 }` was accepted. The minimal parser
  change validates every supplied threshold value as a Decimal string; the focused suite then passed
  12/12.
- Fresh `make verify` exited 0 after the review fix: Ruff format/lint, strict Mypy over 209 files,
  Alembic/MCP/OpenAPI drift checks, TypeScript, ESLint, and the Next.js production build passed.
  Backend: 370 passed / 3 credential-gated skipped. Web: 14 files / 92 passed. The existing Node
  `--localstorage-file` environment warning remains non-functional; no application warning or test
  failure was introduced.
- Fresh real-browser persistence E2E exited 0 with 1 passed / 1 intentionally skipped: `QAWEBAPI`
  add, Decimal-threshold update, reload persistence, delete, and exact cleanup all succeeded against
  FastAPI and PostgreSQL. The unreachable-API E2E also exited 0 with 1 passed / 1 intentionally
  skipped and proved explicit Failure with no Fixture substitution.

#### PR #11 pre-merge review closure

- The pre-landing review found one P1 data-integrity issue: re-adding an existing symbol through the
  UI invoked the existing POST upsert and reset persisted monitoring/threshold configuration to add
  defaults. A regression first failed 1/9; the Server Action now reads the persisted list and rejects
  duplicates before POST, and the focused action suite passed 9/9.
- The review also closed an empty-list hydration mismatch by generating the fallback `asOf` once in
  the Server Component and passing it into the client page. Its regression first failed 1/5 and then
  passed. New action feedback text was raised from approximately 11px to 16px for readable success
  and failure states.
- Fresh post-review `make verify` exited 0: backend 370 passed / 3 credential-gated skipped; Web 14
  files / 94 passed; Ruff, strict Mypy, Alembic/MCP/OpenAPI drift, TypeScript, ESLint, and the Next.js
  production build passed. The existing environment-level Node `--localstorage-file` warning remains
  non-functional.
- Fresh post-review persistence and unreachable-API Playwright commands each exited 0 with 1 passed /
  1 intentionally skipped. The persistence run again proved add, update, reload, delete, and exact
  cleanup against FastAPI/PostgreSQL; the failure run again proved no Fixture substitution.
