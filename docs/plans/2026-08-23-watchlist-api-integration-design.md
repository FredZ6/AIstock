# Watchlist API Integration Design

**Status:** Approved on 2026-08-23

## Purpose

Connect the Watchlist page to the existing FastAPI control-plane contract as the first real backend-to-frontend vertical slice. The page must persist watchlist configuration in PostgreSQL while preserving the platform's research-only and paper-trading boundaries.

This slice does not implement provider ingestion, add a public backend endpoint, or treat TradingView data as authoritative research evidence.

## Considered approaches

### 1. Browser-direct FastAPI client

The client component could call FastAPI directly. This is simple initially, but it requires browser-visible backend configuration and CORS policy, duplicates transport concerns in the client, and makes initial loading and failure handling harder to keep deterministic.

### 2. Next.js server gateway and Server Actions — selected

An async Server Component loads Watchlist data through a server-only API module. Server Actions perform POST, PATCH, and DELETE requests and revalidate the page after successful persistence. This keeps the FastAPI base URL and transport details out of the browser, avoids a new public endpoint, and gives one boundary for strict runtime validation and failure classification.

### 3. New aggregated backend UI endpoint

A backend-for-frontend snapshot endpoint would make the current table easiest to populate, but the approved data-backend note explicitly excludes new frontend APIs. It would also prematurely combine configuration, market, research, and earnings data before their authoritative ingestion contracts are approved.

## Architecture

The selected data flow is:

```text
Browser
  -> Next.js Watchlist route / Server Action
  -> server-only Watchlist API client
  -> existing FastAPI /api/v1/watchlist endpoints
  -> PostgreSQL watchlist_item
```

Responses return through a strict runtime parser before reaching React. The server-only client owns URL construction, timeout handling, HTTP status handling, JSON parsing, and contract validation. UI components receive a typed view model and do not know the FastAPI base URL.

The existing endpoints remain authoritative:

- `GET /api/v1/watchlist`
- `POST /api/v1/watchlist`
- `PATCH /api/v1/watchlist/{symbol}`
- `DELETE /api/v1/watchlist/{symbol}`

## Explicit data-source modes

`WEB_DATA_MODE` must be explicitly set to either `api` or `fixture`.

- `api` reads and writes only through FastAPI. It never imports, calls, or renders fixture data as a fallback.
- `fixture` preserves the frozen demonstration experience. It never claims persistence.

`API_BASE_URL` is server-only and required when `WEB_DATA_MODE=api`. Missing or invalid API configuration produces an explicit failure. No provider secrets or broker credentials are exposed to the browser.

## Watchlist view model

The backend currently stores configuration facts only: symbol, daily research, intraday monitoring, thresholds, and timestamps. It does not yet provide authoritative price, daily return, research opinion, portfolio action, earnings date, or data-quality facts.

API mode therefore must not synthesize zeroes, copy fixture enrichment, or label session drafts as provider data. Each unavailable enrichment field is represented explicitly as unavailable in the typed view model. The table renders `Unavailable` for those cells.

The page can remain useful in degraded mode because configuration is real and writable. Once approved provider ingestion and aggregate read contracts exist, those unavailable fields can be populated without changing the persistence controls.

## UI and mutation behavior

API mode supports:

- adding a normalized US equity symbol with POST;
- updating daily research, intraday monitoring, and alert threshold with PATCH;
- deleting a symbol with DELETE;
- refreshing server-rendered state only after the backend confirms persistence.

The first slice intentionally avoids optimistic state. Controls expose a pending state and remain consistent with the last confirmed server response. A failed mutation keeps the confirmed values visible and presents an explicit error rather than pretending the write succeeded.

The page identifies API mode and paper-trading scope. Fixture mode retains its existing fixture notice and session-only behavior.

## Failure and degraded semantics

The approved invariant is: **API mode never automatically falls back to Fixture data.**

- `Failure`: FastAPI is unreachable, times out, returns a non-success status for the initial read, returns invalid JSON, or violates the response contract. The page shows a failure surface and no fixture-derived watchlist.
- `Degraded`: FastAPI returns valid persisted configuration, but one or more market, research, earnings, or quality fields are unavailable. The page stays usable for configuration and labels missing facts as unavailable.
- `Success`: the response is valid and all facts required by the current view model are available. This state will become reachable as authoritative read contracts are added.

Mutation failures are shown next to the controls while the last confirmed server snapshot remains visible.

## Validation and safety

Runtime parsing enforces:

- normalized symbol syntax;
- aware UTC timestamps;
- decimal strings for thresholds and future monetary facts;
- booleans for schedule controls;
- expected object and list shapes.

Binary floating point is not introduced for monetary or threshold values. The implementation adds no live-broker endpoint, credential, configuration flag, or execution path.

## Testing strategy

Implementation follows TDD. Focused tests will prove:

1. valid FastAPI watchlist responses parse into the typed API-mode view model;
2. invalid symbols, naive timestamps, invalid decimal strings, and malformed payloads are rejected;
3. the server client handles success, timeouts, non-2xx responses, invalid JSON, and invalid contracts;
4. API failure never imports or invokes fixture fallback;
5. POST, PATCH, and DELETE use the locked methods, paths, and payloads;
6. the page renders `Failure`, `Degraded`, and explicit unavailable cells correctly;
7. mutations expose pending/error behavior and refresh only after success;
8. fixture mode remains explicitly selectable and remains labelled as non-current synthetic data;
9. backend contract tests and the repository-wide `make verify` remain green.

An integration check will exercise Next.js against the local FastAPI/PostgreSQL stack. Verification evidence will be recorded in `docs/progress.md` before review.

## Deferred work

The following are intentionally outside this slice:

- Alpaca, SEC, or Alpha Vantage ingestion;
- provider credentials or live-provider smoke tests;
- authoritative market/research/earnings aggregation for Watchlist;
- browser-direct SSE wiring;
- other frontend pages;
- live brokerage or real-money execution.

The Notion data-backend note remains partially approved; its unchecked schema, ingestion, reconciliation, quality, security, and operational sections must be resolved before implementing real provider ingestion.
