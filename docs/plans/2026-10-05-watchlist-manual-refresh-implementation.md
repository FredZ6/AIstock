# Watchlist Manual Market-Data Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a truthful, paper-only `Update latest data` command that durably queues the latest available Alpaca bars for every monitored Watchlist symbol and exposes its admission state in the Watchlist UI.

**Architecture:** A small application service chooses an active-session minute window or the latest completed trading-day window, reuses the existing Alpaca backfill/job-store policy, and publishes only eligible queued jobs to `ingestion-low`. FastAPI exposes the command as a closed `202` contract; a Next.js Server Action calls it server-side and a client form reports pending, queued, duplicate, empty, and failure states without substituting Fixture data.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy/PostgreSQL, Celery, pytest, Next.js 15 Server Actions, React 19, TypeScript, Vitest, Testing Library.

---

### Task 1: Specify the bounded Watchlist refresh scheduler

**Files:**
- Create: `backend/tests/unit/workers/test_watchlist_refresh.py`
- Create: `backend/src/stock_platform/application/ingestion/watchlist_refresh.py`

**Step 1: Write the failing scheduler tests**

Create unit tests around an injected job store and publisher. Cover these exact cases:

```python
def test_active_session_requests_latest_completed_minute_for_every_monitored_symbol() -> None:
    now = datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC)
    result = request_watchlist_market_data_refresh(..., symbols=("AVGO", "NVDA"), now=now)
    assert result.timeframe is BarTimeframe.MINUTE
    assert result.data_cutoff == datetime(2026, 10, 5, 14, 31, tzinfo=UTC)
    assert {spec.symbol for spec in store.specs} == {"AVGO", "NVDA"}
    assert all(spec.window_start == datetime(2026, 10, 5, 14, 30, tzinfo=UTC) for spec in store.specs)


def test_closed_session_requests_latest_completed_trading_day() -> None:
    now = datetime(2026, 10, 4, 12, tzinfo=UTC)  # Sunday
    result = request_watchlist_market_data_refresh(..., symbols=("NVDA",), now=now)
    assert result.timeframe is BarTimeframe.DAY
    assert result.data_cutoff == datetime(2026, 10, 2, 20, tzinfo=UTC)


def test_refresh_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        request_watchlist_market_data_refresh(..., now=datetime(2026, 10, 5, 14, 31))
```

Also assert:

- only monitored symbols supplied by the caller are scheduled;
- zero symbols returns `NO_SYMBOLS` and publishes nothing;
- the selected coverage is IEX when the configured entitlement is IEX;
- no valid Alpaca entitlement returns an explicit unavailable result and no job;
- duplicate job identifiers are deduplicated before publish;
- only IDs confirmed `QUEUED` by the injected eligibility callback are published;
- each publish request names `stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job` and queue `ingestion-low`;
- the service never imports or invokes research, portfolio, or broker execution code.

**Step 2: Run the focused tests to verify RED**

Run:

```bash
PYTHONPATH=backend/src UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/workers/test_watchlist_refresh.py -q
```

Expected: collection fails because `watchlist_refresh` does not exist.

**Step 3: Implement the minimal scheduler service**

Create these closed application types:

```python
class WatchlistRefreshStatus(StrEnum):
    QUEUED = "queued"
    ALREADY_QUEUED = "already_queued"
    NO_SYMBOLS = "no_symbols"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WatchlistRefreshResult:
    status: WatchlistRefreshStatus
    job_ids: tuple[UUID, ...]
    symbol_count: int
    requested_at: datetime
    data_cutoff: datetime | None
    timeframe: BarTimeframe | None
    feed: MarketDataCoverage | None
    message: str
```

Implement `request_watchlist_market_data_refresh(...)` using only injected symbols, `BackfillJobStore`, entitlement, clock, queued-job eligibility, and publisher:

- call `require_aware(now).astimezone(UTC)`;
- select IEX for the current operator entitlement (do not infer SIP);
- use `MarketCalendar().session_at(now)`;
- active session: floor to a complete minute and schedule `[cutoff - 1 minute, cutoff]` with `BarTimeframe.MINUTE` and `DataPurpose.REALTIME_CONTEXT`;
- closed session: call `latest_completed_market_cutoff(now, cutoff=time(16, 0))`, schedule `[cutoff - 1 day, cutoff]` with `BarTimeframe.DAY` and `MarketSession.REGULAR`;
- call existing `schedule_alpaca_backfills(..., max_jobs=1)` per symbol;
- deduplicate job IDs, publish only eligible queued IDs, and derive `queued` versus `already_queued` from whether any publish occurred;
- return data, never provider success claims.

Keep the service provider-transport free: it admits and dispatches work but never calls Alpaca synchronously.

**Step 4: Run the focused tests to verify GREEN**

Run the same pytest command.

Expected: all new unit tests pass.

**Step 5: Run nearby scheduler regression tests**

Run:

```bash
PYTHONPATH=backend/src UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/workers/test_schedules.py backend/tests/unit/workers/test_watchlist_refresh.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/src/stock_platform/application/ingestion/watchlist_refresh.py backend/tests/unit/workers/test_watchlist_refresh.py
git commit -m "feat: schedule bounded Watchlist market refreshes"
```

### Task 2: Add the paper-only FastAPI command contract

**Files:**
- Modify: `backend/src/stock_platform/api/schemas/rest.py`
- Modify: `backend/src/stock_platform/api/routes/rest.py`
- Modify: `backend/tests/contract/api/test_rest_contract.py`
- Create: `backend/tests/integration/api/test_watchlist_refresh.py`

**Step 1: Write failing OpenAPI and endpoint tests**

Add `("POST", "/api/v1/watchlist/refresh-market-data")` to `LOCKED_OPERATIONS` and assert the `202` response references a closed `WatchlistMarketDataRefreshResponse` schema.

In the integration test, seed two monitored Watchlist rows and one disabled row. Override settings with `environment="paper"`, IEX credentials, entitlement coverage, and entitlement version. Replace the scheduler/publisher seam and assert:

```python
response = client.post(
    "/api/v1/watchlist/refresh-market-data",
    headers={"Authorization": "Bearer test-admin-token"},
)
assert response.status_code == 202
assert response.json()["status"] == "queued"
assert response.json()["symbol_count"] == 2
assert response.json()["feed"] == "IEX"
assert response.json()["requested_at"].endswith("+00:00")
```

Also test:

- unauthenticated request returns `403`;
- `fixture` environment returns an explicit conflict/forbidden response and creates no job;
- missing Alpaca entitlement returns an explicit unavailable response and creates no job;
- the disabled symbol is not scheduled;
- publisher failure returns a sanitized `503` and does not claim an update completed;
- repeated requests return the same active IDs and do not add active jobs.

**Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=backend/src UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/contract/api/test_rest_contract.py backend/tests/integration/api/test_watchlist_refresh.py -q
```

Expected: FAIL because the endpoint and schema are absent.

**Step 3: Add the closed response schema**

Add:

```python
class WatchlistMarketDataRefreshResponse(StrictModel):
    status: Literal["queued", "already_queued", "no_symbols", "unavailable"]
    job_ids: list[UUID]
    symbol_count: int = Field(ge=0)
    requested_at: datetime
    data_cutoff: datetime | None
    timeframe: Literal["1Min", "1Day"] | None
    feed: Literal["IEX"] | None
    message: str
```

Pydantic's datetime validation must retain an aware UTC value supplied by the service.

**Step 4: Add the endpoint with explicit dependency boundaries**

Add a `202` route immediately after the Watchlist mutations. It must:

- require `get_human_actor` so this operator command cannot be triggered anonymously;
- require `settings.environment == "paper"`;
- derive the Alpaca entitlement from backend settings at `datetime.now(UTC)`;
- query only `watchlist_item.intraday_monitoring IS TRUE`, ordered by symbol;
- construct `IngestionJobStore(connection.engine)`;
- use a narrow publisher that sends only `run_alpaca_ingestion_job` to `ingestion-low`;
- translate unavailable configuration and dispatch failure to sanitized `ApiError`s;
- serialize enum values and UUIDs through the response model.

Do not add any broker route or order side effect.

**Step 5: Run endpoint tests to verify GREEN**

Run the same focused contract/integration command.

Expected: PASS.

**Step 6: Run ingestion and API regressions**

Run:

```bash
PYTHONPATH=backend/src UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/unit/workers/test_watchlist_refresh.py \
  backend/tests/contract/api/test_rest_contract.py \
  backend/tests/integration/api/test_watchlist_refresh.py \
  backend/tests/integration/ingestion/test_alpaca_recovery.py -q
```

Expected: PASS.

**Step 7: Commit**

```bash
git add backend/src/stock_platform/api/schemas/rest.py backend/src/stock_platform/api/routes/rest.py backend/tests/contract/api/test_rest_contract.py backend/tests/integration/api/test_watchlist_refresh.py
git commit -m "feat: expose paper Watchlist refresh command"
```

### Task 3: Add a strict server-side API client contract

**Files:**
- Modify: `web/lib/server/watchlist-api.ts`
- Modify: `web/tests/watchlist-api.test.ts`

**Step 1: Write failing API-client tests**

Add tests that call `refreshWatchlistMarketData` and assert:

- exact POST URL `/api/v1/watchlist/refresh-market-data`;
- `Accept: application/json` and server-side `Authorization: Bearer …` headers;
- parsing of a valid aware-UTC `202` response;
- rejection of a naive `requested_at` or `data_cutoff`;
- rejection of unexpected status, timeframe, feed, UUID, or extra semantic shape;
- sanitized classification for timeout, network error, `403`, and `503`;
- secrets and upstream response bodies never appear in thrown messages.

Use this TypeScript shape:

```ts
export type WatchlistRefreshResult = {
  dataCutoff: string | null
  feed: 'IEX' | null
  jobIds: string[]
  message: string
  requestedAt: string
  status: 'queued' | 'already_queued' | 'no_symbols' | 'unavailable'
  symbolCount: number
  timeframe: '1Min' | '1Day' | null
}
```

**Step 2: Run the API-client tests to verify RED**

Run:

```bash
npm --prefix web test -- --run tests/watchlist-api.test.ts
```

Expected: FAIL because the client method does not exist.

**Step 3: Implement strict parsing and the POST client**

Add a closed parser using existing aware-instant utilities and UUID validation. Extend `WatchlistClientOptions` with an optional server-only `adminToken` and attach the bearer header only for this command. The Server Action reads `ADMIN_API_TOKEN` from `web/.env.local`; it must never use a `NEXT_PUBLIC_` name, return the value, or log it.

Require HTTP `202`; other success codes are contract failures.

**Step 4: Run the API-client tests to verify GREEN**

Run the same Vitest command.

Expected: PASS.

**Step 5: Commit**

```bash
git add web/lib/server/watchlist-api.ts web/tests/watchlist-api.test.ts
git commit -m "feat: add Watchlist refresh API client"
```

### Task 4: Add the Server Action and accessible update control

**Files:**
- Modify: `web/lib/watchlist-action-state.ts`
- Modify: `web/app/watchlist/actions.ts`
- Modify: `web/components/watchlist/watchlist-api-controls.tsx`
- Modify: `web/tests/watchlist-actions.test.ts`
- Modify: `web/tests/watchlist-route.test.tsx`

**Step 1: Write failing Server Action tests**

Mock `refreshWatchlistMarketData` and assert:

- API mode reads the server-only admin token and calls the client once;
- `queued` returns truthful copy such as `Refresh queued for 12 symbols.`;
- `already_queued` explains that a refresh is already processing;
- `no_symbols` and `unavailable` stay explicit;
- success revalidates `/watchlist` but failures do not;
- Fixture mode does not call FastAPI and returns an error state;
- caught errors return sanitized copy and no token/provider body.

**Step 2: Run action tests to verify RED**

Run:

```bash
npm --prefix web test -- --run tests/watchlist-actions.test.ts
```

Expected: FAIL because `refreshWatchlistAction` is absent.

**Step 3: Implement the minimal Server Action**

Add `refreshWatchlistAction(previousState, formData)` and a dedicated refresh state if the existing mutation state cannot express `queued` cleanly. The action must call only the new API client and `revalidatePath('/watchlist')` after an accepted response.

Read `ADMIN_API_TOKEN` only on the server. If it is absent, return a user-safe configuration error before fetch.

**Step 4: Write the failing component tests**

In `watchlist-route.test.tsx`, assert API Watchlist rendering includes:

- button `Update latest data`;
- disabled `Requesting…` label while the action is pending;
- a polite `aria-live` status for queued/already queued/no-symbol states;
- an alert role for failure;
- no update control in explicit Fixture mode;
- existing add/update/delete controls remain present.

**Step 5: Run component tests to verify RED**

Run:

```bash
npm --prefix web test -- --run tests/watchlist-route.test.tsx
```

Expected: FAIL because the control is absent.

**Step 6: Implement the update form**

Add a small `RefreshWatchlistForm` to the critical-summary heading/action area. Use `useActionState` plus `useFormStatus`; do not add client-side provider calls or optimistic price changes. The copy must distinguish request admission from provider completion.

Keep the current persisted timestamps visible. The existing `LiveDataRefresh` may reveal later database changes.

**Step 7: Run all focused frontend tests to verify GREEN**

Run:

```bash
npm --prefix web test -- --run \
  tests/watchlist-api.test.ts \
  tests/watchlist-actions.test.ts \
  tests/watchlist-route.test.tsx \
  tests/live-data-refresh.test.tsx
```

Expected: PASS.

**Step 8: Run static frontend checks**

Run:

```bash
npm --prefix web run lint
npm --prefix web run typecheck
```

Expected: PASS.

**Step 9: Commit**

```bash
git add web/lib/watchlist-action-state.ts web/app/watchlist/actions.ts web/components/watchlist/watchlist-api-controls.tsx web/tests/watchlist-actions.test.ts web/tests/watchlist-route.test.tsx
git commit -m "feat: add Watchlist update control"
```

### Task 5: Verify runtime truthfulness and failure behavior

**Files:**
- Modify: `web/e2e/watchlist-api.spec.ts`
- Modify: `web/e2e/api-failure-matrix.spec.ts`
- Modify: `docs/runbooks/provider-outage.md`

**Step 1: Add failing browser assertions**

Extend the API-mode browser coverage to assert:

- desktop and mobile expose the update button;
- one click shows queued/admitted copy rather than claiming prices are already updated;
- persisted timestamps remain the evidence until a worker writes a newer fact;
- a backend `503` shows Failure/Unavailable and never Fixture content;
- keyboard focus remains on the form status flow and the control has a visible focus state.

Use intercepted API responses for deterministic UI behavior. Do not fake provider completion as an end-to-end fact.

**Step 2: Run the focused browser tests to verify RED**

Run:

```bash
npm --prefix web exec playwright test e2e/watchlist-api.spec.ts e2e/api-failure-matrix.spec.ts
```

Expected: new assertions fail before the UI wiring is complete.

**Step 3: Make only the minimal accessibility/CSS fixes needed**

Adjust existing shared button/status styles rather than introducing a separate visual system. Preserve the compact MacBook Air layout and mobile wrapping.

**Step 4: Document operator behavior**

Update the outage runbook to state:

- the manual button admits durable jobs but does not start stopped workers;
- Celery worker, Redis, PostgreSQL, MinIO, and valid Alpaca credentials are required for completion;
- outside market hours the expected result is the latest completed trading session;
- provider/worker failure remains explicit and never falls back to Fixture data.

**Step 5: Run browser tests to verify GREEN**

Run the same Playwright command.

Expected: PASS at desktop and mobile projects configured by the repository.

**Step 6: Commit**

```bash
git add web/e2e/watchlist-api.spec.ts web/e2e/api-failure-matrix.spec.ts docs/runbooks/provider-outage.md
git commit -m "test: verify Watchlist refresh failure states"
```

### Task 6: Complete repository verification and evidence

**Files:**
- Modify: `docs/progress.md`

**Step 1: Run the full required gate**

Run:

```bash
make verify
```

Expected: all repository verification stages pass. Do not claim completion if any stage is skipped unexpectedly or fails.

**Step 2: Perform a live local smoke check when credentials and runtime are available**

Start only the documented paper runtime required for the smoke check. Click `Update latest data`, record the returned job IDs, verify the Celery worker processes them, and confirm PostgreSQL/MinIO receive the corresponding new lineage. Outside market hours, verify the cutoff is the most recently completed exchange session rather than the wall-clock time.

If the environment is intentionally stopped or credentials are unavailable, record the smoke check as blocked; never manufacture a passing result.

**Step 3: Record exact evidence**

Append to `docs/progress.md`:

- commit under test;
- focused backend results;
- focused frontend results;
- browser matrix results;
- `make verify` result;
- runtime smoke job IDs/cutoff, or the precise external blocker;
- confirmation that no live-broker path and no Fixture fallback were added.

**Step 4: Review the diff for forbidden scope**

Run:

```bash
git diff main...HEAD --check
git diff --stat main...HEAD
git status --short
```

Expected: no whitespace errors, only scoped files, and no secrets or runtime artifacts.

**Step 5: Commit verification evidence**

```bash
git add docs/progress.md
git commit -m "docs: record Watchlist refresh verification"
```

**Step 6: Request review**

Use `@superpowers:requesting-code-review` for a final code review. Resolve blocking findings with `@superpowers:receiving-code-review`, rerun affected focused tests and `make verify`, and only then prepare push/PR/merge work after explicit user authorization.
