# Watchlist Manual Market-Data Refresh Design

**Date:** 2026-10-05
**Status:** Approved
**Scope:** Paper-research market-data ingestion only

## Problem

The Watchlist UI periodically calls `router.refresh()`, which only rereads facts already persisted in PostgreSQL. New Alpaca facts are produced by the paper-runtime Celery/Beat ingestion loop. When that runtime is stopped, the UI can refresh indefinitely without receiving newer prices.

Users need an explicit way to request the latest available market data for every monitored Watchlist symbol without starting research, placing paper orders, or introducing any live-broker path.

## Goals

- Add one `Update latest data` control to the Watchlist page.
- Refresh all Watchlist symbols whose intraday monitoring is enabled.
- Create bounded, durable, idempotent Alpaca ingestion jobs and dispatch them through the existing `ingestion-low` queue.
- During an active US market session, request the latest completed minute-bar interval.
- Outside an active session, request the latest completed trading day's daily bar instead of pretending a new intraday price exists.
- Keep all timestamps timezone-aware and normalize them to UTC.
- Preserve the configured IEX entitlement; do not claim SIP coverage.
- Show explicit queued, no-new-data, and failure states without substituting Fixture data.

## Non-goals

- No research-run trigger.
- No paper-order trigger and no live-broker endpoint, credential, feature flag, or execution path.
- No synchronous wait for Alpaca inside the HTTP request.
- No automatic promotion from IEX to SIP.
- No client-side direct access to provider credentials.

## Chosen Approach

Use a small authenticated FastAPI command endpoint backed by the existing durable ingestion job store and Celery dispatcher.

The rejected alternatives are:

1. **Refresh only the page.** This cannot create new persisted facts and is the current failure mode.
2. **Call Alpaca synchronously from the browser or HTTP handler.** This exposes credentials or couples request latency to provider latency and retry behavior.
3. **Start a research run.** This is much broader than a market-data refresh and mixes independent product actions.

## Backend Design

### Command endpoint

Add a paper-only endpoint:

`POST /api/v1/watchlist/refresh-market-data`

The endpoint returns `202 Accepted` after durable admission and immediate dispatch of eligible queued jobs. Its response contains:

- `status`: `queued`, `already_queued`, or `no_symbols`
- `job_ids`: newly admitted or matching active ingestion job identifiers
- `symbol_count`
- `requested_at`: aware UTC timestamp
- `data_cutoff`: latest interval that can truthfully be requested
- `timeframe`: `minute` or `day`
- `feed`: the configured entitlement feed, expected to be `iex`
- `message`: user-safe explanation, including closed-market behavior

Provider completion is not claimed by this response. Persisted quote evidence remains the authority for what the UI can display.

### Scheduling policy

The command service reads every Watchlist item with `intraday_monitoring = true` and normalizes the supplied clock to aware UTC.

- **Active session:** enqueue one bounded minute-bar request per symbol for the latest completed minute. Never request the still-forming minute.
- **Closed session:** use `latest_completed_market_cutoff` and the exchange calendar to enqueue one daily-bar request per symbol for the most recently completed trading day. Weekends and holidays must not fall back to a naive calendar-day subtraction.
- **No monitored symbols:** return `no_symbols` without dispatching tasks.

The existing ingestion job uniqueness contract prevents duplicate active requests. Repeated clicks reuse the active request rather than creating unbounded work.

### Dispatch and persistence

After admission, the service dispatches eligible queued Alpaca jobs through the existing Celery path to `ingestion-low`. Workers remain responsible for provider calls, retries, MinIO raw-object lineage, normalization, and PostgreSQL persistence.

If Celery dispatch is unavailable, the endpoint returns an explicit failure response; it does not report that data was updated. Durable jobs that were admitted remain recoverable by the normal dispatcher.

### Safety and truthfulness

- Enforce `ENVIRONMENT=paper` for the command.
- Read Alpaca credentials only from backend settings.
- Use the configured entitlement and reject unsupported feed claims.
- Use aware UTC for request and cutoff values; reject naive injected times in service tests.
- Preserve point-in-time rules for downstream historical reads: `available_at <= decision_time`.
- Never create or expose broker execution behavior.

## Frontend Design

Add `Update latest data` beside the Watchlist page's primary controls.

The client invokes a Next.js Server Action. The Server Action calls the backend command endpoint using the existing server-side API client, validates the response contract, and revalidates `/watchlist`.

The button has these visible states:

- `Update latest data`
- `Requesting…` while the action is pending
- `Queued` after durable admission
- `Already queued` after an idempotent repeat request
- `No monitored symbols` when nothing is eligible
- an explicit error message when API admission or dispatch fails

Status text uses an `aria-live` region. The existing persisted-data refresh mechanism may reveal newly persisted results after the worker completes, but the UI must not say that prices are current merely because a request was queued.

The action is available only in API mode. Fixture mode remains visibly frozen and does not silently call or substitute real data.

## Failure Semantics

- **Backend unavailable:** show a retryable failure; retain the last persisted facts with their original timestamps.
- **Missing/invalid credentials:** reject the command explicitly; do not enqueue synthetic data.
- **Celery unavailable:** expose dispatch failure; admitted durable work remains recoverable.
- **Provider rate limit or outage:** worker records its normal failure/degraded evidence; the frontend never replaces it with Fixture data.
- **Outside market hours:** queue the latest completed session's daily evidence and explain that no newer intraday update is expected.
- **Duplicate click:** return the active job(s) and `already_queued` without multiplying requests.

## Test-Driven Delivery

Tests are written before production code and must cover:

1. Active-session scheduling for all monitored Watchlist symbols.
2. Closed-session, weekend, and holiday selection of the latest completed trading day.
3. Rejection of naive datetimes and preservation of aware UTC.
4. IEX entitlement propagation and rejection of unsupported feed claims.
5. Durable idempotency on repeated requests.
6. Immediate Celery dispatch to `ingestion-low` and explicit dispatch failure.
7. API `202` response contract plus paper-only enforcement.
8. Server Action response validation and API error handling.
9. Button pending/success/error accessibility behavior.
10. No Fixture fallback and no research or execution side effects.

Run focused backend and frontend suites during red/green/refactor. Before review, run `make verify` and record the exact evidence in `docs/progress.md` as required by repository policy.
