from datetime import UTC, datetime
from pathlib import Path

import pytest
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore

FIXTURE_ROOT = Path(__file__).parents[4] / "evals" / "fixtures"
EXPECTED_SYMBOLS = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"}
EXPECTED_DATASETS = {"sec", "market", "news", "options", "analyst"}
EXPECTED_SCENARIOS = {
    "normal",
    "delayed",
    "missing",
    "conflicting_targets",
    "sec_filing",
    "split",
    "anomaly_window",
}


def test_fixture_catalog_is_complete_and_provenanced() -> None:
    catalog = FixtureCatalog.load(FIXTURE_ROOT)

    assert set(catalog.manifests) == EXPECTED_DATASETS
    assert catalog.symbols == EXPECTED_SYMBOLS
    assert EXPECTED_SCENARIOS <= catalog.scenarios

    for manifest in catalog.manifests.values():
        assert manifest.dataset_version == "m1-v1"
        assert manifest.license
        assert manifest.provenance
        assert manifest.records


def test_fixture_hashes_are_reproducible_and_verified() -> None:
    first = FixtureCatalog.load(FIXTURE_ROOT)
    second = FixtureCatalog.load(FIXTURE_ROOT)

    assert first.content_hashes == second.content_hashes
    assert all(len(value) == 64 for value in first.content_hashes)


def test_fixture_provider_is_point_in_time_and_rejects_naive_as_of() -> None:
    provider = FixtureCatalog.load(FIXTURE_ROOT).provider()
    before_late_news = datetime(2026, 8, 15, 13, 0, tzinfo=UTC)
    after_late_news = datetime(2026, 8, 15, 15, 0, tzinfo=UTC)

    before = provider.fetch(FeedType.COMPANY_NEWS, "NVDA", before_late_news)
    after = provider.fetch(FeedType.COMPANY_NEWS, "NVDA", after_late_news)

    assert all(record.available_at <= before_late_news for record in before.records)
    assert len(after.records) == len(before.records) + 1
    assert after.records[-1].payload["headline"] == "NVDA late fixture update"

    with pytest.raises(ValueError, match="timezone-aware"):
        provider.fetch(FeedType.COMPANY_NEWS, "NVDA", datetime(2026, 8, 15, 15, 0))


def test_fixture_provider_rejects_unknown_symbol_and_feed() -> None:
    provider = FixtureCatalog.load(FIXTURE_ROOT).provider()
    as_of = datetime(2026, 8, 16, tzinfo=UTC)

    assert provider.fetch(FeedType.PRICE_BARS, "TSLA", as_of).status.value == "not_found"
    assert provider.fetch(FeedType.OPTION_AGGREGATES, "AMZN", as_of).status.value == "unavailable"


def test_fixture_raw_payloads_are_written_to_versioned_object_keys() -> None:
    class FakeMinioClient:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def bucket_exists(self, bucket: str) -> bool:
            return True

        def make_bucket(self, bucket: str) -> None:
            raise AssertionError("existing fixture bucket must be reused")

        def put_object(
            self,
            bucket: str,
            object_key: str,
            stream: object,
            length: int,
            content_type: str,
        ) -> None:
            assert bucket == "fixture-raw"
            assert content_type == "application/json"
            self.objects[object_key] = stream.read(length)  # type: ignore[attr-defined]

    client = FakeMinioClient()
    store = MinioRawObjectStore(client=client, bucket="fixture-raw")
    catalog = FixtureCatalog.load(FIXTURE_ROOT)

    written = catalog.seed_object_store(store)

    assert written == len(client.objects)
    assert written > 0
    assert all(key.startswith("m1-v1/") for key in client.objects)
