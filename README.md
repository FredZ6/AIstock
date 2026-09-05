# AI Agent 美股科技研究与模拟投资平台

Evidence-grounded US technology research and paper-trading simulation. The repository is implemented
through **M8 Interview-ready Task 18** with a reproducible credential-free demo, measured evaluation
evidence, and interview documentation.

## Product boundary

This system supports research and **Paper Trading only**. It is not investment advice and contains
no live-broker endpoint, credential, feature flag, or real-money execution path. An LLM cannot place
orders, send notifications, change risk rules, approve lessons, or activate policies. Historical
decisions only use facts satisfying `event_time <= decision_time` and
`available_at <= decision_time`.

## Requirements

- Python 3.12
- uv
- Node.js 22 or newer
- pnpm 11
- Docker with Compose

## Quick start

Clean-room M8 acceptance requires no provider credential:

```bash
make clean-fixtures
make bootstrap
make seed
make up
make smoke
make verify
```

For routine development with running services:

```bash
make bootstrap
make up
make seed
make verify
```

Copy `.env.example` to `.env` only when overriding local defaults. Provider credentials are not
required for fixture-mode M1. `make seed` idempotently writes frozen raw objects to MinIO and
normalized point-in-time records to PostgreSQL. `make smoke` writes the demo manifest, evaluation
report, and fallback screenshots under `evals/reports/latest/`.

## Provider modes and data licensing

### SEC read-only setup

In your private root `.env`, set `SEC_USER_AGENT="AIstock/0.2 YOUR_REAL_EMAIL"`.
Replace the placeholder with your reachable contact email. The adapter requires
`application/version email` (not `Name App contact=email`). This is an HTTP identity,
not a SEC API key. Do not commit personal configuration. Restart API/ingestion workers
after changing it, since settings are loaded/cached by the running processes.

To validate only SEC transport, without writing new production facts:

```bash
set -a
source .env
set +a
LIVE_PROVIDER_TESTS=1 UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/contract/providers/test_live_adapter_contracts.py \
  -q -k sec_live_contract
```

This checks the real company-facts response identity and structure. It does not prove
MinIO/PostgreSQL ingestion or make a newly fetched response eligible for an earlier
decision cutoff. Keep IEX coverage declared unless SIP entitlement has actually been verified.

The Next.js frontend requires an explicit server-side `WEB_DATA_MODE`:

- `WEB_DATA_MODE=fixture` renders only the frozen synthetic demonstration data.
- `WEB_DATA_MODE=api` requires `API_BASE_URL`, reads persisted Watchlist configuration from FastAPI,
  and shows explicit `Failure` or `Degraded` states when the service or enrichment is unavailable.

API mode never falls back to Fixture data. `API_BASE_URL` is server-only; do not create a
`NEXT_PUBLIC_API_BASE_URL` variable. To run the current API-backed Watchlist slice locally, start
FastAPI and PostgreSQL, then start Next.js with:

```bash
WEB_DATA_MODE=api API_BASE_URL=http://127.0.0.1:8000 pnpm --dir web dev
```

The API-mode Today, Watchlist, Stock Research, and Portfolio routes use persisted FastAPI facts for
all research, portfolio, alert, and paper-trading decisions. Today also embeds an isolated,
read-only TradingView current-market reference; it is visibly labelled as external context, is not
persisted evidence, and never enters decision-time calculations. Market evidence reads require an
aware `decision_time` and enforce `available_at <= decision_time`.
The read surface includes `/api/v1/market-data/quotes`, `/api/v1/market-data/bars/{symbol}`,
`/api/v1/data-quality`, and evidence-backed `/api/v1/providers/health`. If a provider, contract, or
database read fails, the affected route renders an explicit Failure or Degraded state; it never
loads the fixture snapshot as a recovery path.

For continuous local ingestion, run one Celery worker for the default scheduler queue, one for the
`ingestion-low` persistence queue, Celery Beat, and the read-only Alpaca stream supervisor in
separate terminals. All processes must source the gitignored root `.env`; the frontend uses the
separate gitignored `web/.env.local`. The Alpaca process connects only to Market Data and has no
brokerage or live-order path.

Fixture manifests identify their synthetic provenance and license; they are not real quotations,
filings, analyst research, or news. API Mode uses read-only Alpaca Market Data/News, SEC EDGAR, and
Alpha Vantage earnings adapters when separately configured. Missing credentials remain explicit
Unavailable/Degraded states. Alpaca IEX is partial-market context and is never represented as
consolidated SIP. Third-party data remains subject to its provider's terms and redistribution rules.

## Architecture

Deterministic code owns time eligibility, alerts, risk, accounting, policy authorization, and release
gates. Bounded graphs structure research, portfolio proposals, and weekly reviews; PostgreSQL owns
authoritative facts, MinIO preserves raw objects, and Redis transports recoverable work/SSE events.
The append-only lineage is:

```text
RawDataObject → NormalizedRecord → DerivedMetric → Evidence → Claim
              → InvestmentThesis → DecisionSnapshot → Paper decision / review
```

See [docs/architecture.md](docs/architecture.md) for component ownership and trust boundaries.

## M1 data plane

- Five-symbol frozen fixtures cover normal, delayed, missing, conflict, filing, split, and anomaly
  scenarios.
- SEC, Alpaca, and FMP adapters are GET-only research-data clients. They have no brokerage or order
  surface and require both raw-object and normalized-record persistence before returning data.
- Three Streamable HTTP MCP servers expose only the approved SEC, market, and analyst research
  tools under `stock_platform.mcp_servers`.
- Provider circuit state is available through `FallbackPolicy.health()` for the Task 14 control
  plane to expose at `/api/v1/providers/health`; the HTTP control plane itself remains out of M1.

## M2–M5 capabilities

- Bounded research agents produce evidence-grounded, policy-version-pinned decisions and deterministic
  decision diffs without granting an LLM execution authority.
- Alerts use deterministic rule evaluation, transactional outbox delivery, idempotency, and explicit
  approval boundaries.
- Paper execution uses next-eligible-bar fills, immutable fill and double-entry ledger facts,
  point-in-time Corporate Actions, and deterministic NAV reconstruction.
- The Task 12 Portfolio graph freezes research and market context, maps ResearchOpinion separately from
  PortfolioAction, applies a deterministic Risk Gateway, binds each pending order to exact immutable
  risk authorization, and reports Cash/QQQ/equal-weight/momentum benchmarks and portfolio metrics.
- The Task 13 weekly review computes matured Decimal outcomes, attributes frozen error categories,
  emits duplicate-safe Candidate Lessons, evaluates prior Lessons against later decisions without
  future leakage, and records human approval/rejection plus transactional policy audit facts. No Lesson
  can activate itself or mutate an online prompt.

## M6 product surface

- The FastAPI control plane provides the locked REST contract, idempotent run admission, and durable
  SSE recovery developed in Task 14.
- Eight responsive Next.js pages provide Today, Watchlist, Research, Run Trace, Portfolio, Alerts,
  Weekly Review, and Eval/Admin workflows with explicit loading and failure-state components.
- Fixture-mode decisions remain traceable through Report, Claim, Evidence, ToolCall, provider, and
  aware timestamps; paper fills and cash-ledger fixtures reconcile from opening cash to current cash.

## M7 quality gates

- A frozen 200-case offline evaluation suite enforces deterministic release gates and reproducible
  evidence artifacts.
- Correlation IDs persist from HTTP admission through worker/graph execution, MCP audit, PostgreSQL
  AgentEvent, and durable SSE replay. Logs redact sensitive content and metrics forbid unbounded
  symbol/run labels.
- Authenticated Grafana, Prometheus, and OpenTelemetry Collector services bind only to localhost.
  Recovery runbooks cover provider outage, stuck runs, Redis loss, database restore, and human-only
  policy rollback with explicit RPO/RTO assumptions.
- API, Celery, and MCP processes must inherit the same exported
  `PROMETHEUS_MULTIPROC_DIR=$PWD/.runtime/prometheus`; `/metrics` aggregates those process-local
  files for the single Prometheus API scrape target. Clear that directory only while every runtime
  process is stopped.

## Security

The tool allowlist is deny-by-default, provider text is isolated from instructions, secrets are
redacted, and policy changes require an authenticated human plus compare-and-swap revision. Local
infrastructure binds to localhost. See [docs/security.md](docs/security.md) and `docs/runbooks/`.

## Evaluation

`make evaluate` runs the frozen 200-case, eight-layer offline suite and writes raw case, summary,
JUnit, and HTML evidence to `evals/reports/latest/`. `make smoke` additionally runs the deterministic
interview scenario and creates fallback screenshots. Every displayed or resume-facing number must
link to the generated raw artifact; Fixture results are software evidence, not production alpha.

See [docs/testing.md](docs/testing.md), [docs/demo-script.md](docs/demo-script.md),
[docs/interview-guide.md](docs/interview-guide.md), and
[docs/resume-metrics.md](docs/resume-metrics.md).

## Limitations

- Fixture Mode is synthetic and frozen; it does not prove current market correctness or returns.
- Credential/entitlement-gated live-provider tests skip explicitly and are never reported as passed.
- Analyst targets and options may remain typed Unavailable; SIP requires proven entitlement.
- Paper fills model next-eligible-bar execution rather than every real venue/liquidity effect.
- Generated reports and screenshots are ignored by Git and must be regenerated with `make smoke`.
