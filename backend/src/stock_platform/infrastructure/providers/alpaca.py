"""Read-only Alpaca market-data adapter; no brokerage or order surface."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, GovernedHttpProvider


class AlpacaProvider(GovernedHttpProvider):
    name = "ALPACA"
    supported_feeds = frozenset(
        {FeedType.PRICE_BARS, FeedType.COMPANY_NEWS, FeedType.OPTION_AGGREGATES}
    )

    def __init__(
        self,
        *,
        data_key: str | None,
        data_secret: str | None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._data_key = data_key
        self._data_secret = data_secret

    def _configured(self) -> bool:
        return bool(self._data_key and self._data_secret)

    def _headers(self) -> dict[str, str]:
        return super()._headers() | {
            "APCA-API-KEY-ID": self._data_key or "",
            "APCA-API-SECRET-KEY": self._data_secret or "",
        }

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        end = as_of.isoformat()
        if feed_type is FeedType.PRICE_BARS:
            query = urlencode({"timeframe": "1Day", "end": end, "feed": "iex"})
            return f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{query}"
        if feed_type is FeedType.COMPANY_NEWS:
            query = urlencode({"symbols": str(symbol), "end": end})
            return f"https://data.alpaca.markets/v1beta1/news?{query}"
        query = urlencode({"feed": "indicative"})
        return f"https://data.alpaca.markets/v1beta1/options/snapshots/{symbol}?{query}"
