from __future__ import annotations

import importlib
import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.providers.alpaca_stream import AlpacaStreamDecoder
from stock_platform.infrastructure.providers.base import ProviderBatch, ProviderRateLimit

FIXTURES = Path(__file__).parent / "fixtures" / "alpaca"
OBSERVED_AT = datetime(2026, 8, 21, 14, 31, tzinfo=UTC)


def _batch(name: str, feed_type: FeedType) -> ProviderBatch:
    return ProviderBatch(
        provider="ALPACA",
        feed_type=feed_type,
        symbol=Symbol("NVDA"),
        query_as_of=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        body=(FIXTURES / name).read_bytes(),
        headers=(
            {"X-AIStock-Verified-Coverage": "IEX"} if feed_type is FeedType.PRICE_BARS else {}
        ),
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )


def test_recorded_alpaca_rest_bars_and_news_normalize_deterministically() -> None:
    module_name = "stock_platform.application.ingestion.normalizers.alpaca"
    try:
        module_spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "Alpaca normalizer is missing"
    normalizer = importlib.import_module(module_name).AlpacaNormalizer()

    bars = normalizer.normalize_batch(_batch("rest_bars.json", FeedType.PRICE_BARS))
    news = normalizer.normalize_batch(_batch("rest_news.json", FeedType.COMPANY_NEWS))

    assert len(bars) == 1
    assert bars[0].symbol == "NVDA"
    assert bars[0].event_time == datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    assert bars[0].close == Decimal("181.00")
    assert bars[0].volume == Decimal("125000")
    assert bars[0].coverage == "IEX"
    assert bars[0].session == "REGULAR"
    assert len(news) == 1
    assert news[0].article_id == "987654"
    assert news[0].published_at == datetime(2026, 8, 21, 13, tzinfo=UTC)
    assert news[0].observed_at is None
    assert news[0].pit_eligible is False


def test_news_is_pit_eligible_only_with_explicit_provider_observation_time() -> None:
    normalizer = importlib.import_module(
        "stock_platform.application.ingestion.normalizers.alpaca"
    ).AlpacaNormalizer()
    body = json.dumps(
        {
            "news": [
                {
                    "id": 1,
                    "headline": "Explicit observation fixture",
                    "created_at": "2026-08-21T13:00:00Z",
                    "observed_at": "2026-08-21T13:01:00Z",
                    "symbols": ["NVDA"],
                    "source": "fixture-wire",
                }
            ]
        }
    ).encode()
    batch = ProviderBatch(
        provider="ALPACA",
        feed_type=FeedType.COMPANY_NEWS,
        symbol=Symbol("NVDA"),
        query_as_of=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        body=body,
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )

    article = normalizer.normalize_batch(batch)[0]

    assert article.observed_at == datetime(2026, 8, 21, 13, 1, tzinfo=UTC)
    assert article.pit_eligible is True


def test_daily_bar_uses_official_regular_session_not_midnight_anchor_session() -> None:
    normalizer = importlib.import_module(
        "stock_platform.application.ingestion.normalizers.alpaca"
    ).AlpacaNormalizer()
    body = json.dumps(
        {
            "bars": [
                {
                    "t": "2026-08-21T04:00:00Z",
                    "o": "180",
                    "h": "182",
                    "l": "179",
                    "c": "181",
                    "v": "1000",
                }
            ],
            "symbol": "NVDA",
        }
    ).encode()
    batch = ProviderBatch(
        provider="ALPACA",
        feed_type=FeedType.PRICE_BARS,
        symbol=Symbol("NVDA"),
        query_as_of=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        body=body,
        headers={
            "X-AIStock-Verified-Coverage": "SIP",
            "X-AIStock-Timeframe": "1Day",
        },
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )

    bar = normalizer.normalize_batch(batch)[0]

    assert bar.session == "REGULAR"
    assert bar.payload["timeframe"] == "1Day"


def test_recorded_alpaca_ws_events_decode_without_fact_table_expansion() -> None:
    events = AlpacaStreamDecoder().decode_batch(
        (FIXTURES / "ws_events.json").read_bytes(),
        received_at=OBSERVED_AT,
    )

    assert [event.event_kind for event in events] == [
        "bar",
        "updated_bar",
        "trade",
        "quote",
        "status",
    ]
    assert [event.feed_type.value for event in events] == [
        "price_bars",
        "price_bars",
        "trades",
        "quotes",
        "market_status",
    ]
    assert all(event.symbol == "NVDA" for event in events)
