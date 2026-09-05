from datetime import UTC, datetime
from pathlib import Path

import pytest
from stock_platform.application.ingestion.normalizers.sec import SecNormalizer
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import (
    FeedType,
    HttpRequest,
    HttpResponse,
    ProviderBatch,
    ProviderRateLimit,
    ProviderTransportError,
)
from stock_platform.infrastructure.providers.sec import (
    SecFilingRegime,
    SecIdentity,
    SecProvider,
    SecRequestLimiter,
    StaticSecIdentityResolver,
    allowed_sec_forms,
)

AS_OF = datetime(2026, 8, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "sec"


def test_missing_primary_document_reads_verified_complete_submission() -> None:
    requests: list[str] = []
    # Synthetic SGML transport response, not a recorded live filing.
    body = (
        b"<SEC-DOCUMENT>0001012870-00-006127.txt\n<SEC-HEADER>\n"
        b"ACCESSION NUMBER: 0001012870-00-006127\nCENTRAL INDEX KEY: 0001045810\n"
        b"</SEC-HEADER>\n<DOCUMENT>\n<FILENAME>0001.txt\n<TEXT>Test only</TEXT>\n"
        b"</DOCUMENT>\n</SEC-DOCUMENT>"
    )

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request.url)
        return HttpResponse(
            status_code=404 if len(requests) == 1 else 200,
            headers={"Content-Type": "text/plain"},
            body=b"missing" if len(requests) == 1 else body,
        )

    batch = SecProvider(
        user_agent="AIStock/0.2 research@example.com", transport=transport, clock=lambda: AS_OF
    ).fetch_filing_document(
        "NVDA", accession_number="0001012870-00-006127", primary_document="0001.txt", as_of=AS_OF
    )
    assert batch.body == body
    assert requests == [
        "https://www.sec.gov/Archives/edgar/data/1045810/000101287000006127/0001.txt",
        "https://www.sec.gov/Archives/edgar/data/1045810/0001012870-00-006127.txt",
    ]


def test_empty_historical_primary_document_reads_complete_submission_directly() -> None:
    requests: list[str] = []
    body = (
        b"<SEC-DOCUMENT>0001012870-00-003122.txt\n<SEC-HEADER>\n"
        b"ACCESSION NUMBER: 0001012870-00-003122\nCENTRAL INDEX KEY: 0001045810\n"
        b"</SEC-HEADER>\n</SEC-DOCUMENT>"
    )

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request.url)
        return HttpResponse(status_code=200, headers={"content-type": "text/plain"}, body=body)

    batch = SecProvider(
        user_agent="AIStock/0.2 research@example.com", transport=transport, clock=lambda: AS_OF
    ).fetch_filing_document(
        "NVDA", accession_number="0001012870-00-003122", primary_document="", as_of=AS_OF
    )
    assert batch.body == body
    assert requests == ["https://www.sec.gov/Archives/edgar/data/1045810/0001012870-00-003122.txt"]


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_primary_document_errors_do_not_trigger_alternate_fetch(status: int) -> None:
    requests: list[str] = []

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request.url)
        return HttpResponse(status_code=status, headers={}, body=b"error")

    with pytest.raises(ProviderTransportError) as caught:
        SecProvider(
            user_agent="AIStock/0.2 research@example.com", transport=transport
        ).fetch_filing_document(
            "NVDA",
            accession_number="0001012870-00-006127",
            primary_document="0001.txt",
            as_of=AS_OF,
        )
    assert caught.value.status_code == status
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Temporarily unavailable</html>",
        (
            b"<SEC-DOCUMENT>other.txt\n<SEC-HEADER>\nACCESSION NUMBER: 0001012870-00-006128\n"
            b"CENTRAL INDEX KEY: 0001045810\n</SEC-HEADER>\n</SEC-DOCUMENT>"
        ),
        (
            b"<SEC-DOCUMENT>0001012870-00-006127.txt\n<SEC-HEADER>\n"
            b"ACCESSION NUMBER: 0001012870-00-006127\nCENTRAL INDEX KEY: 0000320193\n"
            b"</SEC-HEADER>\n</SEC-DOCUMENT>"
        ),
    ],
)
def test_complete_submission_rejects_wrong_identity_or_error_page(body: bytes) -> None:
    calls = 0

    def transport(request: HttpRequest) -> HttpResponse:
        nonlocal calls
        calls += 1
        return HttpResponse(status_code=404 if calls == 1 else 200, headers={}, body=body)

    with pytest.raises(ProviderTransportError, match="SCHEMA_DRIFT"):
        SecProvider(
            user_agent="AIStock/0.2 research@example.com", transport=transport
        ).fetch_filing_document(
            "NVDA",
            accession_number="0001012870-00-006127",
            primary_document="0001.txt",
            as_of=AS_OF,
        )


@pytest.mark.parametrize(
    ("regime", "required", "forbidden"),
    [
        (
            SecFilingRegime.US_DOMESTIC,
            {"10-K", "10-Q", "8-K", "DEF 14A", "S-1", "424B4"},
            {"20-F", "6-K", "F-1"},
        ),
        (
            SecFilingRegime.FOREIGN_PRIVATE_ISSUER,
            {"20-F", "6-K", "F-1", "424B4"},
            {"10-K", "10-Q", "DEF 14A", "S-1"},
        ),
    ],
)
def test_filing_regime_selects_only_approved_forms(
    regime: SecFilingRegime,
    required: set[str],
    forbidden: set[str],
) -> None:
    forms = allowed_sec_forms(regime)
    assert required <= forms
    assert forms.isdisjoint(forbidden)


def test_sec_transport_uses_resolved_cik_required_identity_and_raw_batches() -> None:
    requests: list[HttpRequest] = []

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request)
        if request.url.endswith("CIK0001045810.json"):
            body = (FIXTURES / "submissions.json").read_bytes()
        elif request.url.endswith("CIK0001045810-submissions-001.json"):
            body = (FIXTURES / "CIK0001045810-submissions-001.json").read_bytes()
        else:
            body = (FIXTURES / "filing_document.html").read_bytes()
        return HttpResponse(status_code=200, headers={}, body=body)

    resolver = StaticSecIdentityResolver(
        {
            Symbol("NVDA"): SecIdentity(
                symbol=Symbol("NVDA"),
                cik="0001045810",
                regime=SecFilingRegime.US_DOMESTIC,
            )
        }
    )
    provider = SecProvider(
        user_agent="AIStock/0.1 research@example.com",
        identity_resolver=resolver,
        transport=transport,
        clock=lambda: AS_OF,
    )

    submission = provider.fetch_batch(FeedType.FILINGS, "NVDA", AS_OF)
    historical = provider.fetch_historical_submissions(
        "NVDA", file_name="CIK0001045810-submissions-001.json", as_of=AS_OF
    )
    document = provider.fetch_filing_document(
        "NVDA",
        accession_number="0001045810-26-000042",
        primary_document="nvda-20260731.htm",
        as_of=AS_OF,
    )

    assert submission.body == (FIXTURES / "submissions.json").read_bytes()
    assert historical.body == (FIXTURES / "CIK0001045810-submissions-001.json").read_bytes()
    assert document.body == (FIXTURES / "filing_document.html").read_bytes()
    assert requests[0].url.endswith("/submissions/CIK0001045810.json")
    assert requests[1].url.endswith("/submissions/CIK0001045810-submissions-001.json")
    assert requests[2].url.endswith(
        "/Archives/edgar/data/1045810/000104581026000042/nvda-20260731.htm"
    )
    assert all(request.method == "GET" for request in requests)
    assert all(
        request.headers["User-Agent"] == "AIStock/0.1 research@example.com" for request in requests
    )


@pytest.mark.parametrize(
    "user_agent", [None, "", "research@example.com", "AIStock research@example.com"]
)
def test_sec_requires_application_version_and_contact(user_agent: str | None) -> None:
    provider = SecProvider(
        user_agent=user_agent,
        identity_resolver=StaticSecIdentityResolver({}),
    )
    assert not provider.configured


def test_default_sec_identity_resolver_rejects_queries_before_seed_availability() -> None:
    provider = SecProvider(
        user_agent="AIStock/0.1 research@example.com",
        transport=lambda request: pytest.fail(f"unexpected request: {request.url}"),
        clock=lambda: AS_OF,
    )

    with pytest.raises(ValueError, match="unknown SEC Security identity"):
        provider.fetch_batch(FeedType.FILINGS, "NVDA", datetime(2026, 8, 22, tzinfo=UTC))


def test_sec_global_limiter_never_admits_more_than_five_requests_per_second() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = SecRequestLimiter(clock=lambda: now[0], sleep=sleep, requests_per_second=5)
    for _ in range(6):
        limiter.acquire()

    assert sleeps == [pytest.approx(1.0)]


def test_sec_submission_normalizer_preserves_acceptance_and_amendment_versions() -> None:
    identity = SecIdentity(
        symbol=Symbol("NVDA"),
        cik="1045810",
        regime=SecFilingRegime.US_DOMESTIC,
    )
    batch = ProviderBatch(
        provider="SEC",
        feed_type=FeedType.FILINGS,
        symbol=identity.symbol,
        query_as_of=AS_OF,
        observed_at=AS_OF,
        body=(FIXTURES / "submissions.json").read_bytes(),
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )

    result = SecNormalizer().normalize_submissions(batch, identity=identity)

    assert result.historical_submission_files == ("CIK0001045810-submissions-001.json",)
    assert [filing.accession_number for filing in result.filings] == [
        "0001045810-26-000042",
        "0001045810-26-000043",
    ]
    assert result.filings[0].available_at == datetime(2026, 8, 20, 16, 1, 2, tzinfo=UTC)
    assert not result.filings[0].is_amendment
    assert result.filings[1].is_amendment
    assert result.filings[1].base_form == "10-Q"


def test_sec_normalizer_reads_historical_pages_and_company_facts() -> None:
    identity = SecIdentity(
        symbol=Symbol("NVDA"),
        cik="1045810",
        regime=SecFilingRegime.US_DOMESTIC,
    )
    historical = ProviderBatch(
        provider="SEC",
        feed_type=FeedType.FILINGS,
        symbol=identity.symbol,
        query_as_of=AS_OF,
        observed_at=AS_OF,
        body=(FIXTURES / "CIK0001045810-submissions-001.json").read_bytes(),
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )
    company_facts = ProviderBatch(
        provider="SEC",
        feed_type=FeedType.COMPANY_FACTS,
        symbol=identity.symbol,
        query_as_of=AS_OF,
        observed_at=AS_OF,
        body=(FIXTURES / "companyfacts.json").read_bytes(),
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )

    filings = SecNormalizer().normalize_historical_submissions(historical, identity=identity)
    facts = SecNormalizer().normalize_company_facts(company_facts, identity=identity)

    assert [item.accession_number for item in filings] == ["0001045810-25-000010"]
    assert len(facts) == 3
    assert facts[0].concept == "Revenues"
    assert str(facts[0].value) == "44000000000"


def test_sec_submission_normalizer_rejects_parallel_array_schema_drift() -> None:
    identity = SecIdentity(
        symbol=Symbol("NVDA"),
        cik="1045810",
        regime=SecFilingRegime.US_DOMESTIC,
    )
    batch = ProviderBatch(
        provider="SEC",
        feed_type=FeedType.FILINGS,
        symbol=identity.symbol,
        query_as_of=AS_OF,
        observed_at=AS_OF,
        body=b'{"filings":{"recent":{"accessionNumber":["x"],"form":[]}}}',
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )

    with pytest.raises(ValueError, match="parallel arrays"):
        SecNormalizer().normalize_submissions(batch, identity=identity)
