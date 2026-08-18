from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
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
    engine: Engine,
) -> None:
    catalog = FixtureCatalog.load_default()
    fixture_raw_ids = select(raw_data_object.c.id).where(
        raw_data_object.c.raw_object_key.like("m1-v1/%")
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            delete(normalized_record).where(
                normalized_record.c.raw_data_object_id.in_(fixture_raw_ids)
            )
        )
        connection.execute(
            delete(raw_data_object).where(raw_data_object.c.raw_object_key.like("m1-v1/%"))
        )

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
        transaction.rollback()
