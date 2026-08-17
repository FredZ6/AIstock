import os
from datetime import UTC, datetime

import pytest
from stock_platform.infrastructure.providers.alpaca import AlpacaProvider
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse, ProviderStatus
from stock_platform.infrastructure.providers.fmp import FmpProvider
from stock_platform.infrastructure.providers.sec import SecProvider

pytestmark = pytest.mark.live


class MemoryRawStore:
    def __init__(self) -> None:
        self.count = 0

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.count += 1


def require_live() -> None:
    if os.getenv("LIVE_PROVIDER_TESTS") != "1":
        pytest.skip("LIVE_PROVIDER_TESTS=1 is not set")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"missing requirement: {name}")
    return value


def assert_live_result(result: ProviderResponse, store: MemoryRawStore) -> None:
    if result.status is ProviderStatus.UNAVAILABLE and "provider_unavailable" in result.warnings:
        pytest.skip("missing requirement: provider network access")
    assert result.status in {ProviderStatus.OK, ProviderStatus.NOT_FOUND}
    if result.status is ProviderStatus.OK:
        assert store.count == 1


def test_sec_live_contract() -> None:
    require_live()
    store = MemoryRawStore()
    result = SecProvider(user_agent=required_env("SEC_USER_AGENT"), raw_store=store).fetch(
        FeedType.COMPANY_FACTS, "NVDA", datetime.now(UTC)
    )
    assert_live_result(result, store)


def test_alpaca_live_contract() -> None:
    require_live()
    store = MemoryRawStore()
    result = AlpacaProvider(
        data_key=required_env("ALPACA_DATA_KEY"),
        data_secret=required_env("ALPACA_DATA_SECRET"),
        raw_store=store,
    ).fetch(FeedType.PRICE_BARS, "NVDA", datetime.now(UTC))
    assert_live_result(result, store)


def test_fmp_live_contract() -> None:
    require_live()
    store = MemoryRawStore()
    result = FmpProvider(api_key=required_env("FMP_API_KEY"), raw_store=store).fetch(
        FeedType.TARGET_CONSENSUS, "NVDA", datetime.now(UTC)
    )
    assert_live_result(result, store)
