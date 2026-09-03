from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Connection, Engine
from stock_platform.api.dependencies import get_connection, get_settings
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import (
    cash_ledger,
    paper_portfolio_config,
    portfolio_initialization_request,
)
from stock_platform.settings import Settings


def _client(database_url: str) -> tuple[TestClient, Engine]:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)

    def connection_override() -> Iterator[Connection]:
        with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_connection] = connection_override
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="test", _env_file=None
    )
    return TestClient(app), engine


def test_singleton_paper_portfolio_initialization_is_audited_and_idempotent(
    isolated_database_url: str,
) -> None:
    client, engine = _client(isolated_database_url)
    effective_at = datetime(2026, 9, 1, 1, tzinfo=UTC)
    request = {"effective_at": effective_at.isoformat()}
    try:
        first = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper"},
            json=request,
        )
        replay = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper"},
            json=request,
        )

        assert first.status_code == replay.status_code == 200
        assert (
            first.json()
            == replay.json()
            == {
                "status": "READY",
                "portfolio_id": "10000000-0000-0000-0000-000000000001",
                "name": "default-paper",
                "initial_cash": "100000",
                "currency": "USD",
                "initialized_at": effective_at.isoformat().replace("+00:00", "Z"),
            }
        )
        assert first.headers["Idempotency-Replayed"] == "false"
        assert replay.headers["Idempotency-Replayed"] == "true"

        with engine.connect() as connection:
            config = connection.execute(select(paper_portfolio_config)).mappings().one()
            rows = (
                connection.execute(
                    select(cash_ledger).where(cash_ledger.c.portfolio_id == config["id"])
                )
                .mappings()
                .all()
            )
        historical = client.get(
            "/api/v1/portfolio", params={"decision_time": effective_at.isoformat()}
        )
        assert historical.status_code == 200
        assert historical.json()["status"] == "EMPTY"
        assert historical.json()["configuration"] is None
        assert historical.json()["cash_ledger"] == []

        read_time = datetime.now(UTC) + timedelta(minutes=1)
        portfolio = client.get("/api/v1/portfolio", params={"decision_time": read_time.isoformat()})
        assert portfolio.status_code == 200
        assert portfolio.json() == {
            "status": "SUCCESS",
            "decision_time": read_time.isoformat().replace("+00:00", "Z"),
            "trading": "paper_only",
            "configuration": {
                "id": "10000000-0000-0000-0000-000000000001",
                "name": "default-paper",
                "initial_cash": "100000",
                "currency": "USD",
            },
            "initialized_at": effective_at.isoformat().replace("+00:00", "Z"),
            "cash": {"balance": "100000", "currency": "USD"},
            "latest_nav": None,
            "positions": [],
            "risk_decisions": [],
            "orders": [],
            "fills": [],
            "cash_ledger": sorted(
                [
                    {
                        "id": str(row["id"]),
                        "transaction_id": str(row["transaction_id"]),
                        "source_id": str(row["source_id"]),
                        "account": row["account"],
                        "debit": str(row["debit"]),
                        "credit": str(row["credit"]),
                        "currency": row["currency"],
                        "occurred_at": row["occurred_at"].isoformat().replace("+00:00", "Z"),
                        "idempotency_key": row["idempotency_key"],
                        "reversal_of_id": (
                            str(row["reversal_of_id"]) if row["reversal_of_id"] else None
                        ),
                        "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
                    }
                    for row in rows
                ],
                key=lambda row: row["account"],
            ),
            "performance_history": [],
        }

        assert len(rows) == 2
        assert {row["account"] for row in rows} == {
            "ASSET:CASH",
            "EQUITY:OPENING_BALANCE",
        }
        assert sum((row["debit"] for row in rows), Decimal("0")) == Decimal("100000")
        assert sum((row["credit"] for row in rows), Decimal("0")) == Decimal("100000")
        assert all(row["currency"] == "USD" for row in rows)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_paper_portfolio_initialization_requires_an_idempotency_key(
    isolated_database_url: str,
) -> None:
    client, engine = _client(isolated_database_url)
    try:
        response = client.post(
            "/api/v1/portfolio/initialize",
            json={"effective_at": datetime(2026, 9, 1, 1, tzinfo=UTC).isoformat()},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        with engine.connect() as connection:
            count = connection.execute(select(func.count()).select_from(cash_ledger)).scalar_one()
            assert count == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_portfolio_initialization_rejects_key_reuse_with_a_different_payload(
    isolated_database_url: str,
) -> None:
    client, engine = _client(isolated_database_url)
    first_effective_at = datetime(2026, 9, 1, 1, tzinfo=UTC)
    try:
        first = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper"},
            json={"effective_at": first_effective_at.isoformat()},
        )
        conflict = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper"},
            json={"effective_at": (first_effective_at + timedelta(seconds=1)).isoformat()},
        )

        assert first.status_code == 200
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count()).select_from(portfolio_initialization_request)
                ).scalar_one()
                == 1
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_initialized_portfolio_rejects_a_new_initialization_operation(
    isolated_database_url: str,
) -> None:
    client, engine = _client(isolated_database_url)
    effective_at = datetime(2026, 9, 1, 1, tzinfo=UTC)
    try:
        first = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper-a"},
            json={"effective_at": effective_at.isoformat()},
        )
        second_operation = client.post(
            "/api/v1/portfolio/initialize",
            headers={"Idempotency-Key": "initialize-default-paper-b"},
            json={"effective_at": effective_at.isoformat()},
        )

        assert first.status_code == 200
        assert second_operation.status_code == 409
        assert second_operation.json()["error"]["code"] == "PORTFOLIO_ALREADY_INITIALIZED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_uninitialized_portfolio_is_empty_not_failure(isolated_database_url: str) -> None:
    client, engine = _client(isolated_database_url)
    decision_time = datetime.now(UTC) + timedelta(minutes=1)
    try:
        response = client.get(
            "/api/v1/portfolio", params={"decision_time": decision_time.isoformat()}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "EMPTY"
        assert response.json()["configuration"]["initial_cash"] == "100000"
        assert response.json()["initialized_at"] is None
        assert response.json()["cash"] is None
        assert response.json()["cash_ledger"] == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
