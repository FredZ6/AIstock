"""Transactional PostgreSQL persistence for normalized provider records."""

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert

from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
from stock_platform.infrastructure.providers.base import ProviderRecord


class PostgresProviderRecordStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def persist(self, record: ProviderRecord, normalization_version: str) -> None:
        raw_insert = insert(raw_data_object).values(
            provider=record.provider,
            feed_type=record.feed_type.value,
            event_time=record.event_time,
            available_at=record.available_at,
            ingested_at=record.ingested_at,
            content_hash=record.content_hash,
            raw_object_key=record.raw_object_key,
        )
        raw_id = self._connection.execute(
            raw_insert.on_conflict_do_update(
                constraint="uq_raw_data_provider_content",
                set_={
                    "event_time": raw_insert.excluded.event_time,
                    "available_at": raw_insert.excluded.available_at,
                    "ingested_at": raw_insert.excluded.ingested_at,
                    "raw_object_key": raw_insert.excluded.raw_object_key,
                },
            ).returning(raw_data_object.c.id)
        ).scalar_one()

        normalized_insert = insert(normalized_record).values(
            raw_data_object_id=raw_id,
            record_type=record.feed_type.value,
            normalization_version=normalization_version,
            payload={"symbol": str(record.symbol), **record.payload},
        )
        self._connection.execute(
            normalized_insert.on_conflict_do_update(
                constraint="uq_normalized_record_version",
                set_={"payload": normalized_insert.excluded.payload},
            )
        )
