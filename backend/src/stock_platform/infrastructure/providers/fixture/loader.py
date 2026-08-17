"""Load, validate, serve, and seed the frozen M1 fixture catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, and_, select, update
from sqlalchemy.dialects.postgresql import insert

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
    RawObjectStore,
)


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return require_aware(parsed)


@dataclass(frozen=True, slots=True)
class FixtureManifest:
    dataset: str
    dataset_version: str
    license: str
    provenance: str
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FixtureEntry:
    dataset: str
    fixture_id: str
    symbol: Symbol
    feed_type: FeedType
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    scenarios: frozenset[str]
    status: ProviderStatus
    payload: dict[str, Any]

    @property
    def raw_payload(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "feed_type": self.feed_type.value,
            "payload": self.payload,
        }

    @property
    def content_hash(self) -> str:
        return payload_hash(self.raw_payload)

    @property
    def raw_object_key(self) -> str:
        return f"m1-v1/{self.dataset}/{self.fixture_id}.json"

    def provider_record(self) -> ProviderRecord:
        return ProviderRecord(
            symbol=self.symbol,
            feed_type=self.feed_type,
            provider="FIXTURE",
            event_time=self.event_time,
            available_at=self.available_at,
            ingested_at=self.ingested_at,
            content_hash=self.content_hash,
            raw_object_key=self.raw_object_key,
            payload=self.payload,
            is_delayed="delayed" in self.scenarios,
            quality_flags=tuple(sorted(self.scenarios - {"normal"})),
        )


@dataclass(frozen=True, slots=True)
class FixtureCatalog:
    root: Path
    manifests: dict[str, FixtureManifest]
    entries: tuple[FixtureEntry, ...]

    @classmethod
    def load_default(cls) -> FixtureCatalog:
        return cls.load(Path(__file__).resolve().parents[6] / "evals" / "fixtures")

    @classmethod
    def load(cls, root: Path) -> FixtureCatalog:
        manifests: dict[str, FixtureManifest] = {}
        entries: list[FixtureEntry] = []
        for manifest_path in sorted(root.glob("*/manifest.json")):
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = FixtureManifest(
                dataset=document["dataset"],
                dataset_version=document["dataset_version"],
                license=document["license"],
                provenance=document["provenance"],
                records=tuple(document["records"]),
            )
            if manifest.dataset != manifest_path.parent.name:
                raise ValueError(f"fixture dataset mismatch: {manifest_path}")
            if manifest.dataset_version != "m1-v1":
                raise ValueError(f"unsupported fixture version: {manifest.dataset_version}")
            manifests[manifest.dataset] = manifest
            for item in manifest.records:
                entry = FixtureEntry(
                    dataset=manifest.dataset,
                    fixture_id=item["id"],
                    symbol=Symbol(item["symbol"]),
                    feed_type=FeedType(item["feed_type"]),
                    event_time=parse_timestamp(item["event_time"]),
                    available_at=parse_timestamp(item["available_at"]),
                    ingested_at=parse_timestamp(item["ingested_at"]),
                    scenarios=frozenset(item["scenarios"]),
                    status=ProviderStatus(item.get("status", "ok")),
                    payload=item["payload"],
                )
                if not entry.event_time <= entry.available_at <= entry.ingested_at:
                    raise ValueError(f"invalid point-in-time fixture: {entry.fixture_id}")
                declared_hash = item.get("content_hash")
                if declared_hash is not None and declared_hash != entry.content_hash:
                    raise ValueError(f"fixture content hash mismatch: {entry.fixture_id}")
                entries.append(entry)
        if not manifests:
            raise ValueError(f"no fixture manifests found under {root}")
        return cls(root=root, manifests=manifests, entries=tuple(entries))

    @property
    def symbols(self) -> set[str]:
        return {str(entry.symbol) for entry in self.entries}

    @property
    def scenarios(self) -> set[str]:
        return {scenario for entry in self.entries for scenario in entry.scenarios}

    @property
    def content_hashes(self) -> tuple[str, ...]:
        return tuple(entry.content_hash for entry in self.entries)

    def provider(self) -> FixtureProvider:
        return FixtureProvider(self)

    def seed_object_store(self, store: RawObjectStore) -> int:
        count = 0
        for entry in self.entries:
            if entry.status is not ProviderStatus.OK:
                continue
            store.put(entry.raw_object_key, canonical_json(entry.raw_payload), "application/json")
            count += 1
        return count

    def seed_database(self, connection: Connection) -> int:
        count = 0
        for entry in self.entries:
            if entry.status is not ProviderStatus.OK:
                continue
            raw_values = {
                "provider": "FIXTURE",
                "feed_type": entry.feed_type.value,
                "event_time": entry.event_time,
                "available_at": entry.available_at,
                "ingested_at": entry.ingested_at,
                "content_hash": entry.content_hash,
                "raw_object_key": entry.raw_object_key,
            }
            raw_id = connection.execute(
                select(raw_data_object.c.id).where(
                    and_(
                        raw_data_object.c.provider == "FIXTURE",
                        raw_data_object.c.feed_type == entry.feed_type.value,
                        raw_data_object.c.raw_object_key == entry.raw_object_key,
                    )
                )
            ).scalar_one_or_none()
            if raw_id is not None:
                connection.execute(
                    update(raw_data_object)
                    .where(raw_data_object.c.id == raw_id)
                    .values(**raw_values)
                )
            else:
                raw_id = connection.execute(
                    insert(raw_data_object)
                    .values(**raw_values)
                    .on_conflict_do_nothing(constraint="uq_raw_data_provider_content")
                    .returning(raw_data_object.c.id)
                ).scalar_one_or_none()
                if raw_id is None:
                    raw_id = connection.execute(
                        select(raw_data_object.c.id).where(
                            and_(
                                raw_data_object.c.provider == "FIXTURE",
                                raw_data_object.c.feed_type == entry.feed_type.value,
                                raw_data_object.c.content_hash == entry.content_hash,
                            )
                        )
                    ).scalar_one()
            exists = connection.execute(
                select(normalized_record.c.id).where(
                    and_(
                        normalized_record.c.raw_data_object_id == raw_id,
                        normalized_record.c.record_type == entry.feed_type.value,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    insert(normalized_record).values(
                        raw_data_object_id=raw_id,
                        record_type=entry.feed_type.value,
                        payload={"symbol": str(entry.symbol), **entry.payload},
                    )
                )
                count += 1
            else:
                connection.execute(
                    update(normalized_record)
                    .where(normalized_record.c.id == exists)
                    .values(payload={"symbol": str(entry.symbol), **entry.payload})
                )
        return count


class FixtureProvider:
    name = "FIXTURE"

    def __init__(self, catalog: FixtureCatalog) -> None:
        self._catalog = catalog

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        query_as_of = require_aware(as_of)
        normalized_symbol = Symbol(symbol)
        matching = [
            entry
            for entry in self._catalog.entries
            if entry.feed_type is feed_type
            and entry.symbol == normalized_symbol
            and entry.available_at <= query_as_of
        ]
        unavailable = [entry for entry in matching if entry.status is ProviderStatus.UNAVAILABLE]
        visible = [
            entry.provider_record() for entry in matching if entry.status is ProviderStatus.OK
        ]
        visible.sort(key=lambda item: (item.available_at, item.event_time, item.content_hash))
        if visible:
            status = ProviderStatus.OK
            missingness = None
        elif unavailable:
            status = ProviderStatus.UNAVAILABLE
            missingness = "UNAVAILABLE"
        else:
            status = ProviderStatus.NOT_FOUND
            missingness = "MISSING"
        return ProviderResponse(
            status=status,
            provider=self.name,
            feed_type=feed_type,
            symbol=normalized_symbol,
            query_as_of=query_as_of,
            records=tuple(visible),
            missingness=missingness,
        )
