# AI Agent 美股科技研究与模拟投资平台

Evidence-grounded US technology research and paper-trading simulation. The repository is implemented
through **M7 Quality Task 16**; Task 17 operational hardening remains in progress for the milestone.
It runs in **Fixture Mode** without provider credentials and cannot connect to a live broker.

## Requirements

- Python 3.12
- uv
- Node.js 22 or newer
- pnpm 11
- Docker with Compose

## Quick start

```bash
make bootstrap
make up
make seed
make verify
```

Copy `.env.example` to `.env` only when overriding local defaults. Provider credentials are not
required for fixture-mode M1. `make seed` idempotently writes frozen raw objects to MinIO and
normalized point-in-time records to PostgreSQL.

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

## Safety boundary

This repository is for research and paper trading only. It contains no live-broker URL,
credential, switch, endpoint, or order execution path.
