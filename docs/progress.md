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
