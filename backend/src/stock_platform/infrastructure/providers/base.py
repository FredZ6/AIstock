"""Provider-neutral contracts for governed research data access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware


class FeedType(StrEnum):
    COMPANY_FACTS = "company_facts"
    FILINGS = "filings"
    FILING_SECTIONS = "filing_sections"
    PRICE_BARS = "price_bars"
    COMPANY_NEWS = "company_news"
    OPTION_AGGREGATES = "option_aggregates"
    ESTIMATES = "estimates"
    TARGET_CONSENSUS = "target_consensus"


class ProviderStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_SUPPORTED = "not_supported"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    symbol: Symbol
    feed_type: FeedType
    provider: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    content_hash: str
    raw_object_key: str
    payload: dict[str, Any]
    is_delayed: bool = False
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_aware(self.event_time)
        require_aware(self.available_at)
        require_aware(self.ingested_at)
        if not self.event_time <= self.available_at <= self.ingested_at:
            raise ValueError("timestamps must satisfy event_time <= available_at <= ingested_at")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    status: ProviderStatus
    provider: str
    feed_type: FeedType
    symbol: Symbol
    query_as_of: datetime
    records: tuple[ProviderRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    trace_id: str | None = None
    missingness: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.query_as_of)


class ResearchDataProvider(Protocol):
    name: str

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse: ...


class RawObjectStore(Protocol):
    def put(self, object_key: str, content: bytes, content_type: str) -> None: ...
