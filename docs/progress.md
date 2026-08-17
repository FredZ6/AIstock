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
