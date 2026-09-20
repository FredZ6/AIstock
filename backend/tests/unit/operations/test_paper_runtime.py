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
        "SEC_USER_AGENT": "AIstock test contact@example.com",
        "ALPHA_VANTAGE_API_KEY": "configured-alpha-key",
    }


def test_paper_runtime_plan_is_complete_and_separates_ingestion_queue() -> None:
    plan = build_runtime_plan(ROOT, _paper_environment())

    assert plan.infrastructure == ("postgres", "minio", "redis")
    assert plan.migration[-4:] == ("-c", "backend/alembic.ini", "upgrade", "head")
    assert tuple(process.name for process in plan.processes) == (
        "api",
        "scheduler-worker",
        "ingestion-worker",
        "research-ingestion-worker",
        "stream-worker",
        "research-worker",
        "portfolio-worker",
        "alert-worker",
        "review-worker",
        "beat",
        "alpaca-stream",
        "web",
    )
    assert plan.bootstrap_tasks == (
        "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion",
        "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
        "stock_platform.workers.schedules.schedule_sec_daily_ingestion",
        "stock_platform.workers.schedules.schedule_alpha_earnings_calendar",
        "stock_platform.workers.schedules.bootstrap_agent_runs",
    )
    commands = {process.name: process.command for process in plan.processes}
    assert "--queues=control" in commands["scheduler-worker"]
    assert "--queues=ingestion-low" in commands["ingestion-worker"]
    assert "--queues=research-ingestion" in commands["research-ingestion-worker"]
    assert "--queues=stream-events,celery" in commands["stream-worker"]
    assert "--queues=agent-research" in commands["research-worker"]
    assert "--queues=agent-portfolio" in commands["portfolio-worker"]
    assert "--queues=agent-alert" in commands["alert-worker"]
    assert "--queues=agent-review" in commands["review-worker"]
    assert "scripts/run_alpaca_stream.py" in commands["alpaca-stream"]
    assert commands["web"][-2:] == ("--hostname", "127.0.0.1")
    assert "--" not in commands["web"]
    assert dict(plan.environment)["WEB_DATA_MODE"] == "api"


def test_paper_runtime_only_bootstraps_optional_research_providers_when_configured() -> None:
    environment = _paper_environment()
    environment.pop("SEC_USER_AGENT")
    environment.pop("ALPHA_VANTAGE_API_KEY")

    plan = build_runtime_plan(ROOT, environment)

    assert plan.bootstrap_tasks == (
        "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion",
        "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
        "stock_platform.workers.schedules.bootstrap_agent_runs",
    )


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
