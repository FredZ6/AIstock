import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from stock_platform.infrastructure.providers.alpaca import AlpacaProvider
from stock_platform.infrastructure.providers.base import (
    FeedType,
    HttpRequest,
    HttpResponse,
    ResearchDataProvider,
)
from stock_platform.infrastructure.providers.fallback import FallbackPolicy
from stock_platform.infrastructure.providers.fmp import FmpProvider
from stock_platform.infrastructure.providers.sec import SecProvider

AS_OF = datetime(2026, 8, 16, 12, tzinfo=UTC)


class RecordingStore:
    def __init__(self) -> None:
        self.objects: list[tuple[str, bytes, str]] = []

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.objects.append((object_key, content, content_type))


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
    transport = successful_transport(requests)
    adapter: ResearchDataProvider
    if provider == "sec":
        adapter = SecProvider(
            user_agent="research@example.com",
            transport=transport,
            raw_store=store,
            clock=lambda: AS_OF,
        )
    elif provider == "alpaca":
        adapter = AlpacaProvider(
            data_key="fixture-key",
            data_secret="fixture-secret",
            transport=transport,
            raw_store=store,
            clock=lambda: AS_OF,
        )
    else:
        adapter = FmpProvider(
            api_key="fixture-key",
            transport=transport,
            raw_store=store,
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
        clock=lambda: AS_OF,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    fallback = FmpProvider(
        api_key="fixture-key",
        transport=successful_transport([]),
        raw_store=store,
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
        clock=lambda: AS_OF,
    ).fetch(FeedType.ESTIMATES, "NVDA", AS_OF)

    assert result.status.value == "ok"
    assert result.records[0].event_time == datetime(2026, 8, 15, tzinfo=UTC)
    assert result.records[0].payload["records"][0]["estimatedRevenueAvg"] == "123.45"


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
