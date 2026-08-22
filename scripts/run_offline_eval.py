#!/usr/bin/env python3
"""Run the frozen M7 offline evaluation and enforce release gates."""

from __future__ import annotations

import argparse
from pathlib import Path

from stock_platform.application.evaluation.runner import run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets"))
    parser.add_argument("--output", type=Path, default=Path("reports/evaluation"))
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evals/baselines/eval-v0.2.0.json"),
    )
    args = parser.parse_args()
    run = run_evaluation(args.dataset, args.output, baseline_path=args.baseline)
    print(f"offline evaluation: {'PASS' if run.release_decision.passed else 'FAIL'}")
    for finding in run.release_decision.failures:
        print(
            f"{finding.metric}: observed={finding.observed} "
            f"{finding.comparison.value} threshold={finding.threshold}"
        )
    return 0 if run.release_decision.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
