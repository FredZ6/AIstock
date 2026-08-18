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
