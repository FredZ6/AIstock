"""Fail-closed process plan for the local paper-only runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigurationError(ValueError):
    """Raised before any process starts when the runtime is unsafe or incomplete."""


@dataclass(frozen=True)
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    ready_url: str | None = None


@dataclass(frozen=True)
class RuntimePlan:
    infrastructure: tuple[str, ...]
    migration: tuple[str, ...]
    processes: tuple[ManagedProcess, ...]
    bootstrap_tasks: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]


def _required(environment: Mapping[str, str], name: str, message: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RuntimeConfigurationError(message)
    return value


def build_runtime_plan(repo_root: Path, environment: Mapping[str, str]) -> RuntimePlan:
    """Build a deterministic plan without starting services or exposing secrets."""
    root = repo_root.resolve()
    if environment.get("ENVIRONMENT") != "paper":
        raise RuntimeConfigurationError("paper runtime requires ENVIRONMENT=paper")
    if environment.get("WEB_DATA_MODE") != "api":
        raise RuntimeConfigurationError("paper runtime requires WEB_DATA_MODE=api")
    api_base_url = _required(
        environment,
        "API_BASE_URL",
        "paper runtime requires an API_BASE_URL",
    ).rstrip("/")
    _required(
        environment,
        "ALPACA_DATA_KEY",
        "Alpaca market-data credentials are required",
    )
    _required(
        environment,
        "ALPACA_DATA_SECRET",
        "Alpaca market-data credentials are required",
    )
    coverage = _required(
        environment,
        "ALPACA_ENTITLEMENT_COVERAGE",
        "explicit Alpaca IEX entitlement is required",
    ).upper()
    if coverage != "IEX":
        raise RuntimeConfigurationError("this runtime closure must preserve explicit IEX coverage")
    _required(
        environment,
        "ALPACA_ENTITLEMENT_VERSION",
        "an operator-verified Alpaca entitlement version is required",
    )

    python = str(root / ".venv" / "bin" / "python")
    celery = str(root / ".venv" / "bin" / "celery")
    uvicorn = str(root / ".venv" / "bin" / "uvicorn")
    celery_app = "stock_platform.workers.celery_app:celery_app"
    runtime_dir = root / ".runtime"
    child_environment = {
        "API_BASE_URL": api_base_url,
        "ENVIRONMENT": "paper",
        "PYTHONPATH": str(root / "backend" / "src"),
        "UV_CACHE_DIR": str(root / ".uv-cache"),
        "WEB_DATA_MODE": "api",
    }
    return RuntimePlan(
        infrastructure=("postgres", "minio", "redis"),
        migration=(
            python,
            "-m",
            "alembic",
            "-c",
            "backend/alembic.ini",
            "upgrade",
            "head",
        ),
        processes=(
            ManagedProcess(
                "api",
                (
                    uvicorn,
                    "stock_platform.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ),
                f"{api_base_url}/api/v1/health",
            ),
            ManagedProcess(
                "scheduler-worker",
                (
                    celery,
                    "-A",
                    celery_app,
                    "worker",
                    "--pool=solo",
                    "--concurrency=1",
                    "--loglevel=INFO",
                    "--queues=celery",
                    "--hostname=scheduler@%h",
                    "--pidfile=",
                ),
            ),
            ManagedProcess(
                "ingestion-worker",
                (
                    celery,
                    "-A",
                    celery_app,
                    "worker",
                    "--pool=solo",
                    "--concurrency=1",
                    "--loglevel=INFO",
                    "--queues=ingestion-low",
                    "--hostname=ingestion@%h",
                    "--pidfile=",
                ),
            ),
            ManagedProcess(
                "beat",
                (
                    celery,
                    "-A",
                    celery_app,
                    "beat",
                    "--loglevel=INFO",
                    f"--schedule={runtime_dir / 'celerybeat-schedule'}",
                    "--pidfile=",
                ),
            ),
            ManagedProcess(
                "alpaca-stream",
                (python, "scripts/run_alpaca_stream.py"),
            ),
            ManagedProcess(
                "web",
                ("pnpm", "--dir", "web", "dev", "--hostname", "127.0.0.1"),
                "http://127.0.0.1:3000/",
            ),
        ),
        bootstrap_tasks=(
            "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion",
            "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
        ),
        environment=tuple(sorted(child_environment.items())),
    )


def render_command(command: Sequence[str]) -> str:
    """Return a non-shell representation suitable for operator diagnostics."""
    return " ".join(command)
