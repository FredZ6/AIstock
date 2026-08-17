from datetime import UTC, datetime, timedelta

from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
)
from stock_platform.infrastructure.providers.fallback import FallbackPolicy

AS_OF = datetime(2026, 8, 16, 12, tzinfo=UTC)


def response(
    status: ProviderStatus,
    provider: str,
    *,
    available_at: datetime = AS_OF - timedelta(minutes=1),
    payload: dict[str, str] | None = None,
) -> ProviderResponse:
    records: tuple[ProviderRecord, ...] = ()
    if status is ProviderStatus.OK:
        records = (
            ProviderRecord(
                symbol=Symbol("NVDA"),
                feed_type=FeedType.COMPANY_FACTS,
                provider=provider,
                event_time=available_at - timedelta(minutes=1),
                available_at=available_at,
                ingested_at=max(AS_OF, available_at),
                content_hash=(provider.lower() + "0" * 64)[:64],
                raw_object_key=f"live/{provider.lower()}/fixture.json",
                payload=payload or {"revenue": "10"},
            ),
        )
    return ProviderResponse(
        status=status,
        provider=provider,
        feed_type=FeedType.COMPANY_FACTS,
        symbol=Symbol("NVDA"),
        query_as_of=AS_OF,
        records=records,
        missingness=None if records else status.value.upper(),
    )


class SequenceProvider:
    def __init__(self, name: str, *responses: ProviderResponse) -> None:
        self.name = name
        self.responses = list(responses)
        self.calls = 0

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def test_primary_success_does_not_call_fallback() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.OK, "SEC"))
    fallback = SequenceProvider("FMP", response(ProviderStatus.OK, "FMP"))

    result = FallbackPolicy(primary=primary, fallback=fallback).fetch(
        FeedType.COMPANY_FACTS, "NVDA", AS_OF
    )

    assert result.provider == "SEC"
    assert fallback.calls == 0


def test_timeout_uses_fresh_fallback_without_changing_feed_semantics() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.UNAVAILABLE, "SEC"))
    fallback = SequenceProvider("FMP", response(ProviderStatus.OK, "FMP"))

    result = FallbackPolicy(primary=primary, fallback=fallback).fetch(
        FeedType.COMPANY_FACTS, "NVDA", AS_OF
    )

    assert result.status is ProviderStatus.OK
    assert result.provider == "FMP"
    assert result.feed_type is FeedType.COMPANY_FACTS
    assert "fallback_from=SEC" in result.warnings


def test_stale_fallback_is_rejected() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.UNAVAILABLE, "SEC"))
    fallback = SequenceProvider(
        "FMP",
        response(ProviderStatus.OK, "FMP", available_at=AS_OF - timedelta(days=3)),
    )

    result = FallbackPolicy(
        primary=primary,
        fallback=fallback,
        max_staleness=timedelta(days=1),
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    assert result.status is ProviderStatus.UNAVAILABLE
    assert result.records == ()
    assert "stale_fallback_rejected" in result.warnings


def test_future_fallback_is_rejected_by_point_in_time_boundary() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.UNAVAILABLE, "SEC"))
    fallback = SequenceProvider(
        "FMP",
        response(ProviderStatus.OK, "FMP", available_at=AS_OF + timedelta(seconds=1)),
    )

    result = FallbackPolicy(primary=primary, fallback=fallback).fetch(
        FeedType.COMPANY_FACTS, "NVDA", AS_OF
    )

    assert result.status is ProviderStatus.UNAVAILABLE
    assert result.records == ()
    assert "future_fallback_rejected" in result.warnings


def test_circuit_opens_after_bounded_failures_and_skips_primary() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.UNAVAILABLE, "SEC"))
    fallback = SequenceProvider("FMP", response(ProviderStatus.OK, "FMP"))
    policy = FallbackPolicy(primary=primary, fallback=fallback, failure_threshold=2)

    policy.fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)
    policy.fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)
    result = policy.fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    assert primary.calls == 2
    assert fallback.calls == 3
    assert "circuit_open=SEC" in result.warnings


def test_conflict_prefers_primary_and_marks_quality() -> None:
    primary = SequenceProvider("SEC", response(ProviderStatus.OK, "SEC", payload={"revenue": "10"}))
    fallback = SequenceProvider(
        "FMP", response(ProviderStatus.OK, "FMP", payload={"revenue": "11"})
    )

    result = FallbackPolicy(
        primary=primary,
        fallback=fallback,
        compare_on_success=True,
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    assert result.provider == "SEC"
    assert result.records[0].payload == {"revenue": "10"}
    assert "provider_conflict=FMP" in result.warnings
    assert "conflict" in result.records[0].quality_flags


def test_not_supported_and_not_found_remain_distinct_and_do_not_fabricate_zero() -> None:
    fallback = SequenceProvider("FMP", response(ProviderStatus.OK, "FMP"))
    for status in (ProviderStatus.NOT_SUPPORTED, ProviderStatus.NOT_FOUND):
        primary = SequenceProvider("SEC", response(status, "SEC"))
        result = FallbackPolicy(primary=primary, fallback=fallback).fetch(
            FeedType.COMPANY_FACTS, "NVDA", AS_OF
        )
        assert result.status is status
        assert result.records == ()
    assert fallback.calls == 0
