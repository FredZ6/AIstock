import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from stock_platform.infrastructure.providers.alpaca_stream import AlpacaStreamNormalizer


class RecordingRawObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.objects[object_key] = (content, content_type)


def raw_bar(*, event_time: str = "2026-08-20T14:35:00Z", message_type: str = "b") -> bytes:
    return json.dumps(
        {
            "T": message_type,
            "S": "nvda",
            "t": event_time,
            "o": 100.1,
            "h": 106.2,
            "l": 99.9,
            "c": 106.0,
            "v": 600,
        },
        separators=(",", ":"),
    ).encode()


def test_alpaca_bar_normalization_preserves_decimal_time_and_provenance() -> None:
    received_at = datetime(2026, 8, 20, 14, 35, 2, tzinfo=UTC)
    raw_store = RecordingRawObjectStore()
    normalizer = AlpacaStreamNormalizer(raw_store=raw_store)
    payload = raw_bar()

    item = normalizer.normalize(payload, received_at=received_at)

    assert item.symbol == "NVDA"
    assert item.event_time == datetime(2026, 8, 20, 14, 35, tzinfo=UTC)
    assert item.available_at == received_at
    assert item.ingested_at == received_at
    assert item.close == Decimal("106.0")
    assert item.volume == Decimal("600")
    assert item.previous_close is None
    assert item.provider == "ALPACA"
    assert len(item.content_hash) == 64
    assert item.raw_object_key.startswith("alpaca-stream/nvda/2026/08/20/")
    assert raw_store.objects[item.raw_object_key] == (payload, "application/json")

    repeated = normalizer.normalize(payload, received_at=received_at)
    assert repeated == item


def test_alpaca_updated_bar_is_accepted_and_written_before_publication() -> None:
    received_at = datetime(2026, 8, 20, 14, 36, tzinfo=UTC)
    raw_store = RecordingRawObjectStore()
    payload = raw_bar(message_type="u")

    item = AlpacaStreamNormalizer(raw_store=raw_store).normalize(payload, received_at=received_at)

    assert item.raw_payload["T"] == "u"
    assert raw_store.objects[item.raw_object_key][0] == payload


def test_alpaca_normalizer_rejects_future_and_non_bar_events() -> None:
    received_at = datetime(2026, 8, 20, 14, 34, 59, tzinfo=UTC)
    normalizer = AlpacaStreamNormalizer(raw_store=RecordingRawObjectStore())
    with pytest.raises(ValueError, match="future"):
        normalizer.normalize(raw_bar(), received_at=received_at)

    with pytest.raises(ValueError, match="minute bar"):
        normalizer.normalize(b'{"T":"q"}', received_at=received_at)

    with pytest.raises(ValueError, match="timezone-aware"):
        normalizer.normalize(raw_bar(), received_at=datetime(2026, 8, 20, 14, 35))
