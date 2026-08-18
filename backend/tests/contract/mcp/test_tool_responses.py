from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
)
from stock_platform.mcp_servers.common import McpResearchService
from stock_platform.mcp_servers.market_research.server import create_server as create_market_server

AS_OF = datetime(2026, 8, 16, 12, tzinfo=UTC)


class StubRepository:
    def as_of(
        self, *, symbol: str, feed_type: FeedType, decision_time: datetime
    ) -> ProviderResponse:
        record = ProviderRecord(
            symbol=Symbol(symbol),
            feed_type=feed_type,
            provider="FIXTURE",
            event_time=AS_OF - timedelta(minutes=10),
            available_at=AS_OF - timedelta(minutes=5),
            ingested_at=AS_OF - timedelta(minutes=4),
            content_hash="a" * 64,
            raw_object_key="m1-v1/fixture/record.json",
            payload={
                "timeframe": "1d",
                "open": "120.00",
                "high": "125.00",
                "low": "119.00",
                "close": "123.45",
                "volume": "1000",
            },
        )
        return ProviderResponse(
            status=ProviderStatus.OK,
            provider="FIXTURE",
            feed_type=feed_type,
            symbol=Symbol(symbol),
            query_as_of=decision_time,
            records=(record,),
        )


def test_common_envelope_preserves_lineage_freshness_and_trace() -> None:
    result = McpResearchService(StubRepository()).query(FeedType.PRICE_BARS, "NVDA", AS_OF)

    assert result.status == "ok"
    assert result.query_as_of == AS_OF
    assert result.data_as_of == AS_OF - timedelta(minutes=10)
    assert result.available_at == AS_OF - timedelta(minutes=5)
    assert result.freshness is not None
    assert result.freshness.age_seconds == 300
    assert result.records[0].close == "123.45"  # type: ignore[union-attr]
    assert result.source.content_hashes == ["a" * 64]
    assert result.source.raw_object_keys == ["m1-v1/fixture/record.json"]
    assert result.citations[0].content_hash == "a" * 64
    assert len(result.trace_id) == 32


def test_repository_errors_are_redacted() -> None:
    class FailingRepository:
        def as_of(self, **kwargs: object) -> ProviderResponse:
            raise RuntimeError("secret=should-never-leak")

    result = McpResearchService(FailingRepository()).query(FeedType.COMPANY_FACTS, "NVDA", AS_OF)

    serialized = result.model_dump_json()
    assert result.status == "error"
    assert result.warnings == ["repository_error"]
    assert "should-never-leak" not in serialized


@pytest.mark.anyio
async def test_fastmcp_call_returns_structured_content() -> None:
    content, structured = cast(
        tuple[list[object], dict[str, Any]],
        await create_market_server(StubRepository()).call_tool(
            "get_price_bars",
            {"symbol": "NVDA", "as_of": "2026-08-16T12:00:00Z"},
        ),
    )

    assert content
    assert structured["status"] == "ok"
    assert structured["feed"] == "price_bars"
    assert structured["records"][0]["close"] == "123.45"
