from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from stock_platform.api.dependencies import get_connection, get_settings
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    ingestion_job,
    investment_thesis,
    market_bar,
    normalized_record,
    raw_data_object,
    research_opinion,
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
    symbol: str = "NVDA",
    provider: str = "ALPACA",
    feed_type: str = "price_bars",
    timeframe: str = "1Day",
    conflict: bool = False,
) -> None:
    content_hash = (suffix * 64)[:64]
    raw_id = connection.execute(
        raw_data_object.insert()
        .values(
            provider=provider,
            feed_type=feed_type,
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
            record_type=feed_type,
            record_key=f"{symbol}:{event_time.isoformat()}",
            normalization_version="test-v1",
            payload={"symbol": symbol, "close": close, "timeframe": timeframe},
        )
        .returning(normalized_record.c.id)
    ).scalar_one()
    connection.execute(
        market_bar.insert().values(
            event_time=event_time,
            symbol=symbol,
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider=provider,
            feed_type=feed_type,
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
            conflict=conflict,
            payload={"timeframe": timeframe},
        )
    )
    connection.execute(
        data_quality_observation.insert().values(
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider=provider,
            dataset=feed_type,
            dimension="COVERAGE",
            status="PASS",
            observed_at=available_at,
            coverage="IEX",
            conflict=False,
            policy_version="test-v1",
            details={"symbol": symbol, "timeframe": timeframe},
        )
    )


def _quality_observation(
    connection: Connection,
    *,
    observed_at: datetime,
    available_at: datetime,
    status: str,
    suffix: str,
    dataset: str = "price_bars",
    dimension: str = "COVERAGE",
) -> None:
    content_hash = (suffix * 64)[:64]
    raw_id = connection.execute(
        raw_data_object.insert()
        .values(
            provider="ALPACA",
            feed_type=dataset,
            event_time=observed_at,
            available_at=available_at,
            ingested_at=available_at,
            content_hash=content_hash,
            raw_object_key=f"live/ALPACA/{dataset}/{content_hash}.json",
        )
        .returning(raw_data_object.c.id)
    ).scalar_one()
    normalized_id = connection.execute(
        normalized_record.insert()
        .values(
            raw_data_object_id=raw_id,
            record_type=dataset,
            record_key=f"quality:{observed_at.isoformat()}:{suffix}",
            normalization_version="test-v1",
            payload={},
        )
        .returning(normalized_record.c.id)
    ).scalar_one()
    connection.execute(
        data_quality_observation.insert().values(
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider="ALPACA",
            dataset=dataset,
            dimension=dimension,
            status=status,
            observed_at=observed_at,
            coverage="IEX",
            conflict=status == "FAIL",
            policy_version="test-v1",
            details={},
        )
    )


def _ingestion_job(
    connection: Connection,
    *,
    state: str,
    created_at: datetime,
    dataset: str = "price_bars",
    coverage: str = "IEX",
) -> None:
    terminal = state in {"SUCCEEDED", "COMPLETED_WITH_GAPS", "FAILED", "DEAD_LETTER", "CANCELLED"}
    connection.execute(
        ingestion_job.insert().values(
            request_hash=f"health-{state}-{created_at.isoformat()}",
            request_payload={"request": {"coverage": coverage}},
            provider="ALPACA",
            dataset=dataset,
            window_start=created_at,
            window_end=created_at,
            purpose="RESEARCH",
            state=state,
            max_attempts=3,
            policy_version="test-v1",
            completed_at=created_at if terminal else None,
            created_at=created_at,
            updated_at=created_at,
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
            "timeframe": "1Day",
        },
    )

    assert quotes.status_code == bars.status_code == 200
    assert quotes.json()["status"] == bars.json()["status"] == "SUCCESS"
    assert [item["close"] for item in quotes.json()["items"]] == ["180.50"]
    assert [item["close"] for item in bars.json()["items"]] == ["180.50"]
    assert all(item["available_at"] <= decision_time for item in bars.json()["items"])


def test_quotes_batch_source_and_timeframe_with_partial_degradation(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    visible_at = datetime(2026, 8, 20, 20, tzinfo=UTC)
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, tzinfo=UTC),
        available_at=visible_at,
        close="180.50",
        suffix="a",
    )
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 20, 20, 30, tzinfo=UTC),
        close="999.99",
        suffix="f",
        provider="FIXTURE",
    )
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, 45, tzinfo=UTC),
        available_at=datetime(2026, 8, 20, 20, 45, tzinfo=UTC),
        close="888.88",
        suffix="m",
        feed_type="minute_bars_stream",
        timeframe="1Min",
    )
    market_queries: list[str] = []

    def capture_market_query(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FROM market_bar" in statement:
            market_queries.append(statement)

    event.listen(connection, "before_cursor_execute", capture_market_query)
    try:
        response = client.get(
            "/api/v1/market-data/quotes",
            params={
                "symbols": "NVDA,MSFT",
                "decision_time": datetime(2026, 8, 21, tzinfo=UTC).isoformat(),
            },
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture_market_query)

    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"
    assert response.json()["missing_symbols"] == ["MSFT"]
    assert [
        (item["symbol"], item["close"], item["timeframe"]) for item in response.json()["items"]
    ] == [("NVDA", "180.50", "1Day")]
    assert len(market_queries) == 1


def test_historical_bars_isolates_timeframe_and_propagates_conflict(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    visible_at = datetime(2026, 8, 20, 20, tzinfo=UTC)
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, tzinfo=UTC),
        available_at=visible_at,
        close="180.50",
        suffix="d",
        conflict=True,
    )
    _bar(
        connection,
        event_time=datetime(2026, 8, 20, 19, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 20, 20, 1, tzinfo=UTC),
        close="181.00",
        suffix="e",
        feed_type="minute_bars_stream",
        timeframe="1Min",
    )

    response = client.get(
        "/api/v1/market-data/bars/NVDA",
        params={
            "start": datetime(2026, 8, 19, tzinfo=UTC).isoformat(),
            "end": datetime(2026, 8, 21, tzinfo=UTC).isoformat(),
            "decision_time": datetime(2026, 8, 21, tzinfo=UTC).isoformat(),
            "timeframe": "1Day",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"
    assert [
        (item["close"], item["timeframe"], item["conflict"]) for item in response.json()["items"]
    ] == [("180.50", "1Day", True)]


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
    fresh_health_at = datetime.now(UTC)
    _quality_observation(
        connection,
        observed_at=fresh_health_at,
        available_at=fresh_health_at,
        status="PASS",
        suffix="h",
    )
    health = client.get("/api/v1/providers/health")

    assert quality.status_code == health.status_code == 200
    assert quality.json()["status"] == "SUCCESS"
    assert quality.json()["items"][0]["coverage"] == "IEX"
    assert health.json()["mode"] == "paper"
    assert health.json()["providers"]["alpaca"]["mode"] == "read_only"
    assert health.json()["providers"]["alpaca"]["status"] == "SUCCESS"


def test_research_read_enforces_decision_time(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    cutoff = datetime(2026, 8, 21, 20, tzinfo=UTC)
    past_id = uuid4()
    future_id = uuid4()
    connection.execute(
        investment_thesis.insert(),
        [
            {
                "id": past_id,
                "symbol": "NVDA",
                "as_of": datetime(2026, 8, 20, 20, tzinfo=UTC),
                "direction": "BULLISH",
                "summary": "visible",
                "horizon": "MEDIUM",
                "confidence": Decimal("0.7"),
                "created_at": datetime(2026, 8, 20, 20, 1, tzinfo=UTC),
            },
            {
                "id": future_id,
                "symbol": "NVDA",
                "as_of": datetime(2026, 8, 22, 20, tzinfo=UTC),
                "direction": "BEARISH",
                "summary": "future",
                "horizon": "MEDIUM",
                "confidence": Decimal("0.8"),
                "created_at": datetime(2026, 8, 22, 20, 1, tzinfo=UTC),
            },
        ],
    )
    connection.execute(
        research_opinion.insert().values(
            thesis_id=past_id,
            value="BULLISH",
            created_at=datetime(2026, 8, 22, 20, tzinfo=UTC),
        )
    )

    response = client.get(
        "/api/v1/stocks/NVDA/research",
        params={"decision_time": cutoff.isoformat()},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(past_id)]
    assert response.json()[0]["opinion"] is None


def test_portfolio_nav_has_availability_and_enforces_decision_time(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    columns = {column["name"] for column in inspect(connection).get_columns("portfolio_nav")}
    assert "available_at" in columns
    portfolio_id = uuid4()
    cutoff = datetime(2026, 8, 21, 20, tzinfo=UTC)
    connection.execute(
        text(
            "INSERT INTO portfolio_nav (event_time, available_at, portfolio_id, nav) "
            "VALUES (:past_event, :past_available, :portfolio_id, :past_nav), "
            "(:future_event, :future_available, :portfolio_id, :future_nav)"
        ),
        {
            "past_event": datetime(2026, 8, 20, 20, tzinfo=UTC),
            "past_available": datetime(2026, 8, 20, 20, 1, tzinfo=UTC),
            "future_event": datetime(2026, 8, 21, 19, tzinfo=UTC),
            "future_available": datetime(2026, 8, 22, 20, tzinfo=UTC),
            "portfolio_id": portfolio_id,
            "past_nav": Decimal("100000.00"),
            "future_nav": Decimal("999999.00"),
        },
    )

    response = client.get(
        "/api/v1/portfolio",
        params={"decision_time": cutoff.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["latest_nav"]["nav"] == "100000.00"
    assert datetime.fromisoformat(response.json()["latest_nav"]["available_at"]) == datetime(
        2026, 8, 20, 20, 1, tzinfo=UTC
    )


def test_data_quality_uses_latest_dimension_state_and_raw_availability(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    cutoff = datetime(2026, 8, 21, 20, tzinfo=UTC)
    _quality_observation(
        connection,
        observed_at=datetime(2026, 8, 20, 18, tzinfo=UTC),
        available_at=datetime(2026, 8, 20, 18, 1, tzinfo=UTC),
        status="FAIL",
        suffix="q",
    )
    _quality_observation(
        connection,
        observed_at=datetime(2026, 8, 21, 18, tzinfo=UTC),
        available_at=datetime(2026, 8, 21, 18, 1, tzinfo=UTC),
        status="PASS",
        suffix="r",
    )
    _quality_observation(
        connection,
        observed_at=datetime(2026, 8, 21, 19, tzinfo=UTC),
        available_at=datetime(2026, 8, 22, 19, tzinfo=UTC),
        status="FAIL",
        suffix="s",
    )

    response = client.get(
        "/api/v1/data-quality",
        params={
            "provider": "ALPACA",
            "dataset": "price_bars",
            "decision_time": cutoff.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert [item["status"] for item in response.json()["items"]] == ["PASS", "FAIL"]


def test_provider_health_does_not_report_success_while_latest_job_is_pending(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    observed_at = datetime.now(UTC)
    _quality_observation(
        connection,
        observed_at=observed_at,
        available_at=observed_at,
        status="PASS",
        suffix="t",
    )
    _ingestion_job(
        connection,
        state="QUEUED",
        created_at=observed_at,
    )

    response = client.get("/api/v1/providers/health")

    assert response.status_code == 200
    assert response.json()["providers"]["alpaca"]["status"] == "DEGRADED"


def test_data_quality_status_is_independent_of_history_page_limit(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    cutoff = datetime(2026, 8, 21, 20, tzinfo=UTC)
    _quality_observation(
        connection,
        observed_at=datetime(2026, 8, 21, 17, tzinfo=UTC),
        available_at=datetime(2026, 8, 21, 17, tzinfo=UTC),
        status="FAIL",
        suffix="u",
        dimension="CONFLICT",
    )
    for offset, suffix in enumerate(("v", "w", "x")):
        observed_at = datetime(2026, 8, 21, 18 + offset, tzinfo=UTC)
        _quality_observation(
            connection,
            observed_at=observed_at,
            available_at=observed_at,
            status="PASS",
            suffix=suffix,
        )

    response = client.get(
        "/api/v1/data-quality",
        params={
            "provider": "ALPACA",
            "dataset": "price_bars",
            "decision_time": cutoff.isoformat(),
            "limit": 2,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["status"] == "FAILURE"


def test_provider_health_uses_fresh_signals_from_the_same_dataset(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    now = datetime.now(UTC)
    _quality_observation(
        connection,
        observed_at=now,
        available_at=now,
        status="PASS",
        suffix="y",
    )
    _ingestion_job(connection, state="QUEUED", created_at=now, dataset="price_bars")
    _ingestion_job(
        connection,
        state="SUCCEEDED",
        created_at=now + timedelta(seconds=1),
        dataset="company_news",
    )

    response = client.get("/api/v1/providers/health")

    assert response.status_code == 200
    assert response.json()["providers"]["alpaca"]["latest_job_state"] == "QUEUED"
    assert response.json()["providers"]["alpaca"]["status"] == "DEGRADED"


def test_provider_health_rejects_a_stale_pass_without_a_current_job(
    market_client: tuple[TestClient, Connection],
) -> None:
    client, connection = market_client
    stale = datetime.now(UTC) - timedelta(hours=1)
    _quality_observation(
        connection,
        observed_at=stale,
        available_at=stale,
        status="PASS",
        suffix="z",
    )

    response = client.get("/api/v1/providers/health")

    assert response.status_code == 200
    assert response.json()["providers"]["alpaca"]["status"] == "FAILURE"
