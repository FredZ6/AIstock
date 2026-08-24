from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.workers.alpaca_stream_supervisor import (
    AlpacaStreamArchiveUnavailable,
    AlpacaStreamPublishUnavailable,
    AlpacaStreamSupervisor,
    alpaca_stream_recovery_object,
    replay_archived_stream_batches,
)


class FakeConnection:
    def __init__(self, messages: tuple[str, ...]) -> None:
        self.messages = iter(messages)
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self) -> FakeConnection:
        return self

    async def __anext__(self) -> str:
        try:
            return next(self.messages)
        except StopIteration as error:
            raise StopAsyncIteration from error


def test_stream_supervisor_publishes_batches_and_reconnect_recovery() -> None:
    published: list[tuple[str, list[str]]] = []
    archived: list[tuple[str, bytes]] = []
    data = '[{"T":"t","S":"NVDA","t":"2026-08-21T15:00:00Z","p":180.5}]'
    connection = FakeConnection(
        (
            '[{"T":"success","msg":"authenticated"}]',
            '[{"T":"subscription","trades":["NVDA"]}]',
            data,
        )
    )
    supervisor = AlpacaStreamSupervisor(
        data_key="test-key",
        data_secret="test-secret",
        coverage=MarketDataCoverage.IEX,
        symbols=("NVDA",),
        publish=lambda task, args: published.append((task, args)),
        archive=lambda key, raw: archived.append((key, raw)),
    )

    asyncio.run(supervisor.consume(connection))
    supervisor.publish_reconnect_recovery(reconnected_at=datetime(2026, 8, 24, 15, 1, tzinfo=UTC))

    assert '"action":"auth"' in connection.sent[0]
    assert '"updatedBars":["NVDA"]' in connection.sent[1]
    assert published[0] == (
        "stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event",
        [data, published[0][1][1], "IEX"],
    )
    assert archived[0][0].startswith("live/ALPACA/stream-recovery/iex/")
    assert archived[1] == (supervisor.raw_object_key(data.encode()), data.encode())
    assert published[1] == (
        "stock_platform.workers.schedules.schedule_alpaca_reconnect_ingestion",
        ["NVDA", "2026-08-21T15:00:00+00:00", "2026-08-24T15:01:00+00:00"],
    )


def test_stream_supervisor_archives_before_publish_and_does_not_advance_on_failure() -> None:
    order: list[str] = []
    data = '[ {"p":180.5,"t":"2026-08-21T15:00:00Z","S":"NVDA","T":"t"} ]'

    def fail_publish(_task: str, _args: list[str]) -> None:
        order.append("publish")
        raise OSError

    supervisor = AlpacaStreamSupervisor(
        data_key="test-key",
        data_secret="test-secret",
        coverage=MarketDataCoverage.SIP,
        symbols=("NVDA",),
        archive=lambda _key, _raw: order.append("archive"),
        publish=fail_publish,
    )

    try:
        asyncio.run(supervisor.consume(FakeConnection((data,))))
    except AlpacaStreamPublishUnavailable:
        pass

    assert order == ["archive", "archive", "publish"]
    assert supervisor.reconnect_watermarks == {}


def test_stream_supervisor_archives_and_publishes_before_schema_validation() -> None:
    order: list[str] = []
    malformed = '[{"T":"b"'
    supervisor = AlpacaStreamSupervisor(
        data_key="test-key",
        data_secret="test-secret",
        coverage=MarketDataCoverage.IEX,
        symbols=("NVDA",),
        archive=lambda _key, _raw: order.append("archive"),
        publish=lambda _task, _args: order.append("publish"),
    )

    try:
        asyncio.run(supervisor.consume(FakeConnection((malformed,))))
    except ValueError as error:
        assert "invalid JSON" in str(error)

    assert order == ["archive", "archive", "publish"]


def test_sidecar_survives_raw_archive_failure_and_is_replayable() -> None:
    archived: list[tuple[str, bytes]] = []
    published: list[tuple[str, list[str]]] = []
    data = '[{"T":"t","S":"NVDA","t":"2026-08-21T15:00:00Z","p":180.5}]'

    def fail_second_archive(key: str, body: bytes) -> None:
        archived.append((key, body))
        if len(archived) == 2:
            raise OSError("raw archive unavailable")

    supervisor = AlpacaStreamSupervisor(
        data_key="test-key",
        data_secret="test-secret",
        coverage=MarketDataCoverage.SIP,
        symbols=("NVDA",),
        archive=fail_second_archive,
        publish=lambda task, args: published.append((task, args)),
    )
    try:
        asyncio.run(supervisor.consume(FakeConnection((data,))))
    except AlpacaStreamArchiveUnavailable:
        pass

    class SurvivingArchive:
        def iter_keys(self, prefix: str = "") -> Iterator[str]:
            yield archived[0][0]

        def get(self, object_key: str) -> bytes:
            assert object_key == archived[0][0]
            return archived[0][1]

    result = replay_archived_stream_batches(
        SurvivingArchive(),
        publish=lambda task, args: published.append((task, args)),
        is_referenced=lambda _key: False,
    )

    assert archived[0][0].startswith("live/ALPACA/stream-recovery/sip/")
    assert published[0][1][0] == data
    assert result.replayed == 1


def test_archived_batch_is_republished_after_process_restart() -> None:
    raw = b'[{"T":"t","S":"NVDA","t":"2026-08-21T15:00:00Z","p":180.5}]'
    observed_at = datetime(2026, 8, 24, 16, tzinfo=UTC)
    recovery_key, recovery_envelope = alpaca_stream_recovery_object(
        raw,
        coverage=MarketDataCoverage.SIP,
        received_at=observed_at,
    )

    class Archive:
        def iter_keys(self, prefix: str = "") -> Iterator[str]:
            assert prefix == "live/ALPACA/stream-recovery/"
            yield recovery_key

        def get(self, object_key: str) -> bytes:
            assert object_key == recovery_key
            return recovery_envelope

    published: list[tuple[str, list[str]]] = []
    result = replay_archived_stream_batches(
        Archive(),
        publish=lambda task, args: published.append((task, args)),
        is_referenced=lambda _key: False,
    )
    assert result.replayed == 1
    assert result.next_cursor is None
    assert published == [
        (
            "stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event",
            [raw.decode(), observed_at.isoformat(), "SIP"],
        )
    ]


def test_archive_replay_skips_referenced_and_returns_bounded_cursor() -> None:
    observed_at = datetime(2026, 8, 24, 16, tzinfo=UTC)
    entries = sorted(
        [
            alpaca_stream_recovery_object(
                f'{{"T":"t","S":"NVDA","t":"2026-08-21T15:00:0{index}Z"}}'.encode(),
                coverage=MarketDataCoverage.IEX,
                received_at=observed_at,
            )
            for index in range(3)
        ]
    )

    class Archive:
        def iter_keys(self, prefix: str = "") -> Iterator[str]:
            yield from (key for key, _ in entries)

        def get(self, object_key: str) -> bytes:
            return dict(entries)[object_key]

    published: list[tuple[str, list[str]]] = []
    referenced_raw_key = AlpacaStreamSupervisor(
        data_key="key",
        data_secret="secret",
        coverage=MarketDataCoverage.IEX,
        symbols=("NVDA",),
        archive=lambda _key, _raw: None,
        publish=lambda _task, _args: None,
    ).raw_object_key(b'{"T":"t","S":"NVDA","t":"2026-08-21T15:00:00Z"}')
    first = replay_archived_stream_batches(
        Archive(),
        publish=lambda task, args: published.append((task, args)),
        is_referenced=lambda key: key == referenced_raw_key,
        limit=2,
    )
    second = replay_archived_stream_batches(
        Archive(),
        publish=lambda task, args: published.append((task, args)),
        is_referenced=lambda key: key == referenced_raw_key,
        after_key=first.next_cursor,
        limit=2,
    )

    assert first.replayed == 1
    assert first.next_cursor is not None
    assert second.replayed == 1
    assert second.next_cursor is None
    assert len(published) == 2
