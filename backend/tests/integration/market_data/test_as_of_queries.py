from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.infrastructure.db.models.tables import raw_data_object
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog


@pytest.fixture
def seeded_repository(engine: Engine) -> Iterator[PostgresMarketDataRepository]:
    catalog = FixtureCatalog.load_default()
    with engine.connect() as connection:
        transaction = connection.begin()
        catalog.seed_database(connection)
        repository = PostgresMarketDataRepository(connection)
        yield repository
        transaction.rollback()


def test_late_news_is_not_visible_before_available_at(
    seeded_repository: PostgresMarketDataRepository,
) -> None:
    before = seeded_repository.as_of(
        symbol="NVDA",
        feed_type=FeedType.COMPANY_NEWS,
        decision_time=datetime(2026, 8, 15, 13, 0, tzinfo=UTC),
    )
    after = seeded_repository.as_of(
        symbol="NVDA",
        feed_type=FeedType.COMPANY_NEWS,
        decision_time=datetime(2026, 8, 15, 15, 0, tzinfo=UTC),
    )

    assert all(item.available_at <= before.query_as_of for item in before.records)
    assert len(after.records) == len(before.records) + 1
    assert after.records[-1].payload["headline"] == "NVDA late fixture update"


def test_repository_preserves_raw_lineage_and_stable_hash(
    seeded_repository: PostgresMarketDataRepository,
) -> None:
    result = seeded_repository.as_of(
        symbol="AAPL",
        feed_type=FeedType.PRICE_BARS,
        decision_time=datetime(2026, 8, 16, tzinfo=UTC),
    )

    assert result.records
    record = result.records[0]
    assert record.provider == "FIXTURE"
    assert record.raw_object_key.startswith("m1-v1/")
    assert len(record.content_hash) == 64


def test_repository_rejects_naive_decision_time(
    seeded_repository: PostgresMarketDataRepository,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        seeded_repository.as_of(
            symbol="AAPL",
            feed_type=FeedType.PRICE_BARS,
            decision_time=datetime(2026, 8, 16),
        )


def test_seed_is_collision_free_and_idempotent_from_empty_fixture_partition(
    isolated_database_url: str,
) -> None:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    catalog = FixtureCatalog.load_default()
    with engine.begin() as connection:
        assert catalog.seed_database(connection) == 31
        assert catalog.seed_database(connection) == 0
        assert (
            connection.execute(
                select(func.count())
                .select_from(raw_data_object)
                .where(raw_data_object.c.raw_object_key.like("m1-v1/%"))
            ).scalar_one()
            == 31
        )
    engine.dispose()


def test_future_event_is_hidden_even_if_available_at_is_before_decision(
    isolated_database_url: str,
) -> None:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    decision_time = datetime(2026, 8, 23, 14, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE raw_data_object DROP CONSTRAINT ck_raw_data_times"))
        raw_id = connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    'LEGACY', 'price_bars', :event_time, :available_at, :ingested_at,
                    repeat('c', 64), 'legacy/future-event.json'
                ) RETURNING id
                """
            ),
            {
                "event_time": decision_time.replace(hour=15),
                "available_at": decision_time.replace(hour=13),
                "ingested_at": decision_time,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO normalized_record (
                    raw_data_object_id, record_type, record_key,
                    normalization_version, payload
                ) VALUES (
                    :raw_id, 'price_bars', 'NVDA', 'legacy-v1',
                    '{"symbol":"NVDA","close":"999.99"}'::jsonb
                )
                """
            ),
            {"raw_id": raw_id},
        )
        result = PostgresMarketDataRepository(connection).as_of(
            symbol="NVDA",
            feed_type=FeedType.PRICE_BARS,
            decision_time=decision_time,
        )

    assert result.records == ()
    assert result.status.value == "not_found"
    engine.dispose()
