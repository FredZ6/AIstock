"""Raw-first commit path linking object storage to durable normalization dispatch."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.infrastructure.db.models.tables import (
    ingestion_raw_link,
    normalization_dispatch,
)
from stock_platform.infrastructure.providers.base import ProviderRecord, RawObjectStore
from stock_platform.infrastructure.providers.persistence import persist_raw_object


class RawWriter:
    def __init__(self, *, engine: Engine, raw_store: RawObjectStore) -> None:
        self._engine = engine
        self._raw_store = raw_store

    def write(
        self,
        *,
        job_id: UUID,
        record: ProviderRecord,
        raw_content: bytes,
        normalization_version: str,
    ) -> UUID:
        if hashlib.sha256(raw_content).hexdigest() != record.content_hash:
            raise ValueError("raw content hash does not match ProviderRecord")
        self._raw_store.put(record.raw_object_key, raw_content, "application/json")
        with self._engine.begin() as connection:
            raw_id = persist_raw_object(connection, record)
            connection.execute(
                insert(ingestion_raw_link)
                .values(job_id=job_id, raw_data_object_id=raw_id)
                .on_conflict_do_nothing(
                    index_elements=[
                        ingestion_raw_link.c.job_id,
                        ingestion_raw_link.c.raw_data_object_id,
                    ]
                )
            )
            dispatch_values = {
                "raw_data_object_id": raw_id,
                "normalization_version": normalization_version,
                "record_type": record.feed_type.value,
                "record_key": str(record.symbol),
                "normalized_payload": {"symbol": str(record.symbol), **record.payload},
                "state": "PENDING",
                "next_attempt_at": record.ingested_at,
                "updated_at": record.ingested_at,
                "created_at": record.ingested_at,
            }
            dispatch_id = connection.execute(
                insert(normalization_dispatch)
                .values(**dispatch_values)
                .on_conflict_do_nothing(constraint="uq_normalization_dispatch_version")
                .returning(normalization_dispatch.c.id)
            ).scalar_one_or_none()
            if dispatch_id is None:
                existing = (
                    connection.execute(
                        select(normalization_dispatch).where(
                            normalization_dispatch.c.raw_data_object_id == raw_id,
                            normalization_dispatch.c.normalization_version == normalization_version,
                        )
                    )
                    .mappings()
                    .one()
                )
                immutable_keys = ("record_type", "record_key", "normalized_payload")
                if any(existing[key] != dispatch_values[key] for key in immutable_keys):
                    raise ValueError("immutable normalization dispatch conflict")
            return raw_id
