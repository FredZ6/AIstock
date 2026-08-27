import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from stock_platform.application.ingestion.replay import RawReplayService, ReplayNormalized
from stock_platform.infrastructure.db.models.tables import normalization_dispatch, normalized_record

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


class ReadOnlyArchive:
    def __init__(self, key: str, content: bytes) -> None:
        self.key = key
        self.content = content
        self.get_count = 0

    def get(self, object_key: str) -> bytes:
        assert object_key == self.key
        self.get_count += 1
        return self.content


def _raw(engine: Engine, content: bytes) -> tuple[object, str]:
    raw_id = uuid4()
    digest = hashlib.sha256(content).hexdigest()
    key = f"fixture/replay/{digest}.json"
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO raw_data_object (
              id, provider, feed_type, event_time, available_at, ingested_at,
              content_hash, raw_object_key)
            VALUES (:id, 'FIXTURE', 'price_bars', :now, :now, :now, :hash, :key)
            """),
            {"id": raw_id, "now": NOW, "hash": digest, "key": key},
        )
    return raw_id, key


def test_replay_uses_immutable_raw_bytes_and_adds_a_new_normalizer_version(engine: Engine) -> None:
    content = f'{{"symbol":"NVDA","nonce":"{uuid4().hex}"}}'.encode()
    raw_id, key = _raw(engine, content)
    old_normalized_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO normalized_record (
              id, raw_data_object_id, record_type, record_key, normalization_version, payload)
            VALUES (:id, :raw, 'price_bars', 'NVDA', 'normalizer-v1', '{"close":"99.00"}')
            """),
            {"id": old_normalized_id, "raw": raw_id},
        )
    archive = ReadOnlyArchive(key, content)
    service = RawReplayService(engine=engine, raw_store=archive)

    first = service.replay(
        raw_id=raw_id,
        normalization_version="normalizer-v2",
        normalize=lambda body: ReplayNormalized("price_bars", "NVDA", {"close": "100.00"}),
        now=NOW,
    )
    second = service.replay(
        raw_id=raw_id,
        normalization_version="normalizer-v2",
        normalize=lambda body: ReplayNormalized("price_bars", "NVDA", {"close": "100.00"}),
        now=NOW,
    )

    assert first == second
    assert archive.get_count == 2
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(normalized_record)
                .where(normalized_record.c.raw_data_object_id == raw_id)
            ).scalar_one()
            == 1
        )
        dispatch = (
            connection.execute(
                select(normalization_dispatch).where(normalization_dispatch.c.id == first)
            )
            .mappings()
            .one()
        )
        assert dispatch["normalization_version"] == "normalizer-v2"
        assert dispatch["normalized_payload"] == {"close": "100.00"}


def test_replay_rejects_tampered_archive_before_dispatch(engine: Engine) -> None:
    raw_id, key = _raw(engine, f'{{"nonce":"{uuid4().hex}"}}'.encode())
    service = RawReplayService(engine=engine, raw_store=ReadOnlyArchive(key, b"tampered"))

    with pytest.raises(ValueError, match="hash"):
        service.replay(
            raw_id=raw_id,
            normalization_version="normalizer-v2",
            normalize=lambda body: ReplayNormalized("price_bars", "NVDA", {}),
            now=NOW,
        )

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(normalization_dispatch.c.id).where(
                    normalization_dispatch.c.raw_data_object_id == raw_id
                )
            ).scalar_one_or_none()
            is None
        )
