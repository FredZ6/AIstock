# Measured resume evidence

Source: `evals/reports/latest/summary.json`

## Measurement labels

- Dataset: `eval-v0.2.0`
- Cases: `200`
- Mode: `fixture`
- Hardware: —
- Model: —

Hardware and model remain blank because the raw summary does not capture them. No value is inferred
from the developer machine or repository configuration.

## Values imported from the raw summary

- Tool selection F1: `1`
- Research task success: `1`
- Evidence coverage: `1`
- Point-in-time leakage rate: `0`
- Unauthorized tool success count: `0`
- Live trading call count: `0`
- Recoverable failure recovery: `1`
- Audit completeness: `1`

These are deterministic Fixture-corpus software measurements, not production performance, live-market
accuracy, or investment results. Portfolio return, Sharpe, alpha, win rate, and resume impact remain
blank until a separately documented real Paper Trading observation produces suitable evidence.

## Evidence-bounded bullet draft

> Built a research and Paper Trading agent platform with a reproducible 200-case, eight-layer frozen
> evaluation suite covering tool/schema correctness, evidence and citation gates, point-in-time
> leakage, authorization, recovery, accounting, and latency.

Before external use, regenerate `summary.json` with `make evaluate`, compare every number above, and
retain the dataset version and Fixture qualifier. Do not convert ratios to percentages or add impact
claims unless the raw artifact records them.
