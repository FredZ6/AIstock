# FRE-43 Production Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Populate the authoritative Watchlist with durable Research decisions, produce an auditable paper-only Portfolio result, persist deterministic Alerts, and generate point-in-time Weekly Review outcomes without Fixture fallback or automatic policy activation.

**Architecture:** Reuse the existing bounded Research, Portfolio, Alert, and Weekly Review graphs and their append-only PostgreSQL stores. Add only the missing runtime orchestration and real-data adapters: catch-up scheduling at a canonical market cutoff, isolated Celery queues, an explicit IEX `NO_ACTION` portfolio path, persisted alert evaluation, and mature-decision review loading. Every workflow remains idempotent through existing run keys and database uniqueness constraints.

**Tech Stack:** Python 3.12, Celery, LangGraph, SQLAlchemy 2, PostgreSQL/TimescaleDB, Redis Streams, MinIO, Pytest/Hypothesis, FastAPI, Next.js, Vitest, Playwright.

---

## Locked constraints

- Notion v0.2 remains authoritative.
- Research consumes only records satisfying `event_time <= decision_time` and `available_at <= decision_time`.
- Portfolio consumes immutable `DecisionSnapshot` rows and the four pinned policy versions.
- The configured IEX entitlement is research context only. It must never be relabeled SIP or used to create a simulated fill. Without SIP, Portfolio persists an auditable `NO_ACTION`/cash-only result.
- Alerts are deterministic. An LLM explanation is optional and cannot suppress the base alert or notification outbox fact.
- Weekly Review evaluates only mature decisions; future lessons never enter historical replay.
- Candidate lessons remain candidate/rejected/approved audit facts. No code path automatically activates a policy.
- API mode never substitutes Fixture data, and no live-broker endpoint, credential, flag, or execution path may be added.

### Task 1: Isolate durable agent execution and bootstrap the latest closed session

**Files:**
- Modify: `backend/src/stock_platform/workers/celery_app.py`
- Modify: `backend/src/stock_platform/operations/paper_runtime.py`
- Modify: `backend/src/stock_platform/workers/schedules.py`
- Modify: `scripts/verify-recovery.sh`
- Modify: `docs/runbooks/stuck-run.md`
- Test: `backend/tests/unit/workers/test_schedules.py`
- Test: `backend/tests/unit/operations/test_paper_runtime.py`
- Test: `backend/tests/integration/api/test_scheduling.py`

**Step 1: Write failing queue and catch-up tests**

Add assertions that Research, Portfolio, Alert Monitor, and Weekly Review tasks route to separate `agent-research`, `agent-portfolio`, `agent-alert`, and `agent-review` queues. Assert the managed runtime starts one worker for each queue. Add a scheduling test proving a weekend/startup timestamp resolves to the latest completed New York market cutoff and reuses the same idempotency key on retry.

**Step 2: Verify RED**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/unit/workers/test_schedules.py \
  backend/tests/unit/operations/test_paper_runtime.py \
  backend/tests/integration/api/test_scheduling.py -q
```

Expected: FAIL because agent task routes/workers and catch-up scheduling do not exist.

**Step 3: Implement the minimum orchestration**

- Add explicit Celery routes for the four existing task names.
- Add four managed workers without changing task implementations.
- Add a pure UTC-aware helper that computes the latest eligible US market cutoff using the existing New York calendar rules.
- Add one bootstrap task that schedules the due Research/Portfolio/Alert/Review runs using their existing deterministic schedule keys.
- Keep recovery scripts consuming every documented queue, including the legacy `celery` drain queue.

**Step 4: Verify GREEN and integration**

Run the focused command above, then:

```bash
./scripts/verify-recovery.sh
```

Expected: all focused tests and recovery checks pass; replaying bootstrap creates no duplicate `agent_run` rows.

**Step 5: Record and commit**

Update `docs/progress.md` with RED/GREEN commands and exit codes, then commit the task.

### Task 2: Populate idempotent point-in-time Research for the Watchlist

**Files:**
- Modify: `backend/src/stock_platform/workers/research_tasks.py`
- Modify: `backend/src/stock_platform/application/market_data/repositories.py` only if a persisted supported feed cannot currently be reconstructed
- Modify: `backend/src/stock_platform/application/research/persistence.py` only for a proven retry/lineage defect
- Test: `backend/tests/integration/research/test_daily_research.py`
- Test: `backend/tests/integration/api/test_scheduling.py`
- Test: `backend/tests/integration/runtime/test_research_population.py` (create)

**Step 1: Write failing population tests**

Seed two authoritative Watchlist securities with persisted non-Fixture raw/normalized market and SEC facts. Schedule twice at the same cutoff, execute the admitted runs, and assert:

- one durable Research run and one `DecisionSnapshot` per symbol/cutoff;
- all four policy versions, prompt/model version, and data cutoff are pinned;
- the complete Raw → Normalized → Derived → Evidence → Claim → Thesis → Decision path exists;
- IEX creates the typed market-data gap and may cause ABSTAIN/limitations but never Fixture evidence;
- retry/recovery does not duplicate decisions, evidence, events, or tool calls.

**Step 2: Verify RED**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/integration/runtime/test_research_population.py -q
```

Expected: FAIL at the first missing production-loop behavior.

**Step 3: Implement the minimum runtime adapter**

Use `PostgresResearchProvider`, `DailyResearchGraph`, `PostgresResearchStore`, and the existing run-control/checkpoint layer. Add only the data reconstruction or retry guard demonstrated missing by RED. Do not add another Agent, graph, provider, or Fixture fallback.

**Step 4: Verify GREEN and lineage**

Run the new population test, existing daily Research integration tests, run-admission tests, and relevant provider/PIT contract tests.

**Step 5: Real runtime smoke**

Start the managed paper runtime, dispatch the canonical catch-up once, and record per-symbol terminal status and decision IDs. Stop the runtime before database-wide verification.

**Step 6: Record and commit**

Update `docs/progress.md`; commit only after the focused and real-runtime evidence is captured.

### Task 3: Persist a paper-only Portfolio result from immutable Research snapshots

**Files:**
- Modify: `backend/src/stock_platform/workers/schedules.py`
- Modify: `backend/src/stock_platform/workers/portfolio_tasks.py`
- Modify: `backend/src/stock_platform/application/portfolio/accounting.py` only if cash-only NAV cannot be persisted idempotently
- Modify: `backend/src/stock_platform/application/portfolio/risk.py` only if an explicit entitlement rejection reason is absent
- Test: `backend/tests/integration/api/test_scheduling.py`
- Test: `backend/tests/integration/portfolio/test_portfolio_worker.py` (create)
- Test: `backend/tests/integration/portfolio/test_paper_accounting_store.py`
- Test: `backend/tests/integration/portfolio/test_rebalance_run.py`

**Step 1: Write failing paper-boundary tests**

Assert that IEX does not silently suppress the scheduled Portfolio audit. The admitted run must consume the same-cutoff immutable Research snapshots, persist `PortfolioAction.NO_ACTION`, an explicit risk/entitlement decision, opening CashLedger and cash-only `PortfolioNav`, and create no order or fill. Add a SIP fixture case proving approved orders still fill only on the next eligible bar and retry produces one fill/ledger effect.

**Step 2: Verify RED**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/integration/api/test_scheduling.py \
  backend/tests/integration/portfolio/test_portfolio_worker.py \
  backend/tests/integration/portfolio/test_paper_accounting_store.py \
  backend/tests/integration/portfolio/test_rebalance_run.py -q
```

Expected: FAIL because IEX currently returns no Portfolio run and therefore leaves no auditable cash/NAV result.

**Step 3: Implement the minimum denial and execution paths**

- Admit the run with its frozen `DENIED_NO_ACTION` market-data decision instead of dropping it.
- In the worker, load immutable Research snapshots and policy pins first.
- Persist a deterministic no-action/risk record plus cash ledger and NAV when SIP is unavailable.
- Retain the existing SIP-only `load_paper_execution_bars` and next-bar execution path unchanged for authorized data.

**Step 4: Verify GREEN, reconciliation, and recovery**

Run the focused suite plus ledger balance, unique fill, risk coverage, time-travel, and checkpoint recovery tests.

**Step 5: Record and commit**

Update `docs/progress.md` and commit.

### Task 4: Execute deterministic persisted Alerts with deduplicated outbox facts

**Files:**
- Modify: `backend/src/stock_platform/workers/research_tasks.py`
- Modify: `backend/src/stock_platform/application/alerting/outbox.py` only if batch/PIT reads need a minimal adapter
- Reuse: `backend/src/stock_platform/application/alerting/features.py`
- Reuse: `backend/src/stock_platform/application/alerting/rules.py`
- Test: `backend/tests/integration/alerting/test_alert_worker_runtime.py` (create)
- Test: `backend/tests/integration/alerting/test_market_replay.py`

**Step 1: Write failing runtime tests**

Seed cutoff-safe market bars and an active Thesis/evidence link, run the existing `ALERT_MONITOR` worker twice, and assert deterministic metrics, one `AlertEvent`, one `AlertThesisLink`, one notification outbox row per dedupe key, and no LLM dependency. Add unavailable-context and concurrent-recovery cases.

**Step 2: Verify RED**

Run the new worker-runtime test. Expected: FAIL because `monitor_market` currently counts visible bars but never evaluates or persists alerts.

**Step 3: Implement the minimum worker adapter**

Load only PIT-visible persisted bars, compute existing anomaly features, evaluate the existing versioned rule, resolve cutoff-safe Thesis context, and call `PostgresAlertStore.persist_alert`. Emit a structured completion event even when no rule fires. Do not send real notifications from the Agent; retain the outbox boundary.

**Step 4: Verify GREEN, replay, and dedupe**

Run the new worker tests and the complete market-replay suite, including concurrent dispatch, out-of-order revision, MinIO lineage and provider-failure degradation.

**Step 5: Record and commit**

Update `docs/progress.md` and commit.

### Task 5: Produce mature Weekly Review outcomes, calibration and replay safely

**Files:**
- Modify: `backend/src/stock_platform/workers/review_tasks.py`
- Modify: `backend/src/stock_platform/application/learning/persistence.py` only for a proven idempotency gap
- Modify: `backend/src/stock_platform/application/learning/replay.py` only for a proven benchmark/replay gap
- Test: `backend/tests/integration/learning/test_weekly_review_worker.py` (create)
- Test: `backend/tests/integration/learning/test_weekly_review.py`

**Step 1: Write failing worker tests**

Seed mature and pending immutable decisions, PIT-safe symbol/QQQ prices, and one prior validated lesson created before the review cutoff. Execute twice and assert:

- only mature decisions receive Outcomes; pending IDs stay pending;
- returns, excess return, MFE, MAE, risk-adjusted result and calibration are persisted;
- Thesis hit/miss and structured attribution are derivable from persisted facts;
- a prior lesson can produce forward replay, while future/unapproved lessons cannot;
- candidate lessons never become active automatically;
- retry preserves one immutable Weekly Review result.

**Step 2: Verify RED**

Run the new worker test. Expected: FAIL where the worker does not load eligible prior lessons/current benchmark inputs.

**Step 3: Implement the minimum worker input loader**

Load active decisions, mature price windows, QQQ benchmark facts and eligible validated candidate lessons under the same data cutoff. Pass them to the existing `WeeklyReviewGraph` and `PostgresWeeklyReviewStore`; do not add online model/risk/prompt mutation.

**Step 4: Verify GREEN and learning safety**

Run the complete Weekly Review integration suite, policy-approval security tests and time-travel tests.

**Step 5: Record and commit**

Update `docs/progress.md` and commit.

### Task 6: Close API/browser acceptance and milestone evidence

**Files:**
- Modify: `web/e2e/live-production-loop.spec.ts` (create)
- Modify: `backend/tests/contract/api/test_rest_contract.py` only if existing response schemas omit newly persisted facts
- Modify: `docs/api/openapi.yaml` only through `scripts/export_openapi.py`
- Modify: `docs/progress.md`
- Modify: Notion M8.2 delivery record and Linear FRE-43 comment/status

**Step 1: Write the live browser acceptance**

In API mode, assert Watchlist Research decisions are persisted, Portfolio displays cash/NAV and the explicit IEX no-action risk reason, Alerts displays persisted/deduped facts or an honest empty state, and Weekly Review displays mature outcomes/benchmark/calibration facts. Assert no Fixture substitution and no desktop/mobile overflow or serious accessibility violation.

**Step 2: Run affected integration gates**

Run concurrency/idempotency, recovery, lineage, risk rejection, alert dedupe and weekly maturity suites.

**Step 3: Run real-runtime browser matrix**

Start the managed paper runtime, run desktop/mobile Playwright against the real API, capture counts/IDs, then stop runtime writers.

**Step 4: Run complete verification**

```bash
make verify
```

Expected: exit 0 with exact pass/fail/skip counts recorded in `docs/progress.md`.

**Step 5: Review and deliver**

Inspect staged diff and remote diff, verify no secrets/Fixture fallback/live-broker path, commit and push the FRE-43 branch, create a stacked PR after PR #25, and move FRE-43 to `In Review`. Do not merge or mark Done without explicit authorization.
