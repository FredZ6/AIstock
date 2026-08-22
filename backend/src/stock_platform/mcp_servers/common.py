"""Strict response envelope and registration shared by the three MCP servers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMcpSettings
from mcp.types import ContentBlock, ToolAnnotations
from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, field_validator
from sqlalchemy import Connection, Engine, create_engine, insert

from stock_platform.application.market_data.repositories import (
    EngineMarketDataRepository,
    PointInTimeRepository,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import agent_event, tool_call
from stock_platform.infrastructure.observability.context import maybe_current_correlation
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse, ProviderStatus
from stock_platform.settings import Settings

FastMcpSettings.model_rebuild()
SymbolInput = Annotated[str, StringConstraints(pattern=r"^[A-Z.]{1,10}$")]


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


class CompanyFactsRecord(StrictModel):
    fiscal_period: str
    revenue: str
    currency: str


class FilingRecord(StrictModel):
    accession: str
    form: str
    filed_date: str


class FilingSectionRecord(StrictModel):
    accession: str
    section: str
    text: str


class DailyPriceBarRecord(StrictModel):
    timeframe: Literal["1d"]
    open: str
    high: str
    low: str
    close: str
    volume: str


class SplitActionRecord(StrictModel):
    timeframe: Literal["corporate_action"]
    split_ratio: str
    close: str


class CompanyNewsRecord(StrictModel):
    headline: str
    summary: str


class OptionAggregateRecord(StrictModel):
    put_call_volume_ratio: str
    implied_volatility: str


class EstimateRecord(StrictModel):
    period: str
    revenue_estimate: str
    currency: str


class TargetConsensusRecord(StrictModel):
    source_provider: str
    median_target: str
    currency: str


ResearchRecord = (
    CompanyFactsRecord
    | FilingRecord
    | FilingSectionRecord
    | DailyPriceBarRecord
    | SplitActionRecord
    | CompanyNewsRecord
    | OptionAggregateRecord
    | EstimateRecord
    | TargetConsensusRecord
)
RESEARCH_RECORD_ADAPTER: TypeAdapter[ResearchRecord] = TypeAdapter(ResearchRecord)
Missingness = Literal["UNKNOWN", "MISSING", "UNAVAILABLE", "CONFLICTED"]


class Freshness(StrictModel):
    age_seconds: int


class Pagination(StrictModel):
    next_cursor: str | None


class ResearchToolEnvelope(StrictModel):
    status: Literal["ok", "not_found", "not_supported", "unavailable", "error"]
    provider: str
    query_as_of: datetime
    data_as_of: datetime | None
    available_at: datetime | None
    feed: FeedType
    is_delayed: bool
    freshness: Freshness | None
    quality_flags: list[str]
    missingness: Missingness | None
    records: list[ResearchRecord]
    source: SourceMetadata
    citations: list[Citation]
    warnings: list[str]
    pagination: Pagination
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
            Freshness(age_seconds=max(0, int((query_as_of - available_at).total_seconds())))
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
        missingness = cast(Missingness | None, response.missingness)
        return ResearchToolEnvelope(
            status=response.status.value,
            provider=response.provider,
            query_as_of=query_as_of,
            data_as_of=data_as_of,
            available_at=available_at,
            feed=feed_type,
            is_delayed=any(record.is_delayed for record in records),
            freshness=freshness,
            quality_flags=sorted({flag for record in records for flag in record.quality_flags}),
            missingness=missingness,
            records=[RESEARCH_RECORD_ADAPTER.validate_python(record.payload) for record in records],
            source=SourceMetadata(
                provider=response.provider,
                raw_object_keys=[record.raw_object_key for record in records],
                content_hashes=[record.content_hash for record in records],
            ),
            citations=citations,
            warnings=list(response.warnings),
            pagination=Pagination(next_cursor=None),
            trace_id=response.trace_id or uuid4().hex,
        )


@lru_cache(maxsize=1)
def default_repository() -> EngineMarketDataRepository:
    return EngineMarketDataRepository(create_engine(Settings().database_url))


AuditOutcome = Literal["completed", "denied"]


class McpAuditSink(Protocol):
    def record(
        self,
        tool_name: str,
        request_fingerprint: str,
        outcome: AuditOutcome,
    ) -> None: ...


class PostgresMcpAuditSink:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(
        self,
        tool_name: str,
        request_fingerprint: str,
        outcome: AuditOutcome,
    ) -> None:
        context = maybe_current_correlation()
        correlation_id = context.correlation_id if context is not None else uuid4()
        self._connection.execute(
            insert(tool_call).values(
                correlation_id=correlation_id,
                tool_name=tool_name,
                request_fingerprint=request_fingerprint,
            )
        )
        self._connection.execute(
            insert(agent_event).values(
                correlation_id=correlation_id,
                event_type=f"mcp.tool.{outcome}",
                payload={
                    "tool_name": tool_name,
                    "request_fingerprint": request_fingerprint,
                    "outcome": outcome,
                },
            )
        )


class EngineMcpAuditSink:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        tool_name: str,
        request_fingerprint: str,
        outcome: AuditOutcome,
    ) -> None:
        with self._engine.begin() as connection:
            PostgresMcpAuditSink(connection).record(tool_name, request_fingerprint, outcome)


@lru_cache(maxsize=1)
def default_audit_sink() -> EngineMcpAuditSink:
    return EngineMcpAuditSink(create_engine(Settings().database_url))


def request_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{tool_name}\0{canonical}".encode()).hexdigest()


class AuditedFastMCP(FastMCP):
    def __init__(self, *args: Any, audit_sink: McpAuditSink, **kwargs: Any) -> None:
        self._audit_sink = audit_sink
        super().__init__(*args, **kwargs)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        fingerprint = request_fingerprint(name, arguments)
        try:
            result = await super().call_tool(name, arguments)
        except Exception:
            self._audit_sink.record(name, fingerprint, "denied")
            raise
        self._audit_sink.record(name, fingerprint, "completed")
        return result


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
    audit_sink: McpAuditSink | None = None,
) -> FastMCP:
    server = AuditedFastMCP(
        name,
        audit_sink=audit_sink or default_audit_sink(),
        instructions="Read-only point-in-time stock research. No trading or mutations.",
        stateless_http=True,
        json_response=True,
    )
    service = McpResearchService(repository or default_repository())

    def handler(feed_type: FeedType) -> Callable[[SymbolInput, datetime], ResearchToolEnvelope]:
        def query(symbol: SymbolInput, as_of: datetime) -> ResearchToolEnvelope:
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
