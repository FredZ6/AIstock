from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionErrorClass,
    IngestionJobState,
    IngestionRequest,
    MarketDataCoverage,
    MarketSession,
    RetryDisposition,
    can_transition,
    retry_disposition,
)


def test_ingestion_enums_match_the_approved_contract() -> None:
    assert {state.value for state in IngestionJobState} == {
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "COMPLETED_WITH_GAPS",
        "RETRY_SCHEDULED",
        "FAILED",
        "DEAD_LETTER",
        "CANCELLED",
    }
    assert {purpose.value for purpose in DataPurpose} == {
        "REALTIME_CONTEXT",
        "RESEARCH",
        "REPLAY",
        "PAPER_EXECUTION",
    }
    assert {coverage.value for coverage in MarketDataCoverage} == {"IEX", "SIP"}
    assert {session.value for session in MarketSession} == {
        "PRE_MARKET",
        "REGULAR",
        "AFTER_HOURS",
        "OVERNIGHT",
    }
    assert FeedType.PRICE_BARS.value == "price_bars"


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IngestionJobState.QUEUED, IngestionJobState.RUNNING),
        (IngestionJobState.QUEUED, IngestionJobState.CANCELLED),
        (IngestionJobState.RUNNING, IngestionJobState.SUCCEEDED),
        (IngestionJobState.RUNNING, IngestionJobState.COMPLETED_WITH_GAPS),
        (IngestionJobState.RUNNING, IngestionJobState.RETRY_SCHEDULED),
        (IngestionJobState.RUNNING, IngestionJobState.FAILED),
        (IngestionJobState.RUNNING, IngestionJobState.DEAD_LETTER),
        (IngestionJobState.RETRY_SCHEDULED, IngestionJobState.QUEUED),
        (IngestionJobState.RETRY_SCHEDULED, IngestionJobState.CANCELLED),
    ],
)
def test_approved_job_state_transitions_are_legal(
    current: IngestionJobState, target: IngestionJobState
) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    "terminal",
    [
        IngestionJobState.SUCCEEDED,
        IngestionJobState.COMPLETED_WITH_GAPS,
        IngestionJobState.FAILED,
        IngestionJobState.DEAD_LETTER,
        IngestionJobState.CANCELLED,
    ],
)
@pytest.mark.parametrize("target", list(IngestionJobState))
def test_terminal_job_states_cannot_reopen(
    terminal: IngestionJobState, target: IngestionJobState
) -> None:
    assert not can_transition(terminal, target)


@pytest.mark.parametrize(
    ("error_class", "expected"),
    [
        (IngestionErrorClass.TIMEOUT, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.NETWORK, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.RATE_LIMIT, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.PROVIDER_5XX, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.TEMPORARY_DATABASE, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.TEMPORARY_OBJECT_STORE, RetryDisposition.RETRYABLE),
        (IngestionErrorClass.INVALID_AUTH, RetryDisposition.NON_RETRYABLE),
        (IngestionErrorClass.MISSING_CREDENTIALS, RetryDisposition.NON_RETRYABLE),
        (IngestionErrorClass.UNSUPPORTED_DATASET, RetryDisposition.NON_RETRYABLE),
        (IngestionErrorClass.INVALID_SECURITY, RetryDisposition.NON_RETRYABLE),
        (IngestionErrorClass.SCHEMA_DRIFT, RetryDisposition.QUARANTINE),
    ],
)
def test_error_classes_have_a_frozen_retry_disposition(
    error_class: IngestionErrorClass, expected: RetryDisposition
) -> None:
    assert retry_disposition(error_class) is expected


def test_request_hash_is_canonical_for_order_timezones_and_decimal_scale() -> None:
    instant = datetime(2026, 8, 23, 12, tzinfo=UTC)
    first = IngestionRequest(
        {
            "provider": "ALPACA",
            "dataset": FeedType.PRICE_BARS,
            "window": {"start": instant, "limit": 100},
            "price_floor": Decimal("1.00"),
        }
    )
    second = IngestionRequest(
        {
            "price_floor": Decimal("1.0"),
            "window": {
                "limit": 100,
                "start": instant.astimezone(timezone(timedelta(hours=8))),
            },
            "dataset": "price_bars",
            "provider": "ALPACA",
        }
    )

    assert first.request_hash == second.request_hash
    assert len(first.request_hash) == 64
    assert first.canonical_payload["window"]["start"] == "2026-08-23T12:00:00Z"


def test_request_is_immutable_after_the_source_mapping_changes() -> None:
    source = {"symbols": ["NVDA", "AAPL"]}
    request = IngestionRequest(source)

    source["symbols"].append("MSFT")

    assert request.canonical_payload == {"symbols": ("NVDA", "AAPL")}


@pytest.mark.parametrize(
    "payload",
    [
        {"as_of": datetime(2026, 8, 23, 12)},
        {"window": {"end": datetime(2026, 8, 23, 12)}},
    ],
)
def test_request_rejects_naive_datetimes(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        IngestionRequest(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 1.0},
        {"thresholds": [Decimal("1"), 2.5]},
    ],
)
def test_request_rejects_binary_floats(payload: dict[str, object]) -> None:
    with pytest.raises(TypeError, match="float"):
        IngestionRequest(payload)
