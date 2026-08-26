"""Frozen value objects shared by ingestion orchestration and persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

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
    EARNINGS_CALENDAR = "earnings_calendar"


class IngestionJobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    COMPLETED_WITH_GAPS = "COMPLETED_WITH_GAPS"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


_LEGAL_TRANSITIONS = {
    IngestionJobState.QUEUED: frozenset({IngestionJobState.RUNNING, IngestionJobState.CANCELLED}),
    IngestionJobState.RUNNING: frozenset(
        {
            IngestionJobState.SUCCEEDED,
            IngestionJobState.COMPLETED_WITH_GAPS,
            IngestionJobState.RETRY_SCHEDULED,
            IngestionJobState.FAILED,
            IngestionJobState.DEAD_LETTER,
        }
    ),
    IngestionJobState.RETRY_SCHEDULED: frozenset(
        {IngestionJobState.QUEUED, IngestionJobState.CANCELLED}
    ),
}


def can_transition(current: IngestionJobState, target: IngestionJobState) -> bool:
    return target in _LEGAL_TRANSITIONS.get(current, ())


class IngestionErrorClass(StrEnum):
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    PROVIDER_5XX = "PROVIDER_5XX"
    TEMPORARY_DATABASE = "TEMPORARY_DATABASE"
    TEMPORARY_OBJECT_STORE = "TEMPORARY_OBJECT_STORE"
    INVALID_AUTH = "INVALID_AUTH"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    UNSUPPORTED_DATASET = "UNSUPPORTED_DATASET"
    INVALID_SECURITY = "INVALID_SECURITY"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"


class RetryDisposition(StrEnum):
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    QUARANTINE = "QUARANTINE"


_RETRYABLE_ERRORS = frozenset(
    {
        IngestionErrorClass.TIMEOUT,
        IngestionErrorClass.NETWORK,
        IngestionErrorClass.RATE_LIMIT,
        IngestionErrorClass.PROVIDER_5XX,
        IngestionErrorClass.TEMPORARY_DATABASE,
        IngestionErrorClass.TEMPORARY_OBJECT_STORE,
    }
)


def retry_disposition(error_class: IngestionErrorClass) -> RetryDisposition:
    if error_class in _RETRYABLE_ERRORS:
        return RetryDisposition.RETRYABLE
    if error_class is IngestionErrorClass.SCHEMA_DRIFT:
        return RetryDisposition.QUARANTINE
    return RetryDisposition.NON_RETRYABLE


class DataPurpose(StrEnum):
    REALTIME_CONTEXT = "REALTIME_CONTEXT"
    RESEARCH = "RESEARCH"
    REPLAY = "REPLAY"
    PAPER_EXECUTION = "PAPER_EXECUTION"


class MarketDataCoverage(StrEnum):
    IEX = "IEX"
    SIP = "SIP"


class MarketSession(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    OVERNIGHT = "OVERNIGHT"


def _canonicalize(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return require_aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, float):
        raise TypeError("binary float is forbidden in ingestion requests; use Decimal")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Decimal values must be finite")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("ingestion request keys must be strings")
        return MappingProxyType({key: _canonicalize(value[key]) for key in sorted(value)})
    if isinstance(value, (list, tuple)):
        return tuple(_canonicalize(item) for item in value)
    raise TypeError(f"unsupported ingestion request value: {type(value).__name__}")


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True, slots=True, init=False)
class IngestionRequest:
    canonical_payload: Mapping[str, Any]
    request_hash: str

    def __init__(self, payload: Mapping[str, object]) -> None:
        canonical = _canonicalize(payload)
        if not isinstance(canonical, Mapping):
            raise TypeError("ingestion request must be a mapping")
        encoded = json.dumps(
            _json_ready(canonical),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        object.__setattr__(self, "canonical_payload", canonical)
        object.__setattr__(self, "request_hash", hashlib.sha256(encoded).hexdigest())
