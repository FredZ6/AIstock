"""Strict response envelope and registration shared by the three MCP servers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMcpSettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import create_engine
from stock_platform.application.market_data.repositories import (
    EngineMarketDataRepository,
    PointInTimeRepository,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse, ProviderStatus
from stock_platform.settings import Settings

FastMcpSettings.model_rebuild()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceMetadata(StrictModel):
    provider: str
    raw_object_keys: list[str]
    content_hashes: list[str]


class Citation(StrictModel):
    provider: str
    raw_object_key: str
    content_hash: str
    event_time: datetime
    available_at: datetime


class ResearchToolEnvelope(StrictModel):
    status: Literal["ok", "not_found", "not_supported", "unavailable", "error"]
    provider: str
    query_as_of: datetime
    data_as_of: datetime | None
    available_at: datetime | None
    feed: str
    is_delayed: bool
    freshness: dict[str, int] | None
    quality_flags: list[str]
    missingness: str | None
    records: list[dict[str, Any]]
    source: SourceMetadata
    citations: list[Citation]
    warnings: list[str]
    pagination: dict[str, str | None]
    trace_id: str

    @field_validator("query_as_of", "data_as_of", "available_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware(value)


class McpResearchService:
    def __init__(self, repository: PointInTimeRepository) -> None:
        self._repository = repository

    def query(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ResearchToolEnvelope:
        normalized_symbol = Symbol(symbol)
        query_as_of = require_aware(as_of)
        try:
            response = self._repository.as_of(
                symbol=str(normalized_symbol),
                feed_type=feed_type,
                decision_time=query_as_of,
            )
        except Exception:
            response = ProviderResponse(
                status=ProviderStatus.ERROR,
                provider="REDACTED",
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                warnings=("repository_error",),
                missingness="UNAVAILABLE",
            )
        records = list(response.records)
        data_as_of = max((record.event_time for record in records), default=None)
        available_at = max((record.available_at for record in records), default=None)
        freshness = (
            {"age_seconds": max(0, int((query_as_of - available_at).total_seconds()))}
            if available_at is not None
            else None
        )
        citations = [
            Citation(
                provider=record.provider,
                raw_object_key=record.raw_object_key,
                content_hash=record.content_hash,
                event_time=record.event_time,
                available_at=record.available_at,
            )
            for record in records
        ]
        return ResearchToolEnvelope(
            status=response.status.value,
            provider=response.provider,
            query_as_of=query_as_of,
            data_as_of=data_as_of,
            available_at=available_at,
            feed=feed_type.value,
            is_delayed=any(record.is_delayed for record in records),
            freshness=freshness,
            quality_flags=sorted({flag for record in records for flag in record.quality_flags}),
            missingness=response.missingness,
            records=[record.payload for record in records],
            source=SourceMetadata(
                provider=response.provider,
                raw_object_keys=[record.raw_object_key for record in records],
                content_hashes=[record.content_hash for record in records],
            ),
            citations=citations,
            warnings=list(response.warnings),
            pagination={"next_cursor": None},
            trace_id=response.trace_id or uuid4().hex,
        )


@lru_cache(maxsize=1)
def default_repository() -> EngineMarketDataRepository:
    return EngineMarketDataRepository(create_engine(Settings().database_url))


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def create_read_only_server(
    name: str,
    tools: dict[str, str],
    repository: PointInTimeRepository | None = None,
) -> FastMCP:
    server = FastMCP(
        name,
        instructions="Read-only point-in-time stock research. No trading or mutations.",
        stateless_http=True,
        json_response=True,
    )
    service = McpResearchService(repository or default_repository())

    def handler(feed_type: FeedType) -> Callable[[str, datetime], ResearchToolEnvelope]:
        def query(symbol: str, as_of: datetime) -> ResearchToolEnvelope:
            """Read normalized research data visible at the requested point in time."""

            return service.query(feed_type, symbol, as_of)

        return query

    for tool_name, feed_name in tools.items():
        server.add_tool(
            handler(FeedType(feed_name)),
            name=tool_name,
            annotations=READ_ONLY,
        )
        # ponytail: MCP SDK v1 has no public strict-extra switch; remove when v2 exposes one.
        registered = server._tool_manager.get_tool(tool_name)
        if registered is None:
            raise RuntimeError(f"failed to register MCP tool: {tool_name}")
        registered.parameters["additionalProperties"] = False
        registered.fn_metadata.arg_model.model_config["extra"] = "forbid"
        registered.fn_metadata.arg_model.model_rebuild(force=True)
    return server
