"""Read-only SEC EDGAR data adapter."""

from __future__ import annotations

from datetime import datetime

from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, GovernedHttpProvider

_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
}


class SecProvider(GovernedHttpProvider):
    name = "SEC"
    supported_feeds = frozenset({FeedType.COMPANY_FACTS, FeedType.FILINGS})

    def __init__(self, *, user_agent: str | None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._user_agent = user_agent

    def _configured(self) -> bool:
        return bool(self._user_agent)

    def _headers(self) -> dict[str, str]:
        return super()._headers() | {"User-Agent": self._user_agent or ""}

    def _supports_symbol(self, symbol: Symbol) -> bool:
        return str(symbol) in _CIKS

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        cik = _CIKS[str(symbol)]
        if feed_type is FeedType.COMPANY_FACTS:
            return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        if feed_type is FeedType.FILINGS:
            return f"https://data.sec.gov/submissions/CIK{cik}.json"
        raise ValueError(f"unsupported SEC feed: {feed_type.value}")
