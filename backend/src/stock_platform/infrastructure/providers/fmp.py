"""Read-only Financial Modeling Prep research-data adapter."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, GovernedHttpProvider


class FmpProvider(GovernedHttpProvider):
    name = "FMP"
    supported_feeds = frozenset(
        {
            FeedType.COMPANY_FACTS,
            FeedType.PRICE_BARS,
            FeedType.ESTIMATES,
            FeedType.TARGET_CONSENSUS,
        }
    )

    def __init__(self, *, api_key: str | None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    def _configured(self) -> bool:
        return bool(self._api_key)

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        endpoint = {
            FeedType.COMPANY_FACTS: "income-statement",
            FeedType.PRICE_BARS: "historical-price-eod/full",
            FeedType.ESTIMATES: "analyst-estimates",
            FeedType.TARGET_CONSENSUS: "price-target-consensus",
        }[feed_type]
        query = urlencode(
            {"symbol": str(symbol), "to": as_of.date().isoformat(), "apikey": self._api_key}
        )
        return f"https://financialmodelingprep.com/stable/{endpoint}?{query}"
