#!/usr/bin/env python3
"""Prepare and observe one real idempotent Celery research recovery probe."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from stock_platform.application.runs import admit_run
from stock_platform.infrastructure.db.models.tables import agent_run


def prepare(database_url: str) -> UUID:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            correlation_id = uuid4()
            admitted = admit_run(
                connection,
                max_active_runs=100,
                run_type="RESEARCH",
                idempotency_key=f"recovery-probe-{correlation_id}",
                payload={"symbol": "NVDA", "recovery_probe": True},
                symbol="NVDA",
                decision_time=datetime(2026, 8, 16, tzinfo=UTC),
                data_cutoff=datetime(2026, 8, 16, tzinfo=UTC),
                correlation_id=correlation_id,
            )
            return admitted.id
    finally:
        engine.dispose()


def wait_for_status(database_url: str, run_id: UUID, expected: str, timeout: float) -> None:
    engine = create_engine(database_url)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                status = connection.execute(
                    select(agent_run.c.status).where(agent_run.c.id == run_id)
                ).scalar_one()
            if status == expected:
                return
            if status in {"FAILED", "CANCELLED"}:
                raise RuntimeError(f"recovery probe ended as {status}")
            time.sleep(0.2)
    finally:
        engine.dispose()
    raise TimeoutError(f"recovery probe did not reach {expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "wait"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--status", default="COMPLETED")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if args.action == "prepare":
        print(prepare(args.database_url))
        return
    if args.run_id is None:
        parser.error("--run-id is required for wait")
    wait_for_status(args.database_url, UUID(args.run_id), args.status, args.timeout)


if __name__ == "__main__":
    main()
