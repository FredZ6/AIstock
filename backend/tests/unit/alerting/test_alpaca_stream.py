import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from stock_platform.infrastructure.providers.alpaca_stream import AlpacaStreamNormalizer


def raw_bar(*, event_time: str = "2026-08-20T14:35:00Z") -> bytes:
    return json.dumps(
        {
            "T": "b",
            "S": "nvda",
            "t": event_time,
            "o": 100.1,
            "h": 106.2,
            "l": 99.9,
            "c": 106.0,
            "v": 600,
            "pc": 99.0,
        },
        separators=(",", ":"),
    ).encode()


def test_alpaca_bar_normalization_preserves_decimal_time_and_provenance() -> None:
    received_at = datetime(2026, 8, 20, 14, 35, 2, tzinfo=UTC)

    item = AlpacaStreamNormalizer().normalize(raw_bar(), received_at=received_at)

    assert item.symbol == "NVDA"
    assert item.event_time == datetime(2026, 8, 20, 14, 35, tzinfo=UTC)
    assert item.available_at == received_at
    assert item.ingested_at == received_at
    assert item.close == Decimal("106.0")
    assert item.volume == Decimal("600")
    assert item.previous_close == Decimal("99.0")
    assert item.provider == "ALPACA"
    assert len(item.content_hash) == 64
    assert item.raw_object_key.startswith("alpaca-stream/nvda/2026/08/20/")

    repeated = AlpacaStreamNormalizer().normalize(raw_bar(), received_at=received_at)
    assert repeated == item


def test_alpaca_normalizer_rejects_future_and_non_bar_events() -> None:
    received_at = datetime(2026, 8, 20, 14, 34, 59, tzinfo=UTC)
    with pytest.raises(ValueError, match="future"):
        AlpacaStreamNormalizer().normalize(raw_bar(), received_at=received_at)

    with pytest.raises(ValueError, match="minute bar"):
        AlpacaStreamNormalizer().normalize(b'{"T":"q"}', received_at=received_at)

    with pytest.raises(ValueError, match="timezone-aware"):
        AlpacaStreamNormalizer().normalize(raw_bar(), received_at=datetime(2026, 8, 20, 14, 35))
