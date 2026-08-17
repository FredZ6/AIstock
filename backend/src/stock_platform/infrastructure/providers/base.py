"""Provider-neutral contracts for governed research data access."""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


HttpTransport = Callable[[HttpRequest], HttpResponse]


def _parse_provider_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _normalize_json(document: object) -> tuple[datetime, dict[str, Any]]:
    timestamp_keys = (
        "event_time",
        "timestamp",
        "t",
        "date",
        "acceptedDate",
        "publishedDate",
        "created_at",
        "updated_at",
        "filed",
        "acceptanceDateTime",
    )
    if isinstance(document, dict):
        payload = dict(document)
    elif (
        isinstance(document, list) and document and all(isinstance(item, dict) for item in document)
    ):
        payload = {"records": document}
    else:
        raise ValueError("provider JSON must contain object records")
    timestamps: list[datetime] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in timestamp_keys and item:
                    try:
                        timestamps.append(_parse_provider_timestamp(str(item)))
                    except ValueError:
                        pass
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(document)
    if not timestamps:
        raise ValueError("provider payload has no source timestamp")
    payload.pop("event_time", None)
    return max(timestamps), payload


def urllib_transport(request: HttpRequest) -> HttpResponse:
    outgoing = Request(request.url, headers=request.headers, method=request.method)
    try:
        with urlopen(outgoing, timeout=request.timeout_seconds) as incoming:  # noqa: S310
            return HttpResponse(
                status_code=incoming.status,
                headers=dict(incoming.headers.items()),
                body=incoming.read(),
            )
    except HTTPError as error:
        return HttpResponse(
            status_code=error.code,
            headers=dict(error.headers.items()),
            body=error.read(),
        )
    except (TimeoutError, URLError) as error:
        raise TimeoutError("provider request failed") from error


class GovernedHttpProvider:
    """Small shared GET-only adapter with bounded retries and raw-first persistence."""

    name = "UNCONFIGURED"
    supported_feeds: frozenset[FeedType] = frozenset()

    def __init__(
        self,
        *,
        transport: HttpTransport = urllib_transport,
        raw_store: RawObjectStore | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        timeout_seconds: float = 5.0,
        max_attempts: int = 3,
        max_concurrency: int = 4,
    ) -> None:
        if not 0 < timeout_seconds <= 10:
            raise ValueError("provider timeout must be in (0, 10] seconds")
        if not 1 <= max_attempts <= 5:
            raise ValueError("provider max_attempts must be in [1, 5]")
        if max_concurrency < 1:
            raise ValueError("provider max_concurrency must be positive")
        self._transport = transport
        self._raw_store = raw_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._jitter = jitter
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._validators: dict[str, dict[str, str]] = {}

    def _configured(self) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        raise NotImplementedError

    def _unavailable(
        self, feed_type: FeedType, symbol: Symbol, as_of: datetime, warning: str
    ) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.UNAVAILABLE,
            provider=self.name,
            feed_type=feed_type,
            symbol=symbol,
            query_as_of=as_of,
            warnings=(warning,),
            missingness="UNAVAILABLE",
        )

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        query_as_of = require_aware(as_of)
        normalized_symbol = Symbol(symbol)
        if feed_type not in self.supported_feeds:
            return ProviderResponse(
                status=ProviderStatus.NOT_SUPPORTED,
                provider=self.name,
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                missingness="UNAVAILABLE",
            )
        if not self._configured():
            return self._unavailable(
                feed_type, normalized_symbol, query_as_of, "missing_credentials"
            )
        if self._raw_store is None:
            return self._unavailable(
                feed_type, normalized_symbol, query_as_of, "raw_store_not_configured"
            )

        url = self._url(feed_type, normalized_symbol, query_as_of)
        headers = self._headers() | self._validators.get(url, {})
        response: HttpResponse | None = None
        for attempt in range(self._max_attempts):
            request = HttpRequest("GET", url, headers, self._timeout_seconds)
            try:
                with self._semaphore:
                    response = self._transport(request)
            except TimeoutError:
                response = None
            retryable = (
                response is None or response.status_code == 429 or response.status_code >= 500
            )
            if retryable and attempt + 1 < self._max_attempts:
                self._sleep((2**attempt) + self._jitter())
                continue
            break

        if response is None or response.status_code in {429} or response.status_code >= 500:
            return self._unavailable(
                feed_type, normalized_symbol, query_as_of, "provider_unavailable"
            )
        if response.status_code == 404:
            return ProviderResponse(
                status=ProviderStatus.NOT_FOUND,
                provider=self.name,
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                missingness="MISSING",
            )
        if response.status_code == 304:
            return self._unavailable(
                feed_type, normalized_symbol, query_as_of, "not_modified_without_cache"
            )
        if not 200 <= response.status_code < 300:
            return ProviderResponse(
                status=ProviderStatus.ERROR,
                provider=self.name,
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                warnings=(f"provider_http_status={response.status_code}",),
                missingness="UNAVAILABLE",
            )

        ingested_at = require_aware(self._clock())
        content_hash = hashlib.sha256(response.body).hexdigest()
        raw_object_key = f"live/{self.name}/{feed_type.value}/{content_hash}.json"
        self._raw_store.put(raw_object_key, response.body, "application/json")
        try:
            event_time, document = _normalize_json(json.loads(response.body))
            event_time = require_aware(event_time)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return ProviderResponse(
                status=ProviderStatus.ERROR,
                provider=self.name,
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                warnings=("normalization_failed",),
                missingness="UNAVAILABLE",
            )

        etag = response.headers.get("etag") or response.headers.get("ETag")
        modified = response.headers.get("last-modified") or response.headers.get("Last-Modified")
        validators: dict[str, str] = {}
        if etag:
            validators["If-None-Match"] = etag
        if modified:
            validators["If-Modified-Since"] = modified
        if validators:
            self._validators[url] = validators

        record = ProviderRecord(
            symbol=normalized_symbol,
            feed_type=feed_type,
            provider=self.name,
            event_time=event_time,
            available_at=ingested_at,
            ingested_at=ingested_at,
            content_hash=content_hash,
            raw_object_key=raw_object_key,
            payload=document,
        )
        return ProviderResponse(
            status=ProviderStatus.OK,
            provider=self.name,
            feed_type=feed_type,
            symbol=normalized_symbol,
            query_as_of=query_as_of,
            records=(record,),
        )
