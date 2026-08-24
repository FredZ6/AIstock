"""Read-only Alpaca market-data adapter; no brokerage or order surface."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlencode

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import IngestionErrorClass
from stock_platform.infrastructure.providers.base import (
    FeedType,
    GovernedHttpProvider,
    ProviderBatch,
    ProviderTransportError,
)


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

    def fetch_window(
        self,
        feed_type: FeedType,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str | None,
        coverage: str,
        page_token: str | None = None,
    ) -> ProviderBatch:
        window_start = require_aware(start).astimezone(UTC)
        window_end = require_aware(end).astimezone(UTC)
        normalized_symbol = Symbol(symbol)
        if window_start >= window_end:
            raise ValueError("Alpaca window start must be before end")
        if feed_type not in {FeedType.PRICE_BARS, FeedType.COMPANY_NEWS}:
            raise ProviderTransportError(error_class=IngestionErrorClass.UNSUPPORTED_DATASET)
        if not self._configured():
            raise ProviderTransportError(error_class=IngestionErrorClass.MISSING_CREDENTIALS)
        params: dict[str, str] = {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        }
        if page_token is not None:
            params["page_token"] = page_token
        if feed_type is FeedType.PRICE_BARS:
            if timeframe not in {"1Min", "1Day"}:
                raise ValueError("Alpaca bars require 1Min or 1Day timeframe")
            if coverage.upper() not in {"IEX", "SIP"}:
                raise ValueError("Alpaca coverage must be IEX or SIP")
            params.update({"timeframe": timeframe, "feed": coverage.lower()})
            url = f"https://data.alpaca.markets/v2/stocks/{normalized_symbol}/bars?{urlencode(params)}"
        else:
            if timeframe is not None:
                raise ValueError("Alpaca news does not accept a bar timeframe")
            params["symbols"] = str(normalized_symbol)
            url = f"https://data.alpaca.markets/v1beta1/news?{urlencode(params)}"
        batch = self._fetch_batch_from_url(
            feed_type=feed_type,
            symbol=normalized_symbol,
            query_as_of=window_end,
            url=url,
        )
        if feed_type is FeedType.PRICE_BARS:
            return replace(
                batch,
                headers=batch.headers | {"X-Alpaca-Data-Feed": coverage.upper()},
            )
        return batch
