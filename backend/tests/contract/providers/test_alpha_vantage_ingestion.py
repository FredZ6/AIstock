import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from stock_platform.application.ingestion.normalizers.alpha_vantage import AlphaVantageNormalizer
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.providers.alpha_vantage import AlphaVantageProvider
from stock_platform.infrastructure.providers.base import (
    HttpRequest,
    HttpResponse,
    ProviderBatch,
    ProviderRateLimit,
)

AS_OF = datetime(2026, 8, 26, 12, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "alpha_vantage" / "earnings_calendar.csv"


def _batch() -> ProviderBatch:
    return ProviderBatch(
        provider="ALPHA_VANTAGE",
        feed_type=FeedType.EARNINGS_CALENDAR,
        symbol=Symbol("NVDA"),
        query_as_of=AS_OF,
        observed_at=AS_OF,
        body=FIXTURE.read_bytes(),
        headers={"Content-Type": "text/csv"},
        next_page_token=None,
        rate_limit=ProviderRateLimit(limit=25, remaining=24),
    )


def test_alpha_calendar_transport_fetches_one_full_csv_snapshot_read_only() -> None:
    requests: list[HttpRequest] = []

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request)
        return HttpResponse(
            status_code=200, headers={"Content-Type": "text/csv"}, body=FIXTURE.read_bytes()
        )

    provider = AlphaVantageProvider(api_key="fixture-key", transport=transport, clock=lambda: AS_OF)
    batch = provider.fetch_batch(FeedType.EARNINGS_CALENDAR, "NVDA", AS_OF)

    assert batch.body == FIXTURE.read_bytes()
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert "function=EARNINGS_CALENDAR" in requests[0].url
    assert "horizon=12month" in requests[0].url


def test_alpha_provider_is_explicitly_unconfigured_without_credentials() -> None:
    assert not AlphaVantageProvider(api_key=None).configured


@pytest.mark.live
def test_alpha_live_contract() -> None:
    if os.getenv("LIVE_PROVIDER_TESTS") != "1":
        pytest.skip("LIVE_PROVIDER_TESTS=1 is not set")
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        pytest.skip("missing requirement: ALPHA_VANTAGE_API_KEY")

    batch = AlphaVantageProvider(api_key=api_key).fetch_batch(
        FeedType.EARNINGS_CALENDAR, "NVDA", datetime.now(UTC)
    )

    assert batch.provider == "ALPHA_VANTAGE"
    assert batch.body


def test_alpha_calendar_filters_watchlist_resolves_aliases_and_uses_decimal() -> None:
    events = AlphaVantageNormalizer().normalize_calendar(
        _batch(),
        provider_to_canonical={"NVDA": "NVDA", "TSM": "TSM", "NVDA.US": "NVDA"},
    )

    assert [str(event.symbol) for event in events] == ["NVDA", "TSM"]
    assert events[0].estimate == Decimal("1.2345")
    assert isinstance(events[0].estimate, Decimal)
    assert events[0].available_at == AS_OF
    assert events[0].provider_symbol == "NVDA"


def test_alpha_calendar_rejects_duplicate_rows_with_conflicting_dates() -> None:
    duplicate = _batch()
    duplicate = ProviderBatch(
        provider=duplicate.provider,
        feed_type=duplicate.feed_type,
        symbol=duplicate.symbol,
        query_as_of=duplicate.query_as_of,
        observed_at=duplicate.observed_at,
        body=(
            b"symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
            b"NVDA,NVIDIA,2026-11-19,2026-10-31,1.2,USD\n"
            b"NVDA,NVIDIA,2026-11-20,2026-10-31,1.2,USD\n"
        ),
        headers=duplicate.headers,
        next_page_token=None,
        rate_limit=duplicate.rate_limit,
    )

    try:
        AlphaVantageNormalizer().normalize_calendar(
            duplicate,
            provider_to_canonical={"NVDA": "NVDA"},
        )
    except ValueError as error:
        assert "conflicting earnings rows" in str(error)
    else:
        raise AssertionError("conflicting rows must be rejected")
