# TradingView Market Reference List Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Present Today watchlist symbols in a compact TradingView-powered current-market list while preserving a separate PIT audit trail.

**Architecture:** Add a reusable client-side multi-symbol TradingView Market Data wrapper, then replace only the API Today quote grid with that isolated widget and a collapsed persisted-evidence disclosure. Keep the locked backend quote contract unchanged.

**Tech Stack:** Next.js 15, React, TypeScript, TradingView iframe widgets, Vitest, Testing Library, CSS.

---

### Task 1: Lock the TradingView list wrapper

**Files:**
- Create: `web/components/market/tradingview-ticker-list.tsx`
- Create: `web/tests/tradingview-ticker-list.test.tsx`

1. Write failing tests for symbol normalization, exchange mapping, isolated widget configuration, external script URL, current-data warning, and loading placeholder.
2. Run the focused test and confirm the component is missing.
3. Implement the smallest reusable client wrapper with one multi-symbol Market Data widget.
4. Re-run the focused test.

### Task 2: Integrate Today and preserve PIT evidence

**Files:**
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/app/globals.css`

1. Write a failing component test asserting the TradingView list replaces the card heatmap and persisted quotes remain in a collapsed audit disclosure.
2. Run the focused component test and confirm the old grid fails the expectations.
3. Integrate the wrapper and Apple-style responsive material, focus, contrast, and reduced-motion rules.
4. Re-run component and route-degradation tests.

### Task 3: Verify and record evidence

**Files:**
- Modify: `docs/progress.md`

1. Run focused TradingView and Today tests.
2. Run all web unit tests, typecheck, and build.
3. Run `make verify` if focused suites pass.
4. Record commands, exit codes, counts, and remaining third-party-widget risk in `docs/progress.md`.
