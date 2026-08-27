"""Provider-free replay of immutable raw objects through a newer normalizer."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import normalization_dispatch, raw_data_object


class ReadableRawArchive(Protocol):
    def get(self, object_key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ReplayNormalized:
    record_type: str
    record_key: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.record_type or not self.record_key:
            raise ValueError("replay record type and key are required")
        object.__setattr__(self, "payload", dict(self.payload))


ReplayNormalizer = Callable[[bytes], ReplayNormalized]


class RawReplayService:
    def __init__(self, *, engine: Engine, raw_store: ReadableRawArchive) -> None:
        self._engine = engine
        self._raw_store = raw_store

    def replay(
        self,
        *,
        raw_id: UUID,
        normalization_version: str,
        normalize: ReplayNormalizer,
        now: datetime,
    ) -> UUID:
        replayed_at = require_aware(now).astimezone(UTC)
        if not normalization_version:
            raise ValueError("normalization version is required")
        with self._engine.connect() as connection:
            raw = (
                connection.execute(select(raw_data_object).where(raw_data_object.c.id == raw_id))
                .mappings()
                .one()
            )
        content = self._raw_store.get(str(raw["raw_object_key"]))
        if hashlib.sha256(content).hexdigest() != raw["content_hash"]:
            raise ValueError("immutable raw object hash mismatch")
        normalized = normalize(content)
        values = {
            "raw_data_object_id": raw_id,
            "normalization_version": normalization_version,
            "record_type": normalized.record_type,
            "record_key": normalized.record_key,
            "normalized_payload": dict(normalized.payload),
            "state": "PENDING",
            "next_attempt_at": replayed_at,
            "updated_at": replayed_at,
            "created_at": replayed_at,
        }
        with self._engine.begin() as connection:
            dispatch_id = connection.execute(
                insert(normalization_dispatch)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_normalization_dispatch_version")
                .returning(normalization_dispatch.c.id)
            ).scalar_one_or_none()
            if dispatch_id is not None:
                return cast(UUID, dispatch_id)
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
            for key in ("record_type", "record_key", "normalized_payload"):
                if existing[key] != values[key]:
                    raise ValueError("immutable replay dispatch conflict")
            return cast(UUID, existing["id"])
