# Product requirements v0.2 delivery summary

## Purpose

The platform helps an engineering reviewer research a bounded US technology Watchlist, inspect the
evidence behind conclusions, evaluate deterministic alerts, and simulate portfolio decisions without
granting an AI system control over real funds.

## Users and jobs

- A researcher reviews claims, supporting/contradicting evidence, gaps, freshness, and provenance.
- A portfolio reviewer inspects actions separately from opinions, immutable RiskDecisions, paper
  fills, the CashLedger, NAV, drawdown, and benchmark comparisons.
- A human policy owner reviews matured outcomes and Candidate Lessons, approves or rejects them, and
  separately controls activation or rollback.
- An engineer reproduces each decision through correlation IDs, append-only facts, evaluation
  artifacts, dashboards, and recovery runbooks.

## Locked safety requirements

- Research and Paper Trading only; no live brokerage or real-money configuration.
- UTC-aware datetimes and `Decimal` money throughout authoritative code.
- Historical eligibility requires both event time and availability time at or before the cutoff.
- LLM output is advisory and cannot execute orders, notify externally, mutate risk, or activate a
  policy.
- API mode never silently substitutes Fixture data.
- All resume and interview numbers must originate from reproducible raw artifacts.

## M8 acceptance scenario

From a clean checkout, Fixture Mode must seed without credentials and demonstrate: NVDA research,
an evidence conflict, one deterministic alert, a paper rebalance/fill, a Risk Reject, NAV/drawdown
and four benchmarks, Weekly Review, rejection of unapproved activation, human Candidate Lesson
approval, and the offline Eval report. `make smoke` and `make verify` must both exit 0.

The authoritative detailed specification remains the Notion v0.2 design and Codex executable
engineering specification. This file summarizes the shipped repository behavior; it does not
override those sources.
