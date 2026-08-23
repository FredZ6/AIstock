"""Immutable PostgreSQL persistence for provider lineage."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import Connection, and_, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
from stock_platform.infrastructure.providers.base import ProviderRecord


def persist_raw_object(connection: Connection, record: ProviderRecord) -> UUID:
    values = {
        "provider": record.provider,
        "feed_type": record.feed_type.value,
        "event_time": record.event_time,
        "available_at": record.available_at,
        "ingested_at": record.ingested_at,
        "content_hash": record.content_hash,
        "raw_object_key": record.raw_object_key,
    }
    inserted = connection.execute(
        insert(raw_data_object)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_raw_data_provider_content")
        .returning(raw_data_object.c.id)
    ).scalar_one_or_none()
    if inserted is not None:
        return cast(UUID, inserted)
    existing = (
        connection.execute(
            select(raw_data_object).where(
                and_(
                    raw_data_object.c.provider == record.provider,
                    raw_data_object.c.feed_type == record.feed_type.value,
                    raw_data_object.c.content_hash == record.content_hash,
                )
            )
        )
        .mappings()
        .one()
    )
    if any(existing[key] != value for key, value in values.items()):
        raise ValueError("immutable raw object conflict")
    return cast(UUID, existing["id"])


def persist_normalized_record(
    connection: Connection,
    *,
    raw_id: UUID,
    record: ProviderRecord,
    normalization_version: str,
) -> UUID:
    record_key = str(record.symbol)
    payload = {"symbol": record_key, **record.payload}
    inserted = connection.execute(
        insert(normalized_record)
        .values(
            raw_data_object_id=raw_id,
            record_type=record.feed_type.value,
            record_key=record_key,
            normalization_version=normalization_version,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_normalized_record_version")
        .returning(normalized_record.c.id)
    ).scalar_one_or_none()
    if inserted is not None:
        return cast(UUID, inserted)
    existing = (
        connection.execute(
            select(normalized_record).where(
                normalized_record.c.raw_data_object_id == raw_id,
                normalized_record.c.record_type == record.feed_type.value,
                normalized_record.c.normalization_version == normalization_version,
                normalized_record.c.record_key == record_key,
            )
        )
        .mappings()
        .one()
    )
    if existing["payload"] != payload:
        raise ValueError("immutable normalized record conflict")
    return cast(UUID, existing["id"])


class PostgresProviderRecordStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def persist(self, record: ProviderRecord, normalization_version: str) -> None:
        raw_id = persist_raw_object(self._connection, record)
        persist_normalized_record(
            self._connection,
            raw_id=raw_id,
            record=record,
            normalization_version=normalization_version,
        )
