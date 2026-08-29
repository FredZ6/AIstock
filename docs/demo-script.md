# Ten-minute interview demo

## Preparation

Run `make smoke`. Confirm `M8 fixture demo: PASS` and open the application in Fixture Mode. If a
browser cannot be used, show the generated files in `evals/reports/latest/screenshots/`.

## Ten-minute walkthrough

### 0:00–1:00 — Product and safety boundary

Open Today. Explain that the system is research and Paper Trading only, that current market widgets
are reference-only, and that Fixture data is frozen synthetic evidence rather than current quotes.

### 1:00–3:00 — NVDA research and evidence conflict

Open `/research/NVDA`. Trace the NVDA research result through Report → Claim → Evidence → ToolCall →
provider and aware `available_at`. Show the `CONTRADICTS` link and the `CONFLICTED` EvidenceGap. The
backend scripted scenario forces `ABSTAIN` when critical evidence conflicts.

Fallback: `01-research.png`.

### 3:00–4:00 — Deterministic alert

Open Alerts and locate `alert-nvda-volume-001`. Explain that price/volume features, cooldown identity,
severity, materiality, thesis link, and outbox are deterministic; an LLM explanation can fail without
suppressing the deterministic alert.

### 4:00–6:00 — Paper rebalance, fill, and Risk Reject

Open Portfolio. Show the next-eligible-bar PaperFill and CashLedger, then `risk-decision-001` with
`REJECTED`. Explain the separation between ResearchOpinion and PortfolioAction and that rejected
intents cannot become fills.

### 6:00–7:00 — NAV and drawdown

Use the performance selector to show NAV and drawdown. Review Cash, QQQ, Equal weight, and Momentum
benchmarks. All money is Decimal and all fills are simulated.

Fallback: `02-portfolio.png`.

### 7:00–8:30 — Weekly Review and policy control

Open Weekly Review. Show matured thesis outcomes, confidence calibration, point-in-time replay, and
the Candidate Lesson. The smoke scenario exercises the real append-only approval insert inside a
rollback-only transaction probe so repeated demos do not accumulate audit fixtures; the visible page
remains the frozen fixture artifact. Point out the human approval, the explicit unapproved activation
rejection message, `Unapproved activation rejected`; approval never activates a policy
automatically.

Fallback: `03-weekly-review.png`.

### 8:30–10:00 — Offline evaluation report

Open Eval & Admin. Show the Offline evaluation report, dataset version, 200 cases, gate policy, and
PASS/FAIL state loaded from `evals/reports/latest/summary.json`. Finish by opening `report.html` and
one raw case hash. These are Fixture software-quality measurements, not production performance.

Fallback: `04-eval.png`.

## Recovery fallback

If the UI cannot start, use `demo-manifest.json`, `summary.json`, `report.html`, and the four
screenshots. Never substitute live data, invented credentials, or remembered metric values.
