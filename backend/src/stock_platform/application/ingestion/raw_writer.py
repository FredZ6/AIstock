"""Raw-first commit path linking object storage to durable normalization dispatch."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from sqlalchemy import Connection, Engine, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.infrastructure.db.models.tables import (
    ingestion_raw_link,
    normalization_dispatch,
    raw_data_object,
)
from stock_platform.infrastructure.providers.base import ProviderRecord, RawObjectStore
from stock_platform.infrastructure.providers.persistence import (
    canonical_normalized_payload,
    persist_raw_object,
)


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
        if record.raw_object_key.rsplit("/", 1)[-1] != f"{record.content_hash}.json":
            raise ValueError("raw object key must be content-addressed by its SHA-256 hash")
        try:
            self._raw_store.put(record.raw_object_key, raw_content, "application/json")
        except Exception as error:
            raise RawObjectStoreUnavailable("raw object store write failed") from error
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
                "normalized_payload": canonical_normalized_payload(record),
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

    def write_artifact(
        self,
        *,
        record: ProviderRecord,
        raw_content: bytes,
        content_type: str,
        job_id: UUID | None = None,
        transaction_guard: Callable[[Connection], None] | None = None,
    ) -> UUID:
        """Persist immutable non-JSON source bytes without creating a normalization job."""
        if hashlib.sha256(raw_content).hexdigest() != record.content_hash:
            raise ValueError("raw content hash does not match ProviderRecord")
        filename = record.raw_object_key.rsplit("/", 1)[-1]
        if not filename.startswith(f"{record.content_hash}."):
            raise ValueError("raw artifact key must be content-addressed by its SHA-256 hash")
        try:
            self._raw_store.put(record.raw_object_key, raw_content, content_type)
        except Exception as error:
            raise RawObjectStoreUnavailable("raw object store write failed") from error
        with self._engine.begin() as connection:
            if transaction_guard is not None:
                transaction_guard(connection)
            raw_id = persist_raw_object(connection, record)
            if job_id is not None:
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
            return raw_id


class RawObjectStoreUnavailable(RuntimeError):
    pass


class RawObjectInventory(Protocol):
    def list_keys(self, prefix: str = "") -> tuple[str, ...]: ...


def report_orphaned_raw_objects(
    engine: Engine,
    inventory: RawObjectInventory,
    *,
    prefix: str = "",
) -> tuple[str, ...]:
    with engine.connect() as connection:
        referenced = set(connection.execute(select(raw_data_object.c.raw_object_key)).scalars())
    return tuple(sorted(set(inventory.list_keys(prefix)) - referenced))
