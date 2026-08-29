from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine
from stock_platform.api.dependencies import get_connection, get_settings
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    market_bar,
    normalized_record,
    raw_data_object,
)
from stock_platform.settings import Settings


@pytest.fixture
def market_client(isolated_database_url: str) -> Iterator[tuple[TestClient, Connection]]:
    from alembic import command
    from alembic.config import Config

    config = Config("backend/alembic.ini")
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine: Engine = create_engine(isolated_database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        app.dependency_overrides[get_connection] = lambda: connection
        app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
            environment="paper",
            database_url=isolated_database_url,
            alpaca_data_key="configured-key",
            alpaca_data_secret="configured-secret",
            alpaca_entitlement_coverage="IEX",
            alpaca_entitlement_version="test-iex-v1",
            _env_file=None,
        )
        try:
            yield TestClient(app), connection
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()
    engine.dispose()


def _bar(
    connection: Connection,
    *,
    event_time: datetime,
    available_at: datetime,
    close: str,
    suffix: str,
) -> None:
    content_hash = suffix * 64
    raw_id = connection.execute(
        raw_data_object.insert()
        .values(
            provider="ALPACA",
            feed_type="price_bars",
            event_time=event_time,
            available_at=available_at,
            ingested_at=available_at,
            content_hash=content_hash,
            raw_object_key=f"live/ALPACA/price_bars/{content_hash}.json",
        )
        .returning(raw_data_object.c.id)
    ).scalar_one()
    normalized_id = connection.execute(
        normalized_record.insert()
        .values(
            raw_data_object_id=raw_id,
            record_type="price_bars",
            record_key=f"NVDA:{event_time.isoformat()}",
            normalization_version="test-v1",
            payload={"symbol": "NVDA", "close": close},
        )
        .returning(normalized_record.c.id)
    ).scalar_one()
    connection.execute(
        market_bar.insert().values(
            event_time=event_time,
            symbol="NVDA",
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider="ALPACA",
            feed_type="price_bars",
            coverage="IEX",
            session="REGULAR",
            content_hash=content_hash,
            raw_object_key=f"live/ALPACA/price_bars/{content_hash}.json",
            available_at=available_at,
            ingested_at=available_at,
            open=Decimal(close) - Decimal("1"),
            high=Decimal(close) + Decimal("1"),
            low=Decimal(close) - Decimal("2"),
            close=Decimal(close),
            volume=Decimal("1000"),
            payload={"timeframe": "1Day"},
        )
    )
    connection.execute(
        data_quality_observation.insert().values(
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider="ALPACA",
            dataset="price_bars",
            dimension="COVERAGE",
            status="PASS",
            observed_at=available_at,
            coverage="IEX",
            conflict=False,
            policy_version="test-v1",
            details={"symbol": "NVDA"},
        )
    )


def test_quotes_and_bars_enforce_point_in_time_visibility(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    visible_at = datetime(2026, 8, 20, 20, tzinfo=UTC)
    future_available_at = datetime(2026, 8, 22, 20, tzinfo=UTC)
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, tzinfo=UTC),
        available_at=visible_at,
        close="180.50",
        suffix="a",
    )
    _bar(
        connection,
        event_time=datetime(2026, 8, 21, 19, tzinfo=UTC),
        available_at=future_available_at,
        close="999.99",
        suffix="b",
    )
    decision_time = datetime(2026, 8, 21, 21, tzinfo=UTC).isoformat()

    quotes = client.get(
        "/api/v1/market-data/quotes",
        params={"symbols": "NVDA", "decision_time": decision_time},
    )
    bars = client.get(
        "/api/v1/market-data/bars/NVDA",
        params={
            "start": datetime(2026, 8, 19, tzinfo=UTC).isoformat(),
            "end": decision_time,
            "decision_time": decision_time,
        },
    )

    assert quotes.status_code == bars.status_code == 200
    assert quotes.json()["status"] == bars.json()["status"] == "SUCCESS"
    assert [item["close"] for item in quotes.json()["items"]] == ["180.50"]
    assert [item["close"] for item in bars.json()["items"]] == ["180.50"]
    assert all(item["available_at"] <= decision_time for item in bars.json()["items"])


def test_market_data_reads_reject_naive_times(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, _ = market_client

    response = client.get(
        "/api/v1/market-data/quotes",
        params={"symbols": "NVDA", "decision_time": "2026-08-21T21:00:00"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_quality_and_provider_health_report_real_runtime_evidence(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    observed_at = datetime(2026, 8, 20, 20, tzinfo=UTC)
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, tzinfo=UTC),
        available_at=observed_at,
        close="180.50",
        suffix="c",
    )

    quality = client.get(
        "/api/v1/data-quality",
        params={
            "provider": "ALPACA",
            "dataset": "price_bars",
            "decision_time": datetime(2026, 8, 21, tzinfo=UTC).isoformat(),
        },
    )
    health = client.get("/api/v1/providers/health")

    assert quality.status_code == health.status_code == 200
    assert quality.json()["status"] == "SUCCESS"
    assert quality.json()["items"][0]["coverage"] == "IEX"
    assert health.json()["mode"] == "paper"
    assert health.json()["providers"]["alpaca"]["mode"] == "read_only"
    assert health.json()["providers"]["alpaca"]["status"] == "SUCCESS"
