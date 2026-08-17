from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.engine import Engine
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
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
