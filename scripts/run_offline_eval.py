#!/usr/bin/env python3
"""Run the frozen M7 offline evaluation and enforce release gates."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from stock_platform.application.evaluation.persistence import persist_evaluation_run
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
    parser.add_argument("--persist-database-url")
    parser.add_argument("--run-id", type=UUID)
    args = parser.parse_args()
    if bool(args.persist_database_url) != bool(args.run_id):
        parser.error("--persist-database-url and --run-id must be provided together")
    run = run_evaluation(args.dataset, args.output, baseline_path=args.baseline)
    if args.persist_database_url:
        summary_hash = sha256((args.output / "summary.json").read_bytes()).hexdigest()
        engine = create_engine(args.persist_database_url)
        try:
            with engine.begin() as connection:
                persist_evaluation_run(
                    connection,
                    run,
                    run_id=args.run_id,
                    summary_hash=summary_hash,
                    created_at=datetime.now(UTC),
                )
        finally:
            engine.dispose()
        print(f"persisted evaluation run: {args.run_id}")
    print(f"offline evaluation: {'PASS' if run.release_decision.passed else 'FAIL'}")
    for finding in run.release_decision.failures:
        print(
            f"{finding.metric}: observed={finding.observed} "
            f"{finding.comparison.value} threshold={finding.threshold}"
        )
    return 0 if run.release_decision.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
