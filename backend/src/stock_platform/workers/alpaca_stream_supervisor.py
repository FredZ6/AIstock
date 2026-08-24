"""Operational Alpaca WebSocket producer feeding durable Celery persistence tasks."""

from __future__ import annotations

import hashlib
import json
from asyncio import sleep
from base64 import b64decode, b64encode
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.infrastructure.providers.alpaca_stream import (
    AlpacaStreamDecoder,
    alpaca_stream_object_key,
)


class WebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    def __aiter__(self) -> WebSocketConnection: ...

    async def __anext__(self) -> str | bytes: ...


Connect = Callable[[str], object]
Publish = Callable[[str, list[str]], None]
Archive = Callable[[str, bytes], None]


class StreamArchive(Protocol):
    def iter_keys(self, prefix: str = "") -> Iterator[str]: ...

    def get(self, object_key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ArchiveReplayResult:
    replayed: int
    next_cursor: str | None


def replay_archived_stream_batches(
    archive: StreamArchive,
    *,
    publish: Publish,
    is_referenced: Callable[[str], bool],
    after_key: str | None = None,
    limit: int = 100,
) -> ArchiveReplayResult:
    if limit < 1 or limit > 1000:
        raise ValueError("archive replay limit must be between 1 and 1000")
    replayed = 0
    scanned = 0
    cursor: str | None = None
    for key in archive.iter_keys("live/ALPACA/stream-recovery/"):
        if after_key is not None and key <= after_key:
            continue
        cursor = key
        scanned += 1
        envelope = json.loads(archive.get(key))
        if not isinstance(envelope, dict):
            raise ValueError("Alpaca stream recovery envelope must be an object")
        raw_object_key = str(envelope["raw_object_key"])
        if not is_referenced(raw_object_key):
            coverage = MarketDataCoverage(str(envelope["coverage"]))
            raw = b64decode(str(envelope["body_base64"]), validate=True)
            received_at = require_aware(
                datetime.fromisoformat(str(envelope["received_at"]))
            ).astimezone(UTC)
            publish(
                "stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event",
                [raw.decode("utf-8"), received_at.isoformat(), coverage.value],
            )
            replayed += 1
        if scanned == limit:
            break
    return ArchiveReplayResult(
        replayed=replayed,
        next_cursor=cursor if scanned == limit else None,
    )


def alpaca_stream_recovery_object(
    raw: bytes,
    *,
    coverage: MarketDataCoverage,
    received_at: datetime,
) -> tuple[str, bytes]:
    observed_at = require_aware(received_at).astimezone(UTC)
    content_hash = hashlib.sha256(raw).hexdigest()
    timestamp = observed_at.strftime("%Y%m%dT%H%M%S.%fZ")
    key = f"live/ALPACA/stream-recovery/{coverage.value.lower()}/{timestamp}-{content_hash}.json"
    envelope = json.dumps(
        {
            "coverage": coverage.value,
            "received_at": observed_at.isoformat(),
            "raw_object_key": alpaca_stream_object_key(raw, coverage=coverage),
            "body_base64": b64encode(raw).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return key, envelope


class AlpacaStreamPublishUnavailable(RuntimeError):
    pass


class AlpacaStreamArchiveUnavailable(RuntimeError):
    pass


class AlpacaStreamSupervisor:
    """Authenticate, subscribe, persist batches, and enqueue bounded REST recovery on reconnect."""

    def __init__(
        self,
        *,
        data_key: str,
        data_secret: str,
        coverage: MarketDataCoverage,
        symbols: Collection[str],
        publish: Publish,
        archive: Archive,
    ) -> None:
        if not data_key or not data_secret:
            raise ValueError("Alpaca stream credentials are required")
        self._data_key = data_key
        self._data_secret = data_secret
        self._coverage = coverage
        self._symbols = tuple(sorted(str(Symbol(symbol)) for symbol in symbols))
        if not self._symbols:
            raise ValueError("Alpaca stream requires at least one symbol")
        self._publish = publish
        self._archive = archive
        self._decoder = AlpacaStreamDecoder()
        self._last_event: dict[str, datetime] = {}

    @property
    def url(self) -> str:
        return f"wss://stream.data.alpaca.markets/v2/{self._coverage.value.lower()}"

    @property
    def reconnect_watermarks(self) -> dict[str, datetime]:
        return dict(self._last_event)

    def raw_object_key(self, raw: bytes) -> str:
        return alpaca_stream_object_key(raw, coverage=self._coverage)

    async def consume(self, connection: WebSocketConnection) -> None:
        await connection.send(
            json.dumps(
                {"action": "auth", "key": self._data_key, "secret": self._data_secret},
                separators=(",", ":"),
            )
        )
        await connection.send(
            json.dumps(
                {
                    "action": "subscribe",
                    "trades": self._symbols,
                    "quotes": self._symbols,
                    "bars": self._symbols,
                    "updatedBars": self._symbols,
                    "statuses": ["*"],
                },
                separators=(",", ":"),
            )
        )
        async for message in connection:
            raw = message if isinstance(message, bytes) else message.encode()
            received_at = datetime.now(UTC)
            events = self._decoder.decode_batch(raw, received_at=received_at)
            if not events:
                continue
            recovery_key, recovery_envelope = alpaca_stream_recovery_object(
                raw,
                coverage=self._coverage,
                received_at=received_at,
            )
            try:
                # The self-contained recovery envelope goes first, closing the two-write crash gap.
                self._archive(recovery_key, recovery_envelope)
                self._archive(self.raw_object_key(raw), raw)
            except Exception as error:
                raise AlpacaStreamArchiveUnavailable("stream batch archive failed") from error
            try:
                self._publish(
                    "stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event",
                    [raw.decode(), received_at.isoformat(), self._coverage.value],
                )
            except Exception as error:
                raise AlpacaStreamPublishUnavailable("stream batch publish failed") from error
            for event in events:
                previous = self._last_event.get(str(event.symbol))
                if previous is None or event.event_time > previous:
                    self._last_event[str(event.symbol)] = event.event_time

    def publish_reconnect_recovery(self, *, reconnected_at: datetime) -> None:
        for symbol, last_event_at in sorted(self._last_event.items()):
            self._publish(
                "stock_platform.workers.schedules.schedule_alpaca_reconnect_ingestion",
                [symbol, last_event_at.isoformat(), reconnected_at.astimezone(UTC).isoformat()],
            )

    async def run_forever(self) -> None:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed

        delay = 1.0
        while True:
            try:
                async with connect(self.url, open_timeout=10, ping_interval=20) as connection:
                    if self._last_event:
                        self.publish_reconnect_recovery(reconnected_at=datetime.now(UTC))
                    await self.consume(connection)  # type: ignore[arg-type]
                    delay = 1.0
            except (OSError, TimeoutError, ConnectionClosed):
                await sleep(delay)
                delay = min(delay * 2, 30.0)
