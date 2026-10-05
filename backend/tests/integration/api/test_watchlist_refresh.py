from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, delete, insert, select, update
from stock_platform.api.dependencies import get_connection, get_settings
from stock_platform.api.main import app
from stock_platform.api.routes import rest
from stock_platform.infrastructure.db.models.tables import (
    ingestion_job,
    security,
    watchlist_item,
)
from stock_platform.settings import Settings


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    value = create_engine(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        )
    )
    try:
        yield value
    finally:
        value.dispose()


@pytest.fixture
def refresh_rows(engine: Engine) -> Iterator[None]:
    symbols = ("TSKA", "TSKB", "TSKC")
    security_ids = {symbol: uuid4() for symbol in symbols}
    with engine.begin() as connection:
        prior_monitoring = tuple(
            connection.execute(
                select(watchlist_item.c.security_id, watchlist_item.c.intraday_monitoring)
            ).mappings()
        )
        connection.execute(update(watchlist_item).values(intraday_monitoring=False))
        connection.execute(
            delete(ingestion_job).where(ingestion_job.c.policy_version == "operator-verified-test")
        )
        connection.execute(delete(watchlist_item).where(watchlist_item.c.symbol.in_(symbols)))
        connection.execute(delete(security).where(security.c.id.in_(security_ids.values())))
        for symbol, security_id in security_ids.items():
            connection.execute(insert(security).values(id=security_id, instrument_type="EQUITY"))
            connection.execute(
                insert(watchlist_item).values(
                    security_id=security_id,
                    symbol=symbol,
                    daily_research=True,
                    intraday_monitoring=symbol != "TSKC",
                )
            )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(ingestion_job).where(
                    ingestion_job.c.policy_version == "operator-verified-test"
                )
            )
            connection.execute(delete(watchlist_item).where(watchlist_item.c.symbol.in_(symbols)))
            connection.execute(delete(security).where(security.c.id.in_(security_ids.values())))
            for row in prior_monitoring:
                connection.execute(
                    update(watchlist_item)
                    .where(watchlist_item.c.security_id == row["security_id"])
                    .values(intraday_monitoring=row["intraday_monitoring"])
                )


def paper_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        environment="paper",
        alpaca_data_key="test-key",
        alpaca_data_secret="test-secret",
        alpaca_entitlement_coverage="IEX",
        alpaca_entitlement_version="operator-verified-test",
        admin_api_token=SecretStr("test-admin-token"),
        admin_actor_id="test-operator",
        _env_file=None,
    )


@pytest.fixture
def client(engine: Engine, refresh_rows: None) -> Iterator[TestClient]:
    def connection_override() -> Iterator[object]:
        with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_connection] = connection_override
    app.dependency_overrides[get_settings] = paper_settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def authorize() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-token"}


def refresh_jobs(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                ingestion_job.c.id,
                ingestion_job.c.state,
                ingestion_job.c.request_payload,
            ).where(
                ingestion_job.c.request_payload["request"]["symbol"].astext.in_(
                    ("TSKA", "TSKB", "TSKC")
                )
            )
        ).mappings()
        return [dict(row) for row in rows]


def test_authorized_refresh_queues_only_intraday_monitored_symbols(
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC)
    published: list[tuple[str, UUID, str]] = []
    monkeypatch.setattr(rest, "_watchlist_refresh_now", lambda: now)
    monkeypatch.setattr(
        rest,
        "_publish_watchlist_refresh_job",
        lambda task, job_id, queue: published.append((task, job_id, queue)),
    )

    response = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["symbol_count"] == 2
    assert payload["feed"] == "IEX"
    assert payload["timeframe"] == "1Min"
    assert datetime.fromisoformat(payload["requested_at"]) == now
    assert datetime.fromisoformat(payload["requested_at"]).utcoffset() == timedelta(0)
    assert len(payload["job_ids"]) == 2
    assert published == [
        (
            "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
            UUID(job_id),
            "ingestion-low",
        )
        for job_id in payload["job_ids"]
    ]
    jobs = refresh_jobs(engine)
    assert {job["request_payload"]["request"]["symbol"] for job in jobs} == {
        "TSKA",
        "TSKB",
    }


def test_refresh_requires_an_authenticated_human(client: TestClient) -> None:
    response = client.post("/api/v1/watchlist/refresh-market-data")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_fixture_mode_is_rejected_without_creating_jobs(
    client: TestClient,
    engine: Engine,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="fixture",
        admin_api_token=SecretStr("test-admin-token"),
        admin_actor_id="test-operator",
        _env_file=None,
    )

    response = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_MODE_REQUIRED"
    assert refresh_jobs(engine) == []


def test_missing_entitlement_is_explicitly_unavailable_without_creating_jobs(
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[UUID] = []
    monkeypatch.setattr(
        rest,
        "_publish_watchlist_refresh_job",
        lambda _task, job_id, _queue: published.append(job_id),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="paper",
        admin_api_token=SecretStr("test-admin-token"),
        admin_actor_id="test-operator",
        _env_file=None,
    )

    response = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["job_ids"] == []
    assert payload["symbol_count"] == 2
    assert payload["feed"] is None
    assert "credential" not in payload["message"].casefold()
    assert refresh_jobs(engine) == []
    assert published == []


def test_publisher_failure_is_sanitized_and_jobs_remain_queued(
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rest,
        "_watchlist_refresh_now",
        lambda: datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC),
    )

    def fail_publish(_task: str, _job_id: UUID, _queue: str) -> None:
        raise RuntimeError("redis://secret-host/internal-detail")

    monkeypatch.setattr(rest, "_publish_watchlist_refresh_job", fail_publish)

    response = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "REFRESH_DISPATCH_UNAVAILABLE"
    assert "redis" not in error["message"].casefold()
    jobs = refresh_jobs(engine)
    assert len(jobs) == 2
    assert {job["state"] for job in jobs} == {"QUEUED"}


def test_repeat_requests_with_same_cutoff_reuse_active_jobs(
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter(
        (
            datetime(2026, 10, 4, 12, 0, tzinfo=UTC),
            datetime(2026, 10, 4, 12, 17, tzinfo=UTC),
        )
    )
    published: list[UUID] = []
    monkeypatch.setattr(rest, "_watchlist_refresh_now", lambda: next(times))
    monkeypatch.setattr(
        rest,
        "_publish_watchlist_refresh_job",
        lambda _task, job_id, _queue: published.append(job_id),
    )

    first = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())
    second = client.post("/api/v1/watchlist/refresh-market-data", headers=authorize())

    assert first.status_code == 202
    assert second.status_code == 202
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["status"] == "queued"
    assert second_payload["status"] == "already_queued"
    assert second_payload["requested_at"] != first_payload["requested_at"]
    assert second_payload["data_cutoff"] == first_payload["data_cutoff"]
    assert second_payload["job_ids"] == first_payload["job_ids"]
    assert len(published) == 2
    assert len(refresh_jobs(engine)) == 2
