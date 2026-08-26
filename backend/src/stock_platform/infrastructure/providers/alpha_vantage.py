"""Read-only Alpha Vantage full-market earnings-calendar transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import Connection, or_, select

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import (
    security_identifier_version,
    watchlist_item,
)
from stock_platform.infrastructure.providers.base import FeedType, GovernedHttpProvider


@dataclass(frozen=True, slots=True)
class AlphaSymbolIdentity:
    security_id: UUID
    symbol: Symbol
    provider_symbol: str


class PostgresAlphaSymbolResolver:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def identities(self, as_of: datetime) -> dict[str, AlphaSymbolIdentity]:
        cutoff = require_aware(as_of)
        rows = self._connection.execute(
            select(
                security_identifier_version.c.security_id,
                security_identifier_version.c.identifier_value,
                security_identifier_version.c.provider_identifiers,
            )
            .join(
                watchlist_item,
                watchlist_item.c.security_id == security_identifier_version.c.security_id,
            )
            .where(
                security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL",
                security_identifier_version.c.available_at <= cutoff,
                security_identifier_version.c.effective_from <= cutoff,
                or_(
                    security_identifier_version.c.effective_to.is_(None),
                    security_identifier_version.c.effective_to > cutoff,
                ),
            )
        ).mappings()
        identities: dict[str, AlphaSymbolIdentity] = {}
        for row in rows:
            canonical = Symbol(str(row["identifier_value"]))
            provider_symbol = str(row["provider_identifiers"].get("ALPHA_VANTAGE", canonical))
            if provider_symbol in identities:
                raise ValueError("duplicate Alpha Vantage provider symbol in Security master")
            identities[provider_symbol] = AlphaSymbolIdentity(
                security_id=row["security_id"],
                symbol=canonical,
                provider_symbol=provider_symbol,
            )
        return identities

    def mapping(self, as_of: datetime) -> dict[str, str]:
        return {
            provider_symbol: str(identity.symbol)
            for provider_symbol, identity in self.identities(as_of).items()
        }


class AlphaVantageProvider(GovernedHttpProvider):
    name = "ALPHA_VANTAGE"
    supported_feeds = frozenset({FeedType.EARNINGS_CALENDAR})

    def __init__(self, *, api_key: str | None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return self._configured()

    def _configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _headers(self) -> dict[str, str]:
        return {"Accept": "text/csv"}

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        if feed_type is not FeedType.EARNINGS_CALENDAR:
            raise ValueError(f"unsupported Alpha Vantage feed: {feed_type.value}")
        query = urlencode(
            {
                "function": "EARNINGS_CALENDAR",
                "horizon": "12month",
                "apikey": self._api_key,
            }
        )
        return f"https://www.alphavantage.co/query?{query}"
