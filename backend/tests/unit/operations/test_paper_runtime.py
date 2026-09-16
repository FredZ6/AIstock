from pathlib import Path

import pytest
from stock_platform.operations.paper_runtime import (
    RuntimeConfigurationError,
    build_runtime_plan,
)

ROOT = Path(__file__).resolve().parents[4]


def _paper_environment() -> dict[str, str]:
    return {
        "ENVIRONMENT": "paper",
        "WEB_DATA_MODE": "api",
        "API_BASE_URL": "http://127.0.0.1:8000",
        "ALPACA_DATA_KEY": "configured-key",
        "ALPACA_DATA_SECRET": "configured-secret",
        "ALPACA_ENTITLEMENT_COVERAGE": "IEX",
        "ALPACA_ENTITLEMENT_VERSION": "operator-verified-test",
    }


def test_paper_runtime_plan_is_complete_and_separates_ingestion_queue() -> None:
    plan = build_runtime_plan(ROOT, _paper_environment())

    assert plan.infrastructure == ("postgres", "minio", "redis")
    assert plan.migration[-4:] == ("-c", "backend/alembic.ini", "upgrade", "head")
    assert tuple(process.name for process in plan.processes) == (
        "api",
        "scheduler-worker",
        "ingestion-worker",
        "beat",
        "alpaca-stream",
        "web",
    )
    assert plan.bootstrap_tasks == (
        "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion",
        "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
    )
    commands = {process.name: process.command for process in plan.processes}
    assert "--queues=celery" in commands["scheduler-worker"]
    assert "--queues=ingestion-low" in commands["ingestion-worker"]
    assert "scripts/run_alpaca_stream.py" in commands["alpaca-stream"]
    assert commands["web"][-2:] == ("--hostname", "127.0.0.1")
    assert "--" not in commands["web"]
    assert dict(plan.environment)["WEB_DATA_MODE"] == "api"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        ("ENVIRONMENT", "fixture", "ENVIRONMENT=paper"),
        ("WEB_DATA_MODE", "fixture", "WEB_DATA_MODE=api"),
        ("ALPACA_DATA_KEY", "", "Alpaca market-data credentials"),
        ("ALPACA_ENTITLEMENT_COVERAGE", "SIP", "IEX"),
    ),
)
def test_paper_runtime_fails_closed_for_unsafe_or_incomplete_configuration(
    name: str,
    value: str,
    message: str,
) -> None:
    environment = _paper_environment() | {name: value}

    with pytest.raises(RuntimeConfigurationError, match=message):
        build_runtime_plan(ROOT, environment)


def test_makefile_exposes_one_managed_paper_runtime_command() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    verification = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")

    assert "paper-runtime:" in makefile
    assert "scripts/run_paper_runtime.py" in makefile
    assert "make paper-runtime" in readme
    assert ".runtime/logs" in readme
    assert "scripts/run_paper_runtime.py" in verification
