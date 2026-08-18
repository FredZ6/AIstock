import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from stock_platform.application.market_data.fallback import FallbackPolicy
from stock_platform.infrastructure.providers.alpaca import AlpacaProvider
from stock_platform.infrastructure.providers.base import (
    FeedType,
    HttpRequest,
    HttpResponse,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
    ResearchDataProvider,
)
from stock_platform.infrastructure.providers.fmp import FmpProvider
from stock_platform.infrastructure.providers.sec import SecProvider

AS_OF = datetime(2026, 8, 16, 12, tzinfo=UTC)


class RecordingStore:
    def __init__(self) -> None:
        self.objects: list[tuple[str, bytes, str]] = []

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.objects.append((object_key, content, content_type))


class RecordingRecordStore:
    def __init__(self) -> None:
        self.records: list[tuple[ProviderRecord, str]] = []

    def persist(self, record: ProviderRecord, normalization_version: str) -> None:
        self.records.append((record, normalization_version))


def successful_transport(requests: list[HttpRequest]) -> Callable[[HttpRequest], HttpResponse]:
    def send(request: HttpRequest) -> HttpResponse:
        requests.append(request)
        body = json.dumps(
            {
                "event_time": "2026-08-16T11:55:00Z",
                "value": "123.45",
                "currency": "USD",
            }
        ).encode()
        return HttpResponse(status_code=200, headers={"etag": "fixture-v1"}, body=body)

    return send


@pytest.mark.parametrize(
    ("provider", "feed_type", "expected_host"),
    [
        ("sec", FeedType.COMPANY_FACTS, "data.sec.gov"),
        ("alpaca", FeedType.PRICE_BARS, "data.alpaca.markets"),
        ("fmp", FeedType.TARGET_CONSENSUS, "financialmodelingprep.com"),
    ],
)
def test_live_adapters_use_fixed_read_only_endpoints_and_persist_raw_first(
    provider: str, feed_type: FeedType, expected_host: str
) -> None:
    requests: list[HttpRequest] = []
    store = RecordingStore()
    record_store = RecordingRecordStore()
    transport = successful_transport(requests)
    adapter: ResearchDataProvider
    if provider == "sec":
        adapter = SecProvider(
            user_agent="research@example.com",
            transport=transport,
            raw_store=store,
            record_store=record_store,
            clock=lambda: AS_OF,
        )
    elif provider == "alpaca":
        adapter = AlpacaProvider(
            data_key="fixture-key",
            data_secret="fixture-secret",
            transport=transport,
            raw_store=store,
            record_store=record_store,
            clock=lambda: AS_OF,
        )
    else:
        adapter = FmpProvider(
            api_key="fixture-key",
            transport=transport,
            raw_store=store,
            record_store=record_store,
            clock=lambda: AS_OF,
        )

    result = adapter.fetch(feed_type, "NVDA", AS_OF)

    assert result.status.value == "ok"
    assert len(result.records) == 1
    assert expected_host in requests[0].url
    assert requests[0].method == "GET"
    assert requests[0].timeout_seconds <= 10
    assert store.objects[0][0].startswith(f"live/{provider.upper()}/")
    assert result.records[0].raw_object_key == store.objects[0][0]
    assert record_store.records == [(result.records[0], f"{provider}-{feed_type.value}-v1")]


def test_live_adapter_never_returns_data_ingested_after_query_cutoff() -> None:
    store = RecordingStore()
    record_store = RecordingRecordStore()
    adapter = FmpProvider(
        api_key="fixture-key",
        transport=successful_transport([]),
        raw_store=store,
        record_store=record_store,
        clock=lambda: AS_OF + timedelta(seconds=1),
    )

    result = adapter.fetch(FeedType.PRICE_BARS, "NVDA", AS_OF)

    assert result.status.value == "unavailable"
    assert result.records == ()
    assert "future_data_rejected" in result.warnings
    assert store.objects
    assert record_store.records


def test_sec_requires_identity_and_sets_user_agent() -> None:
    requests: list[HttpRequest] = []
    store = RecordingStore()
    missing = SecProvider(
        user_agent=None,
        transport=successful_transport(requests),
        raw_store=store,
        clock=lambda: AS_OF,
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)
    configured = SecProvider(
        user_agent="research@example.com",
        transport=successful_transport(requests),
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    assert missing.status.value == "unavailable"
    assert configured.status.value == "ok"
    assert requests[-1].headers["User-Agent"] == "research@example.com"


def test_rate_limit_retries_with_exponential_backoff_and_jitter() -> None:
    responses = [429, 429, 200]
    sleeps: list[float] = []
    store = RecordingStore()

    def transport(request: HttpRequest) -> HttpResponse:
        status = responses.pop(0)
        return HttpResponse(
            status_code=status,
            headers={},
            body=b'{"event_time":"2026-08-16T11:55:00Z","close":"1.00"}',
        )

    result = AlpacaProvider(
        data_key="fixture-key",
        data_secret="fixture-secret",
        transport=transport,
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
        sleep=sleeps.append,
        jitter=lambda: 0.25,
    ).fetch(FeedType.PRICE_BARS, "NVDA", AS_OF)

    assert result.status.value == "ok"
    assert sleeps == [1.25, 2.25]


def test_adapter_timeout_flows_through_fallback_policy() -> None:
    store = RecordingStore()

    def timeout(request: HttpRequest) -> HttpResponse:
        raise TimeoutError

    primary = SecProvider(
        user_agent="research@example.com",
        transport=timeout,
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    fallback = FmpProvider(
        api_key="fixture-key",
        transport=successful_transport([]),
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    )

    result = FallbackPolicy(primary=primary, fallback=fallback).fetch(
        FeedType.COMPANY_FACTS, "NVDA", AS_OF
    )

    assert result.status.value == "ok"
    assert result.provider == "FMP"
    assert "fallback_from=SEC" in result.warnings


def test_raw_payload_is_saved_even_when_normalization_fails() -> None:
    store = RecordingStore()

    def invalid_json(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status_code=200, headers={}, body=b"not-json")

    result = FmpProvider(
        api_key="fixture-key",
        transport=invalid_json,
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    ).fetch(FeedType.ESTIMATES, "NVDA", AS_OF)

    assert result.status.value == "error"
    assert store.objects and store.objects[0][1] == b"not-json"
    assert result.records == ()


def test_conditional_request_reuses_etag_without_changing_endpoint() -> None:
    requests: list[HttpRequest] = []
    store = RecordingStore()
    provider = SecProvider(
        user_agent="research@example.com",
        transport=successful_transport(requests),
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    )

    provider.fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)
    provider.fetch(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    assert requests[0].url == requests[1].url
    assert "If-None-Match" not in requests[0].headers
    assert requests[1].headers["If-None-Match"] == "fixture-v1"


def test_list_payload_uses_provider_timestamp_instead_of_fabricated_zero() -> None:
    store = RecordingStore()

    def list_payload(request: HttpRequest) -> HttpResponse:
        return HttpResponse(
            status_code=200,
            headers={},
            body=b'[{"date":"2026-08-15","estimatedRevenueAvg":"123.45"}]',
        )

    result = FmpProvider(
        api_key="fixture-key",
        transport=list_payload,
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    ).fetch(FeedType.ESTIMATES, "NVDA", AS_OF)

    assert result.status.value == "ok"
    assert result.records[0].event_time == datetime(2026, 8, 15, tzinfo=UTC)
    assert result.records[0].payload["records"][0]["estimatedRevenueAvg"] == "123.45"


def test_future_estimate_period_is_not_misread_as_source_event_time() -> None:
    store = RecordingStore()

    def future_estimate(request: HttpRequest) -> HttpResponse:
        return HttpResponse(
            status_code=200,
            headers={},
            body=b'[{"date":"2027-01-01","estimatedRevenueAvg":"123.45"}]',
        )

    result = FmpProvider(
        api_key="fixture-key",
        transport=future_estimate,
        raw_store=store,
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    ).fetch(FeedType.ESTIMATES, "NVDA", AS_OF)

    assert result.status.value == "ok"
    assert result.records[0].event_time == AS_OF
    assert "source_timestamp_unavailable" in result.records[0].quality_flags
    assert result.records[0].payload["records"][0]["date"] == "2027-01-01"


def test_sec_unknown_symbol_and_unimplemented_section_are_typed_results() -> None:
    def fail_on_network(request: HttpRequest) -> HttpResponse:
        raise AssertionError("network must not run")

    adapter = SecProvider(
        user_agent="research@example.com",
        transport=fail_on_network,
        raw_store=RecordingStore(),
        record_store=RecordingRecordStore(),
        clock=lambda: AS_OF,
    )

    unknown = adapter.fetch(FeedType.COMPANY_FACTS, "TSLA", AS_OF)
    section = adapter.fetch(FeedType.FILING_SECTIONS, "NVDA", AS_OF)

    assert unknown.status.value == "not_found"
    assert section.status.value == "not_supported"


@pytest.mark.parametrize(
    ("adapter", "unsupported_feed"),
    [
        (SecProvider(user_agent=None), FeedType.PRICE_BARS),
        (AlpacaProvider(data_key=None, data_secret=None), FeedType.COMPANY_FACTS),
        (FmpProvider(api_key=None), FeedType.OPTION_AGGREGATES),
    ],
)
def test_adapters_report_not_supported_without_network(
    adapter: object, unsupported_feed: FeedType
) -> None:
    result = adapter.fetch(unsupported_feed, "NVDA", AS_OF)  # type: ignore[attr-defined]
    assert result.status.value == "not_supported"
    assert result.records == ()


def require_live() -> None:
    if os.getenv("LIVE_PROVIDER_TESTS") != "1":
        pytest.skip("LIVE_PROVIDER_TESTS=1 is not set")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"missing requirement: {name}")
    return value


def assert_live_result(result: ProviderResponse, store: RecordingStore) -> None:
    if result.status is ProviderStatus.UNAVAILABLE and "provider_unavailable" in result.warnings:
        pytest.skip("missing requirement: provider network access")
    assert result.status in {ProviderStatus.OK, ProviderStatus.NOT_FOUND}
    if result.status is ProviderStatus.OK:
        assert len(store.objects) == 1


@pytest.mark.live
def test_sec_live_contract() -> None:
    require_live()
    store = RecordingStore()
    result = SecProvider(
        user_agent=required_env("SEC_USER_AGENT"),
        raw_store=store,
        record_store=RecordingRecordStore(),
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", datetime.now(UTC))
    assert_live_result(result, store)


@pytest.mark.live
def test_alpaca_live_contract() -> None:
    require_live()
    store = RecordingStore()
    result = AlpacaProvider(
        data_key=required_env("ALPACA_DATA_KEY"),
        data_secret=required_env("ALPACA_DATA_SECRET"),
        raw_store=store,
        record_store=RecordingRecordStore(),
    ).fetch(FeedType.PRICE_BARS, "NVDA", datetime.now(UTC))
    assert_live_result(result, store)


@pytest.mark.live
def test_fmp_live_contract() -> None:
    require_live()
    store = RecordingStore()
    result = FmpProvider(
        api_key=required_env("FMP_API_KEY"),
        raw_store=store,
        record_store=RecordingRecordStore(),
    ).fetch(FeedType.TARGET_CONSENSUS, "NVDA", datetime.now(UTC))
    assert_live_result(result, store)
