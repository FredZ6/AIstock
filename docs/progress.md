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
