# Market Quote Rank List Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Render persisted Today quotes as a compact company-aware rank list with PIT-safe sparklines and deterministic daily returns.

**Architecture:** Extend the existing latest-quotes response with an optional presentation enrichment produced from the security master and canonical daily-bar repository. Parse the strict contract in the Next.js server client and render a reusable accessible SVG row component. Missing enrichment remains explicit and never triggers Fixture fallback.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Next.js 15, React, TypeScript, Vitest, Pytest.

---

### Task 1: Lock the enriched market quote REST contract

**Files:**
- Modify: `backend/tests/integration/api/test_market_data_reads.py`
- Modify: `backend/src/stock_platform/api/schemas/rest.py`
- Modify: `backend/src/stock_platform/api/routes/rest.py`

1. Add a failing integration test asserting company name, decimal-string daily return, ordered sparkline points, and PIT exclusion of a future-available bar.
2. Run the focused Pytest test and confirm the enrichment fields are absent.
3. Implement the smallest query/composition change using the existing canonical historical-bar repository and security-master table.
4. Run the focused integration file and confirm it passes.

### Task 2: Lock the strict web client contract

**Files:**
- Modify: `web/tests/live-data-api.test.ts`
- Modify: `web/lib/server/live-data-api.ts`

1. Add failing tests for valid enrichment and malformed decimal/sparkline fields.
2. Run the focused Vitest file and confirm the new expectations fail.
3. Extend `MarketQuote` and strict parsing with nullable `companyName`, `dailyReturn`, and decimal-string `sparkline` fields.
4. Re-run the focused Vitest file.

### Task 3: Render the approved compact list

**Files:**
- Create: `web/components/market/market-quote-list.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/api-pages.test.tsx`

1. Add failing component assertions for row links, company names, prices, signed returns, provenance, SVG accessible names, and unavailable fallbacks.
2. Run the focused component test and observe the expected failure against the card grid.
3. Implement the reusable list and minimal responsive CSS, then replace only the API Today quote grid. Follow `apple-design`: content-first hierarchy, tabular numerals, 44px minimum target, immediate restrained press feedback, strong focus visibility, dark/high-contrast themes, and reduced-motion behavior.
4. Re-run the focused component test and related route-degradation tests.

### Task 4: Verify and record evidence

**Files:**
- Modify: `docs/progress.md`

1. Run backend market-data integration tests.
2. Run web unit tests, typecheck, and build.
3. Run `make verify` if the focused suites pass.
4. Record exact commands, exit codes, counts, and any remaining risks in `docs/progress.md`.
