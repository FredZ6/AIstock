# Testing and verification

## Layers

- Unit and property tests enforce UTC, Decimal, identifiers, deterministic rules, budgets, and
  accounting invariants.
- Contract tests validate frozen and credential-gated provider schemas without fabricating live
  responses.
- PostgreSQL/Redis/MinIO integration tests cover migrations, append-only guards, durable ACK/outbox,
  point-in-time queries, replay, concurrency, recovery, and lineage.
- Vitest covers typed page contracts and shared Loading/Empty/Stale/Degraded/Failure/Success states.
- Playwright covers eight-page navigation, accessibility, API-mode failure semantics, and the M8
  interview scenario on desktop and mobile.
- The 200-case offline evaluation produces raw case, summary, JUnit, and HTML evidence.

## Commands

```bash
make verify
make evaluate
make smoke
```

The final clean-room gate is:

```bash
make clean-fixtures && make bootstrap && make seed && make up && make smoke && make verify
```

`make verify` runs Ruff formatting/lint, strict Mypy, Alembic drift detection, MCP/OpenAPI contract
checks, all Pytest tests, TypeScript, ESLint, Vitest, and a production Next.js build.

## Evidence locations

- `evals/reports/latest/demo-manifest.json`: deterministic scenario facts.
- `evals/reports/latest/summary.json`: measured aggregate metrics and release decision.
- `evals/reports/latest/cases.jsonl`: raw per-case outcomes and hashes.
- `evals/reports/latest/junit.xml`: machine-readable gate result.
- `evals/reports/latest/report.html`: human-readable evaluation report.
- `evals/reports/latest/screenshots/`: Playwright fallback screenshots.
- `docs/progress.md`: commands, actual exits, counts, skips, and remediation history.

Generated evidence is ignored by Git. Regenerate it rather than committing stale output.

## Live-test policy

Tests that require provider credentials or network entitlements use explicit `live` markers and
skip with a reason when unavailable. A skip is not a pass. Fixture Mode remains the credential-free
release path and never claims current market data.
