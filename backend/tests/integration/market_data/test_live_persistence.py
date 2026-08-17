from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
from stock_platform.infrastructure.providers.base import FeedType, ProviderRecord
from stock_platform.infrastructure.providers.persistence import PostgresProviderRecordStore


def test_live_provider_record_store_persists_complete_lineage_and_version(engine: Engine) -> None:
    record = ProviderRecord(
        symbol=Symbol("NVDA"),
        feed_type=FeedType.PRICE_BARS,
        provider="FMP",
        event_time=datetime(2026, 8, 16, 11, 55, tzinfo=UTC),
        available_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        content_hash="f" * 64,
        raw_object_key="live/FMP/price_bars/test-persistence.json",
        payload={"close": "123.45"},
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        PostgresProviderRecordStore(connection).persist(record, "fmp-price_bars-v1")

        row = connection.execute(
            select(
                raw_data_object.c.provider,
                raw_data_object.c.feed_type,
                normalized_record.c.normalization_version,
                normalized_record.c.payload,
            )
            .select_from(
                normalized_record.join(
                    raw_data_object,
                    normalized_record.c.raw_data_object_id == raw_data_object.c.id,
                )
            )
            .where(raw_data_object.c.raw_object_key == record.raw_object_key)
        ).one()
        transaction.rollback()

    assert row.provider == "FMP"
    assert row.feed_type == "price_bars"
    assert row.normalization_version == "fmp-price_bars-v1"
    assert row.payload == {"symbol": "NVDA", "close": "123.45"}
