from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import Connection, and_, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoResultFound

from stock_platform.api.dependencies import get_connection, get_human_actor, get_settings
from stock_platform.api.schemas.errors import ApiError
from stock_platform.api.schemas.rest import (
    AlertPage,
    DataQualityResponse,
    EvalRunDetail,
    EvalRunPage,
    HumanAction,
    MarketDataResponse,
    PaperFillPage,
    PaperOrderPage,
    PortfolioInitializationRequest,
    PortfolioInitializationResponse,
    PortfolioResponse,
    PortfolioRunRequest,
    ProviderHealthResponse,
    ResearchPage,
    ResearchRunReportResponse,
    ResearchRunRequest,
    RunResponse,
    WatchlistPatch,
    WatchlistRequest,
    WeeklyReviewDetail,
    WeeklyReviewPage,
)
from stock_platform.application.learning.approval import LessonNotFound, record_lesson_decision
from stock_platform.application.learning.promotion import (
    HumanActor,
    PolicyPromotionForbidden,
    PolicyPromotionService,
    PostgresPolicyRepository,
    VersionConflict,
)
from stock_platform.application.market_data.policy import (
    PolicyOutcome,
    admission_payload,
    paper_market_data_admission,
)
from stock_platform.application.market_data.quality import QualityPolicy
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    initial_funding,
)
from stock_platform.application.portfolio.read_model import PositionFill, build_positions
from stock_platform.application.research.supersession import decision_is_active_at
from stock_platform.application.runs import (
    IdempotencyConflict,
    RunAdmissionLimit,
    admit_run,
    append_run_event,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    alert_event,
    candidate_lesson,
    cash_ledger,
    claim,
    confidence_policy_version,
    data_quality_observation,
    decision_diff,
    decision_outcome,
    decision_snapshot,
    derived_metric,
    earnings_event,
    error_attribution,
    eval_metric,
    eval_run,
    evidence_gap,
    evidence_item,
    execution_policy_version,
    financial_fact,
    ingestion_job,
    investment_thesis,
    lesson_approval,
    lesson_attribution_link,
    market_bar,
    news_article,
    normalized_record,
    option_snapshot,
    paper_fill,
    paper_order,
    paper_portfolio_config,
    portfolio_initialization_request,
    portfolio_nav,
    raw_data_object,
    regression_gate_result,
    replay_run,
    research_opinion,
    research_scoring_policy_version,
    risk_decision,
    risk_policy_version,
    sec_filing,
    security,
    security_identifier_version,
    thesis_evidence_link,
    watchlist_item,
    weekly_review_run,
)
from stock_platform.infrastructure.observability.context import current_correlation
from stock_platform.settings import Settings

router = APIRouter(prefix="/api/v1")
_DATA_QUALITY_POLICY = QualityPolicy.load(
    Path(__file__).parents[4] / "config" / "data_quality_v1.yaml"
)
ConnectionDependency = Annotated[Connection, Depends(get_connection)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ActorDependency = Annotated[HumanActor, Depends(get_human_actor)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


def _value(value: Any) -> Any:
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _row(row: Any) -> dict[str, Any]:
    return cast(dict[str, Any], _value(dict(row)))


def _symbol(value: str) -> str:
    try:
        return str(Symbol(value))
    except ValueError as exception:
        raise ApiError(422, "INVALID_REQUEST", str(exception)) from exception


def _aware_query_time(value: datetime, field: str) -> datetime:
    try:
        return require_aware(value).astimezone(UTC)
    except ValueError as exception:
        raise ApiError(422, "INVALID_REQUEST", f"{field} must include a timezone") from exception


def _encode_cursor(sort_time: datetime, row_id: UUID) -> str:
    payload = f"{sort_time.astimezone(UTC).isoformat()}|{row_id}".encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        timestamp, row_id = urlsafe_b64decode(padded).decode().split("|", 1)
        return _aware_query_time(datetime.fromisoformat(timestamp), "cursor"), UUID(row_id)
    except (Base64Error, UnicodeDecodeError, ValueError) as exception:
        raise ApiError(422, "INVALID_REQUEST", "cursor is invalid") from exception


def _cursor_filter(sort_column: Any, id_column: Any, cursor: str | None) -> Any:
    if cursor is None:
        return True
    sort_time, row_id = _decode_cursor(cursor)
    return or_(sort_column < sort_time, and_(sort_column == sort_time, id_column < row_id))


def _page(
    rows: Sequence[Any], limit: int, sort_key: str
) -> tuple[list[dict[str, Any]], str | None]:
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit and visible:
        last = visible[-1]
        next_cursor = _encode_cursor(last[sort_key], last["id"])
    return [_row(row) for row in visible], next_cursor


def _coverage(settings: Settings) -> MarketDataCoverage:
    configured = settings.alpaca_entitlement_coverage or ""
    return (
        MarketDataCoverage.SIP if "SIP" in configured.upper().split(",") else MarketDataCoverage.IEX
    )


def _market_record(record: Any) -> dict[str, Any]:
    payload = record.payload
    return cast(
        dict[str, Any],
        _value(
            {
                "symbol": str(record.symbol),
                "provider": record.provider,
                "feed_type": record.feed_type.value,
                "event_time": record.event_time,
                "available_at": record.available_at,
                "ingested_at": record.ingested_at,
                "content_hash": record.content_hash,
                "raw_object_key": record.raw_object_key,
                "timeframe": payload["timeframe"],
                "open": payload["open"],
                "high": payload["high"],
                "low": payload["low"],
                "close": payload["close"],
                "volume": payload["volume"],
                "coverage": payload["coverage"],
                "session": payload["session"],
                "conflict": payload["conflict"],
            }
        ),
    )


def _read_status(items: list[dict[str, Any]]) -> Literal["SUCCESS", "DEGRADED", "FAILURE"]:
    if not items:
        return "FAILURE"
    if any(bool(item.get("conflict")) for item in items):
        return "DEGRADED"
    return "SUCCESS"


_WATCHLIST_PUBLIC_COLUMNS = (
    watchlist_item.c.symbol,
    watchlist_item.c.daily_research,
    watchlist_item.c.intraday_monitoring,
    watchlist_item.c.thresholds,
    watchlist_item.c.updated_at,
    watchlist_item.c.created_at,
)


def _security_id_for_symbol(connection: Connection, symbol: str) -> UUID:
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:symbol))"), {"symbol": symbol})
    existing = connection.execute(
        select(security_identifier_version.c.security_id)
        .where(
            security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL",
            security_identifier_version.c.identifier_value == symbol,
        )
        .order_by(security_identifier_version.c.available_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return cast(UUID, existing)
    now = datetime.now(UTC)
    security_id = connection.execute(
        insert(security).values(instrument_type="COMMON_STOCK").returning(security.c.id)
    ).scalar_one()
    connection.execute(
        insert(security_identifier_version).values(
            security_id=security_id,
            identifier_type="PRIMARY_SYMBOL",
            identifier_value=symbol,
            provider_identifiers={},
            effective_from=now,
            available_at=now,
        )
    )
    return cast(UUID, security_id)


def _run_response(row: Any) -> RunResponse:
    return RunResponse(
        run_id=row["id"],
        run_type=row["run_type"],
        status=row["status"],
        symbol=row["symbol"],
        decision_time=row["decision_time"],
        data_cutoff=row["data_cutoff"],
    )


def _create_run(
    connection: Connection,
    settings: Settings,
    response: Response,
    *,
    run_type: Literal["RESEARCH", "PORTFOLIO"],
    idempotency_key: str,
    payload: dict[str, Any],
    symbol: str | None,
    decision_time: datetime,
    data_cutoff: datetime,
) -> RunResponse:
    try:
        admitted = admit_run(
            connection,
            max_active_runs=settings.max_active_agent_runs,
            run_type=run_type,
            idempotency_key=idempotency_key,
            payload=payload,
            symbol=symbol,
            decision_time=decision_time,
            data_cutoff=data_cutoff,
            correlation_id=current_correlation().correlation_id,
        )
    except IdempotencyConflict as exception:
        raise ApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "Idempotency key was already used for a different request",
        ) from exception
    except RunAdmissionLimit as exception:
        raise ApiError(
            429, "TASK_ADMISSION_LIMIT", "Active agent run limit reached", retryable=True
        ) from exception
    response.headers["Idempotency-Replayed"] = str(admitted.replayed).lower()
    return RunResponse(
        run_id=admitted.id,
        run_type=cast(Literal["RESEARCH", "PORTFOLIO"], admitted.run_type),
        status=cast(Any, admitted.status),
        symbol=admitted.symbol,
        decision_time=admitted.decision_time,
        data_cutoff=admitted.data_cutoff,
    )


@router.get("/providers/health", response_model=ProviderHealthResponse)
def provider_health(
    settings: SettingsDependency, connection: ConnectionDependency
) -> dict[str, Any]:
    coverage = _coverage(settings)
    ranked_quality = (
        select(
            data_quality_observation.c.status,
            data_quality_observation.c.observed_at,
            func.dense_rank()
            .over(
                partition_by=data_quality_observation.c.dimension,
                order_by=data_quality_observation.c.observed_at.desc(),
            )
            .label("rank"),
        )
        .where(
            data_quality_observation.c.provider == "ALPACA",
            data_quality_observation.c.dataset == "price_bars",
            data_quality_observation.c.coverage == coverage.value,
        )
        .subquery()
    )
    latest_quality = (
        connection.execute(
            select(ranked_quality.c.status, ranked_quality.c.observed_at).where(
                ranked_quality.c.rank == 1
            )
        )
        .mappings()
        .all()
    )
    quality_priority = {"PASS": 0, "DEGRADED": 1, "UNAVAILABLE": 2, "FAIL": 3}
    latest_quality_status = (
        max((row["status"] for row in latest_quality), key=quality_priority.__getitem__)
        if latest_quality
        else None
    )
    latest_job = connection.execute(
        select(ingestion_job.c.state)
        .where(
            ingestion_job.c.provider == "ALPACA",
            ingestion_job.c.dataset == "price_bars",
            ingestion_job.c.request_payload["request"]["coverage"].astext == coverage.value,
        )
        .order_by(ingestion_job.c.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    alpaca_configured = bool(settings.alpaca_data_key and settings.alpaca_data_secret)
    quality_age = (
        datetime.now(UTC) - min(row["observed_at"] for row in latest_quality)
        if latest_quality
        else None
    )
    degraded_after, unavailable_after = _DATA_QUALITY_POLICY.thresholds("ALPACA", "price_bars")
    if not alpaca_configured:
        alpaca_status = "UNAVAILABLE"
    elif latest_quality_status in {"FAIL", "UNAVAILABLE"} or latest_job in {
        "FAILED",
        "DEAD_LETTER",
    }:
        alpaca_status = "FAILURE"
    elif quality_age is None or quality_age >= unavailable_after:
        alpaca_status = "FAILURE"
    elif (
        quality_age >= degraded_after
        or latest_quality_status == "DEGRADED"
        or latest_job in {"QUEUED", "RUNNING", "RETRY_SCHEDULED", "COMPLETED_WITH_GAPS"}
    ):
        alpaca_status = "DEGRADED"
    elif latest_quality_status == "PASS" and latest_job in {None, "SUCCEEDED"}:
        alpaca_status = "SUCCESS"
    else:
        alpaca_status = "DEGRADED"
    return {
        "mode": settings.environment,
        "providers": {
            "sec": {
                "configured": bool(settings.sec_user_agent),
                "mode": "read_only" if settings.sec_user_agent else "unavailable",
                "operator_action": (
                    None
                    if settings.sec_user_agent
                    else "Configure SEC_USER_AGENT with a monitored contact identity."
                ),
            },
            "alpaca": {
                "configured": alpaca_configured,
                "mode": "read_only" if alpaca_configured else "unavailable",
                "status": alpaca_status,
                "coverage": settings.alpaca_entitlement_coverage,
                "latest_job_state": latest_job,
                "latest_quality_status": latest_quality_status,
                "operator_action": (
                    None
                    if alpaca_configured
                    else (
                        "Configure ALPACA_DATA_KEY and ALPACA_DATA_SECRET "
                        "for read-only market data."
                    )
                ),
            },
            "alpha_vantage": {
                "configured": bool(settings.alpha_vantage_api_key),
                "mode": "read_only" if settings.alpha_vantage_api_key else "unavailable",
                "operator_action": (
                    None
                    if settings.alpha_vantage_api_key
                    else "Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar."
                ),
            },
        },
    }


@router.get("/market-data/quotes", response_model=MarketDataResponse)
def latest_quotes(
    connection: ConnectionDependency,
    settings: SettingsDependency,
    symbols: Annotated[str, Query(min_length=1)],
    decision_time: datetime,
    timeframe: Literal["1Min", "1Day"] = "1Day",
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    requested = tuple(
        dict.fromkeys(_symbol(item.strip()) for item in symbols.split(",") if item.strip())
    )
    if not requested:
        raise ApiError(422, "INVALID_REQUEST", "symbols must contain at least one symbol")
    if len(requested) > 50:
        raise ApiError(422, "INVALID_REQUEST", "symbols cannot contain more than 50 entries")
    records = PostgresMarketDataRepository(connection).latest_bars_as_of(
        symbols=requested,
        decision_time=cutoff,
        coverage=_coverage(settings),
        session=MarketSession.REGULAR,
        timeframe=timeframe,
    )
    record_by_symbol = {str(record.symbol): record for record in records}
    items = [
        _market_record(record_by_symbol[symbol])
        for symbol in requested
        if symbol in record_by_symbol
    ]
    missing_symbols = [symbol for symbol in requested if symbol not in record_by_symbol]
    status = _read_status(items)
    if items and missing_symbols:
        status = "DEGRADED"
    return {
        "status": status,
        "decision_time": cutoff,
        "missing_symbols": missing_symbols,
        "items": items,
    }


@router.get("/market-data/bars/{symbol}", response_model=MarketDataResponse)
def historical_bars(
    symbol: str,
    connection: ConnectionDependency,
    settings: SettingsDependency,
    start: datetime,
    end: datetime,
    decision_time: datetime,
    timeframe: Literal["1Min", "1Day"],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict[str, Any]:
    normalized_symbol = _symbol(symbol)
    start_at = _aware_query_time(start, "start")
    end_at = _aware_query_time(end, "end")
    cutoff = _aware_query_time(decision_time, "decision_time")
    if start_at > end_at:
        raise ApiError(422, "INVALID_REQUEST", "start cannot be after end")
    if end_at > cutoff:
        raise ApiError(422, "INVALID_REQUEST", "end cannot be after decision_time")
    records = PostgresMarketDataRepository(connection).historical_bars_as_of(
        symbol=normalized_symbol,
        start=start_at,
        end=end_at,
        decision_time=cutoff,
        coverage=_coverage(settings),
        session=MarketSession.REGULAR,
        timeframe=timeframe,
        limit=limit,
    )
    items = [_market_record(record) for record in records]
    return {"status": _read_status(items), "decision_time": cutoff, "items": items}


@router.get("/data-quality", response_model=DataQualityResponse)
def list_data_quality(
    connection: ConnectionDependency,
    provider: Annotated[str, Query(min_length=1)],
    dataset: Annotated[str, Query(min_length=1)],
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    visible = (
        select(data_quality_observation)
        .join(
            raw_data_object,
            raw_data_object.c.id == data_quality_observation.c.raw_data_object_id,
        )
        .where(
            data_quality_observation.c.provider == provider.strip().upper(),
            data_quality_observation.c.dataset == dataset.strip(),
            data_quality_observation.c.observed_at <= cutoff,
            raw_data_object.c.available_at <= cutoff,
        )
    ).subquery()
    rows = connection.execute(
        select(visible).order_by(visible.c.observed_at.desc()).limit(limit)
    ).mappings()
    items = [_row(row) for row in rows]
    status: Literal["SUCCESS", "DEGRADED", "FAILURE"]
    current_rank = (
        func.row_number()
        .over(
            partition_by=visible.c.dimension,
            order_by=(visible.c.observed_at.desc(), visible.c.created_at.desc()),
        )
        .label("current_rank")
    )
    ranked = select(visible, current_rank).subquery()
    current = tuple(connection.execute(select(ranked).where(ranked.c.current_rank == 1)).mappings())
    if not current or any(item["status"] in {"FAIL", "UNAVAILABLE"} for item in current):
        status = "FAILURE"
    elif any(item["status"] == "DEGRADED" for item in current):
        status = "DEGRADED"
    else:
        status = "SUCCESS"
    return {"status": status, "decision_time": cutoff, "items": items}


@router.get("/watchlist")
def list_watchlist(connection: ConnectionDependency) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(*_WATCHLIST_PUBLIC_COLUMNS).order_by(watchlist_item.c.symbol)
    ).mappings()
    return [_row(row) for row in rows]


@router.post("/watchlist", status_code=201)
def add_watchlist(request: WatchlistRequest, connection: ConnectionDependency) -> dict[str, Any]:
    values = request.model_dump()
    values["security_id"] = _security_id_for_symbol(connection, request.symbol)
    row = (
        connection.execute(
            pg_insert(watchlist_item)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[watchlist_item.c.symbol],
                set_={
                    "daily_research": request.daily_research,
                    "intraday_monitoring": request.intraday_monitoring,
                    "thresholds": request.thresholds,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(*_WATCHLIST_PUBLIC_COLUMNS)
        )
        .mappings()
        .one()
    )
    return _row(row)


@router.patch("/watchlist/{symbol}")
def patch_watchlist(
    symbol: str, request: WatchlistPatch, connection: ConnectionDependency
) -> dict[str, Any]:
    values = request.model_dump(exclude_none=True)
    values["updated_at"] = datetime.now(UTC)
    row = (
        connection.execute(
            update(watchlist_item)
            .where(watchlist_item.c.symbol == _symbol(symbol))
            .values(**values)
            .returning(*_WATCHLIST_PUBLIC_COLUMNS)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Watchlist item not found")
    return _row(row)


@router.delete("/watchlist/{symbol}", status_code=204)
def delete_watchlist(symbol: str, connection: ConnectionDependency) -> Response:
    deleted = connection.execute(
        watchlist_item.delete().where(watchlist_item.c.symbol == _symbol(symbol))
    )
    if deleted.rowcount != 1:
        raise ApiError(404, "NOT_FOUND", "Watchlist item not found")
    return Response(status_code=204)


@router.post("/research-runs", response_model=RunResponse, status_code=202)
def create_research_run(
    request: ResearchRunRequest,
    response: Response,
    connection: ConnectionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RunResponse:
    payload = request.model_dump(mode="json")
    admission = paper_market_data_admission(
        settings,
        cutoff=request.data_cutoff,
        purpose=DataPurpose.RESEARCH,
    )
    if admission is not None:
        payload.update(admission_payload(admission))
    return _create_run(
        connection,
        settings,
        response,
        run_type="RESEARCH",
        idempotency_key=idempotency_key,
        payload=payload,
        symbol=request.symbol,
        decision_time=request.decision_time,
        data_cutoff=request.data_cutoff,
    )


@router.get("/research-runs/latest", response_model=RunResponse)
def get_latest_research_run(
    decision_time: datetime, connection: ConnectionDependency
) -> RunResponse:
    cutoff = _aware_query_time(decision_time, "decision_time")
    row = (
        connection.execute(
            select(agent_run)
            .where(
                agent_run.c.run_type == "RESEARCH",
                agent_run.c.decision_time <= cutoff,
                agent_run.c.created_at <= cutoff,
            )
            .order_by(agent_run.c.decision_time.desc(), agent_run.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "No research run exists at this decision time")
    return _run_response(row)


@router.get("/research-runs/{run_id}", response_model=RunResponse)
def get_research_run(
    run_id: UUID,
    decision_time: datetime,
    connection: ConnectionDependency,
) -> RunResponse:
    cutoff = _aware_query_time(decision_time, "decision_time")
    row = (
        connection.execute(
            select(agent_run).where(
                agent_run.c.id == run_id,
                agent_run.c.created_at <= cutoff,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Research run not found")
    return _run_response(row)


@router.post("/research-runs/{run_id}/cancel", response_model=RunResponse)
def cancel_research_run(run_id: UUID, connection: ConnectionDependency) -> RunResponse:
    row = (
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == run_id, agent_run.c.status.in_(("QUEUED", "RUNNING")))
            .values(status="CANCELLED", updated_at=datetime.now(UTC))
            .returning(agent_run)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(409, "RUN_NOT_CANCELLABLE", "Research run is not active")
    append_run_event(
        connection,
        run_id,
        "run.cancelled",
        {"status": "CANCELLED", "source": "api"},
    )
    return _run_response(row)


@router.get("/research-runs/{run_id}/report", response_model=ResearchRunReportResponse)
def get_research_report(
    run_id: UUID,
    decision_time: datetime,
    connection: ConnectionDependency,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    thesis = (
        connection.execute(
            select(investment_thesis)
            .join(agent_run, agent_run.c.id == investment_thesis.c.run_id)
            .where(
                investment_thesis.c.run_id == run_id,
                agent_run.c.created_at <= cutoff,
                investment_thesis.c.created_at <= cutoff,
            )
            .order_by(investment_thesis.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if thesis is None:
        raise ApiError(404, "NOT_FOUND", "Research report not found")
    opinion = (
        connection.execute(
            select(research_opinion)
            .where(
                research_opinion.c.thesis_id == thesis["id"],
                research_opinion.c.created_at <= cutoff,
            )
            .order_by(research_opinion.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )
    decision = (
        connection.execute(
            select(
                decision_snapshot.c.id,
                decision_snapshot.c.data_cutoff,
                decision_snapshot.c.available_at,
                decision_snapshot.c.prompt_version,
                decision_snapshot.c.model_version,
                decision_snapshot.c.created_at,
                research_scoring_policy_version.c.version.label("research_scoring"),
                risk_policy_version.c.version.label("risk"),
                execution_policy_version.c.version.label("execution"),
                confidence_policy_version.c.version.label("confidence"),
            )
            .join(
                research_scoring_policy_version,
                research_scoring_policy_version.c.id
                == decision_snapshot.c.research_scoring_policy_version_id,
            )
            .join(
                risk_policy_version,
                risk_policy_version.c.id == decision_snapshot.c.risk_policy_version_id,
            )
            .join(
                execution_policy_version,
                execution_policy_version.c.id == decision_snapshot.c.execution_policy_version_id,
            )
            .join(
                confidence_policy_version,
                confidence_policy_version.c.id == decision_snapshot.c.confidence_policy_version_id,
            )
            .where(
                decision_snapshot.c.thesis_id == thesis["id"],
                decision_snapshot.c.available_at <= cutoff,
                decision_snapshot.c.created_at <= cutoff,
            )
            .order_by(decision_snapshot.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )
    evidence_rows = (
        connection.execute(
            select(
                evidence_item.c.id,
                thesis_evidence_link.c.relation,
                thesis_evidence_link.c.weight,
                thesis_evidence_link.c.rationale,
                claim.c.statement,
                raw_data_object.c.provider,
                raw_data_object.c.feed_type,
                raw_data_object.c.event_time,
                raw_data_object.c.available_at,
                raw_data_object.c.ingested_at,
                raw_data_object.c.content_hash,
                raw_data_object.c.raw_object_key,
            )
            .select_from(
                thesis_evidence_link.join(
                    evidence_item,
                    evidence_item.c.id == thesis_evidence_link.c.evidence_id,
                )
                .join(
                    derived_metric,
                    derived_metric.c.id == evidence_item.c.derived_metric_id,
                )
                .join(
                    normalized_record,
                    normalized_record.c.id == derived_metric.c.normalized_record_id,
                )
                .join(
                    raw_data_object,
                    raw_data_object.c.id == normalized_record.c.raw_data_object_id,
                )
                .outerjoin(
                    claim,
                    and_(
                        claim.c.evidence_id == evidence_item.c.id,
                        claim.c.created_at <= cutoff,
                    ),
                )
            )
            .where(
                thesis_evidence_link.c.thesis_id == thesis["id"],
                thesis_evidence_link.c.created_at <= cutoff,
                evidence_item.c.created_at <= cutoff,
                derived_metric.c.created_at <= cutoff,
                normalized_record.c.created_at <= cutoff,
                raw_data_object.c.available_at <= cutoff,
                raw_data_object.c.ingested_at <= cutoff,
            )
            .order_by(evidence_item.c.id, claim.c.created_at, claim.c.id)
        )
        .mappings()
        .all()
    )
    evidence: list[dict[str, Any]] = []
    evidence_by_link: dict[tuple[UUID, str], dict[str, Any]] = {}
    for item in evidence_rows:
        key = (item["id"], str(item["relation"]))
        rendered = evidence_by_link.get(key)
        if rendered is None:
            rendered = {
                "id": item["id"],
                "relation": item["relation"],
                "weight": item["weight"],
                "rationale": item["rationale"],
                "claims": [],
                "provider": item["provider"],
                "feed_type": item["feed_type"],
                "event_time": item["event_time"],
                "available_at": item["available_at"],
                "ingested_at": item["ingested_at"],
                "content_hash": item["content_hash"],
                "raw_object_key": item["raw_object_key"],
            }
            evidence_by_link[key] = rendered
            evidence.append(rendered)
        if item["statement"] is not None:
            rendered["claims"].append(item["statement"])

    gaps = (
        connection.execute(
            select(evidence_gap)
            .where(
                evidence_gap.c.run_id == run_id,
                evidence_gap.c.observed_at <= cutoff,
                evidence_gap.c.created_at <= cutoff,
            )
            .order_by(evidence_gap.c.observed_at, evidence_gap.c.id)
        )
        .mappings()
        .all()
    )
    diff = (
        connection.execute(
            select(decision_diff).where(
                decision_diff.c.decision_id == decision["id"],
                decision_diff.c.created_at <= cutoff,
            )
        )
        .mappings()
        .one()
    )
    return {
        "run_id": run_id,
        "thesis": {
            key: thesis[key]
            for key in (
                "id",
                "symbol",
                "as_of",
                "direction",
                "summary",
                "catalysts",
                "risks",
                "invalidation_conditions",
                "horizon",
                "confidence",
                "supersedes_thesis_id",
                "created_at",
            )
        },
        "opinion": {key: opinion[key] for key in ("id", "value", "created_at")},
        "decision": {
            "id": decision["id"],
            "data_cutoff": decision["data_cutoff"],
            "available_at": decision["available_at"],
            "prompt_version": decision["prompt_version"],
            "model_version": decision["model_version"],
            "policy_versions": {
                key: decision[key]
                for key in ("research_scoring", "risk", "execution", "confidence")
            },
            "created_at": decision["created_at"],
        },
        "evidence": evidence,
        "evidence_gaps": [dict(gap) for gap in gaps],
        "decision_diff": dict(diff),
    }


@router.get("/stocks/{symbol}/research", response_model=ResearchPage)
def get_stock_research(
    symbol: str,
    connection: ConnectionDependency,
    settings: SettingsDependency,
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    has_superseded_decision = (
        select(decision_snapshot.c.id)
        .where(
            decision_snapshot.c.thesis_id == investment_thesis.c.id,
            decision_snapshot.c.data_cutoff <= cutoff,
            decision_snapshot.c.available_at <= cutoff,
            decision_snapshot.c.created_at <= cutoff,
            ~decision_is_active_at(decision_snapshot.c.id, cutoff),
        )
        .exists()
    )
    latest_opinion = (
        select(research_opinion.c.value)
        .where(
            research_opinion.c.thesis_id == investment_thesis.c.id,
            research_opinion.c.created_at <= cutoff,
        )
        .order_by(research_opinion.c.created_at.desc(), research_opinion.c.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = (
        connection.execute(
            select(investment_thesis, latest_opinion.label("opinion"))
            .where(
                investment_thesis.c.symbol == _symbol(symbol),
                investment_thesis.c.as_of <= cutoff,
                investment_thesis.c.created_at <= cutoff,
                ~has_superseded_decision,
                _cursor_filter(investment_thesis.c.as_of, investment_thesis.c.id, cursor),
            )
            .order_by(investment_thesis.c.as_of.desc(), investment_thesis.c.id.desc())
            .limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "as_of")
    visible_security = (
        select(security_identifier_version.c.security_id)
        .where(
            security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL",
            security_identifier_version.c.identifier_value == _symbol(symbol),
            security_identifier_version.c.available_at <= cutoff,
            security_identifier_version.c.effective_from <= cutoff,
            or_(
                security_identifier_version.c.effective_to.is_(None),
                security_identifier_version.c.effective_to > cutoff,
            ),
        )
        .order_by(security_identifier_version.c.available_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    document_raw = raw_data_object.alias("sec_document_raw")
    filing_rows = (
        connection.execute(
            select(
                sec_filing.c.id,
                sec_filing.c.provider,
                sec_filing.c.accession_number,
                sec_filing.c.form,
                sec_filing.c.filing_date,
                sec_filing.c.report_date,
                sec_filing.c.accepted_at,
                sec_filing.c.available_at,
                sec_filing.c.description,
                document_raw.c.event_time,
                document_raw.c.content_hash,
                document_raw.c.raw_object_key,
                document_raw.c.raw_object_key.label("document_raw_object_key"),
            )
            .join(document_raw, document_raw.c.id == sec_filing.c.document_raw_data_object_id)
            .where(
                sec_filing.c.security_id == visible_security,
                sec_filing.c.accepted_at <= cutoff,
                sec_filing.c.available_at <= cutoff,
                document_raw.c.available_at <= cutoff,
            )
            .order_by(sec_filing.c.accepted_at.desc(), sec_filing.c.id.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    fact_raw = raw_data_object.alias("financial_fact_raw")
    fact_rows = (
        connection.execute(
            select(
                financial_fact.c.id,
                financial_fact.c.provider,
                financial_fact.c.taxonomy,
                financial_fact.c.source_concept,
                financial_fact.c.canonical_concept,
                financial_fact.c.value,
                financial_fact.c.unit,
                financial_fact.c.currency,
                financial_fact.c.period_start,
                financial_fact.c.period_end,
                financial_fact.c.accession_number,
                fact_raw.c.event_time,
                financial_fact.c.available_at,
                fact_raw.c.content_hash,
                fact_raw.c.raw_object_key,
                financial_fact.c.mapping_status,
            )
            .join(sec_filing, sec_filing.c.id == financial_fact.c.sec_filing_id)
            .join(fact_raw, fact_raw.c.id == financial_fact.c.raw_data_object_id)
            .where(
                financial_fact.c.security_id == visible_security,
                financial_fact.c.available_at <= cutoff,
                sec_filing.c.available_at <= cutoff,
                fact_raw.c.available_at <= cutoff,
            )
            .order_by(financial_fact.c.period_end.desc(), financial_fact.c.id.desc())
            .limit(100)
        )
        .mappings()
        .all()
    )
    news_raw = raw_data_object.alias("news_raw")
    news_rows = (
        connection.execute(
            select(
                news_article.c.id,
                news_article.c.provider,
                news_article.c.headline,
                news_article.c.source,
                news_article.c.summary,
                news_article.c.published_at.label("event_time"),
                news_article.c.available_at,
                news_raw.c.content_hash,
                news_raw.c.raw_object_key,
            )
            .join(news_raw, news_raw.c.id == news_article.c.raw_data_object_id)
            .where(
                news_article.c.provider != "FIXTURE",
                news_raw.c.provider != "FIXTURE",
                news_article.c.symbols.contains([_symbol(symbol)]),
                news_article.c.pit_eligible.is_(True),
                news_article.c.observed_at <= cutoff,
                news_article.c.available_at <= cutoff,
                news_raw.c.available_at <= cutoff,
            )
            .order_by(news_article.c.published_at.desc(), news_article.c.id.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    earnings_raw = raw_data_object.alias("earnings_raw")
    newer_earnings = earnings_event.alias("newer_earnings")
    has_visible_earnings_revision = (
        select(newer_earnings.c.id)
        .where(
            newer_earnings.c.supersedes_id == earnings_event.c.id,
            newer_earnings.c.available_at <= cutoff,
        )
        .exists()
    )
    earnings_rows = (
        connection.execute(
            select(
                earnings_event.c.id,
                earnings_event.c.provider,
                earnings_event.c.event_date,
                earnings_event.c.fiscal_date_end,
                earnings_event.c.estimate,
                earnings_event.c.currency,
                earnings_raw.c.event_time,
                earnings_event.c.available_at,
                earnings_raw.c.content_hash,
                earnings_raw.c.raw_object_key,
            )
            .join(earnings_raw, earnings_raw.c.id == earnings_event.c.raw_data_object_id)
            .where(
                earnings_event.c.provider != "FIXTURE",
                earnings_raw.c.provider != "FIXTURE",
                earnings_event.c.security_id == visible_security,
                earnings_event.c.available_at <= cutoff,
                earnings_raw.c.available_at <= cutoff,
                ~has_visible_earnings_revision,
            )
            .order_by(earnings_event.c.event_date, earnings_event.c.id.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    option_rows = (
        connection.execute(
            select(
                option_snapshot.c.id,
                option_snapshot.c.provider,
                option_snapshot.c.feed_type,
                option_snapshot.c.event_time,
                option_snapshot.c.available_at,
                option_snapshot.c.content_hash,
                option_snapshot.c.raw_object_key,
                option_snapshot.c.payload,
            )
            .where(
                option_snapshot.c.provider != "FIXTURE",
                option_snapshot.c.symbol == _symbol(symbol),
                option_snapshot.c.event_time <= cutoff,
                option_snapshot.c.available_at <= cutoff,
            )
            .order_by(option_snapshot.c.event_time.desc(), option_snapshot.c.id.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    unavailable_domains = ["ANALYST_TARGETS"]
    unavailable_reasons = {
        "ANALYST_TARGETS": (
            "Unsupported until an authoritative provider, schema, and license are approved."
        )
    }
    if not news_rows:
        unavailable_domains.append("NEWS")
        unavailable_reasons["NEWS"] = (
            "No point-in-time eligible Alpaca News record exists at this decision time."
            if settings.alpaca_data_key and settings.alpaca_data_secret
            else "Configure ALPACA_DATA_KEY and ALPACA_DATA_SECRET to ingest Alpaca News."
        )
    if not earnings_rows:
        unavailable_domains.append("EARNINGS")
        unavailable_reasons["EARNINGS"] = (
            "No point-in-time eligible Alpha Vantage earnings record exists at this decision time."
            if settings.alpha_vantage_api_key
            else "Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar."
        )
    if not option_rows:
        unavailable_domains.append("OPTIONS")
        unavailable_reasons["OPTIONS"] = (
            "Unavailable because the locked architecture has no approved lawful read-only "
            "Options provider."
        )
    return {
        "decision_time": cutoff,
        "items": items,
        "sec_filings": [_row(row) for row in filing_rows],
        "financial_facts": [_row(row) for row in fact_rows],
        "news_articles": [_row(row) for row in news_rows],
        "earnings_events": [_row(row) for row in earnings_rows],
        "option_snapshots": [_row(row) for row in option_rows],
        "unavailable_domains": unavailable_domains,
        "unavailable_reasons": unavailable_reasons,
        "next_cursor": next_cursor,
    }


@router.get("/alerts", response_model=AlertPage)
def list_alerts(
    connection: ConnectionDependency,
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    rows = (
        connection.execute(
            select(alert_event)
            .where(
                alert_event.c.event_time <= cutoff,
                alert_event.c.created_at <= cutoff,
                _cursor_filter(alert_event.c.event_time, alert_event.c.id, cursor),
            )
            .order_by(alert_event.c.event_time.desc(), alert_event.c.id.desc())
            .limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "event_time")
    return {"decision_time": cutoff, "items": items, "next_cursor": next_cursor}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: UUID,
    action: HumanAction,
    connection: ConnectionDependency,
    actor: ActorDependency,
) -> dict[str, Any]:
    row = (
        connection.execute(
            update(alert_event)
            .where(alert_event.c.id == alert_id)
            .values(acknowledged_at=datetime.now(UTC), acknowledged_by=actor.id)
            .returning(alert_event)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Alert not found")
    return _row(row)


@router.get("/portfolio", response_model=PortfolioResponse)
def get_portfolio(connection: ConnectionDependency, decision_time: datetime) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    configuration = (
        connection.execute(
            select(
                paper_portfolio_config.c.id,
                paper_portfolio_config.c.name,
                paper_portfolio_config.c.initial_cash,
                paper_portfolio_config.c.currency,
            ).where(paper_portfolio_config.c.created_at <= cutoff)
        )
        .mappings()
        .one_or_none()
    )
    empty = {
        "status": "EMPTY",
        "decision_time": cutoff,
        "trading": "paper_only",
        "configuration": _row(configuration) if configuration else None,
        "initialized_at": None,
        "cash": None,
        "latest_nav": None,
        "positions": [],
        "risk_decisions": [],
        "orders": [],
        "fills": [],
        "cash_ledger": [],
        "performance_history": [],
    }
    if configuration is None:
        return empty
    portfolio_id = configuration["id"]
    initialized_at = connection.execute(
        select(cash_ledger.c.occurred_at)
        .where(
            cash_ledger.c.portfolio_id == portfolio_id,
            cash_ledger.c.account == "EQUITY:OPENING_BALANCE",
            cash_ledger.c.occurred_at <= cutoff,
            cash_ledger.c.created_at <= cutoff,
        )
        .order_by(cash_ledger.c.occurred_at, cash_ledger.c.id)
        .limit(1)
    ).scalar_one_or_none()
    if initialized_at is None:
        return empty

    cash = connection.execute(
        select(func.coalesce(func.sum(cash_ledger.c.debit - cash_ledger.c.credit), 0)).where(
            cash_ledger.c.portfolio_id == portfolio_id,
            cash_ledger.c.account == "ASSET:CASH",
            cash_ledger.c.occurred_at <= cutoff,
            cash_ledger.c.created_at <= cutoff,
        )
    ).scalar_one()
    fill_rows = (
        connection.execute(
            select(paper_fill)
            .where(
                paper_fill.c.portfolio_id == portfolio_id,
                paper_fill.c.filled_at <= cutoff,
                paper_fill.c.created_at <= cutoff,
            )
            .order_by(paper_fill.c.filled_at, paper_fill.c.id)
            .limit(5001)
        )
        .mappings()
        .all()
    )
    if len(fill_rows) > 5000:
        raise ApiError(
            503,
            "READ_MODEL_LIMIT",
            "Portfolio position history exceeds the bounded read model",
            retryable=True,
        )
    symbols = tuple(sorted({str(row["symbol"]) for row in fill_rows}))
    prices: dict[str, tuple[Decimal, datetime]] = {}
    if symbols:
        ranked_prices = (
            select(
                market_bar.c.symbol,
                market_bar.c.close,
                market_bar.c.available_at,
                func.row_number()
                .over(
                    partition_by=market_bar.c.symbol,
                    order_by=(market_bar.c.event_time.desc(), market_bar.c.available_at.desc()),
                )
                .label("rank"),
            )
            .where(
                market_bar.c.symbol.in_(symbols),
                market_bar.c.event_time <= cutoff,
                market_bar.c.available_at <= cutoff,
                market_bar.c.close.is_not(None),
            )
            .subquery()
        )
        price_rows = connection.execute(select(ranked_prices).where(ranked_prices.c.rank == 1))
        prices = {str(row.symbol): (Decimal(row.close), row.available_at) for row in price_rows}
    positions = build_positions(
        tuple(
            PositionFill(
                str(row["symbol"]),
                cast(Literal["BUY", "SELL"], row["side"]),
                Decimal(row["quantity"]),
                Decimal(row["price"]),
            )
            for row in fill_rows
        ),
        prices=prices,
    )
    latest_nav = (
        connection.execute(
            select(portfolio_nav)
            .where(
                portfolio_nav.c.portfolio_id == portfolio_id,
                portfolio_nav.c.event_time <= cutoff,
                portfolio_nav.c.available_at <= cutoff,
            )
            .order_by(portfolio_nav.c.event_time.desc(), portfolio_nav.c.available_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    nav_rows = list(
        reversed(
            connection.execute(
                select(portfolio_nav)
                .where(
                    portfolio_nav.c.portfolio_id == portfolio_id,
                    portfolio_nav.c.event_time <= cutoff,
                    portfolio_nav.c.available_at <= cutoff,
                )
                .order_by(portfolio_nav.c.event_time.desc(), portfolio_nav.c.id.desc())
                .limit(365)
            )
            .mappings()
            .all()
        )
    )
    risk_rows = (
        connection.execute(
            select(risk_decision)
            .where(
                risk_decision.c.portfolio_id == portfolio_id,
                risk_decision.c.decided_at <= cutoff,
                risk_decision.c.created_at <= cutoff,
            )
            .order_by(risk_decision.c.decided_at.desc(), risk_decision.c.id.desc())
            .limit(100)
        )
        .mappings()
        .all()
    )
    order_rows = (
        connection.execute(
            select(paper_order)
            .where(
                paper_order.c.portfolio_id == portfolio_id,
                paper_order.c.decision_time <= cutoff,
                paper_order.c.created_at <= cutoff,
            )
            .order_by(paper_order.c.decision_time.desc(), paper_order.c.id.desc())
            .limit(100)
        )
        .mappings()
        .all()
    )
    ledger_rows = list(
        reversed(
            connection.execute(
                select(
                    cash_ledger.c.id,
                    cash_ledger.c.transaction_id,
                    cash_ledger.c.source_id,
                    cash_ledger.c.account,
                    cash_ledger.c.debit,
                    cash_ledger.c.credit,
                    cash_ledger.c.currency,
                    cash_ledger.c.occurred_at,
                    cash_ledger.c.idempotency_key,
                    cash_ledger.c.reversal_of_id,
                    cash_ledger.c.created_at,
                )
                .where(
                    cash_ledger.c.portfolio_id == portfolio_id,
                    cash_ledger.c.occurred_at <= cutoff,
                    cash_ledger.c.created_at <= cutoff,
                )
                .order_by(
                    cash_ledger.c.occurred_at.desc(),
                    cash_ledger.c.account.desc(),
                    cash_ledger.c.id.desc(),
                )
                .limit(100)
            )
            .mappings()
            .all()
        )
    )
    return {
        "status": "SUCCESS",
        "decision_time": cutoff,
        "trading": "paper_only",
        "configuration": _row(configuration),
        "initialized_at": initialized_at,
        "cash": {"balance": cash, "currency": configuration["currency"]},
        "latest_nav": _row(latest_nav) if latest_nav else None,
        "positions": [_value(asdict(position)) for position in positions],
        "risk_decisions": [_row(row) for row in risk_rows],
        "orders": [_row(row) for row in order_rows],
        "fills": [_row(row) for row in reversed(fill_rows[-100:])],
        "cash_ledger": [_row(row) for row in ledger_rows],
        "performance_history": [_row(row) for row in nav_rows],
    }


@router.post("/portfolio/initialize", response_model=PortfolioInitializationResponse)
def initialize_portfolio(
    request: PortfolioInitializationRequest,
    response: Response,
    connection: ConnectionDependency,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('paper-portfolio-initialize'))"))
    config = connection.execute(select(paper_portfolio_config)).mappings().one()
    effective_at = request.effective_at.astimezone(UTC)
    request_hash = sha256(effective_at.isoformat().encode()).hexdigest()
    admitted = (
        connection.execute(
            select(portfolio_initialization_request).where(
                portfolio_initialization_request.c.idempotency_key == idempotency_key
            )
        )
        .mappings()
        .one_or_none()
    )
    if admitted is not None:
        if admitted["request_hash"] != request_hash:
            raise ApiError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "Idempotency-Key was already used with a different request payload",
            )
        response.headers["Idempotency-Replayed"] = "true"
        return {
            "status": "READY",
            "portfolio_id": config["id"],
            "name": config["name"],
            "initial_cash": config["initial_cash"],
            "currency": config["currency"],
            "initialized_at": admitted["effective_at"],
        }
    initialized_at = connection.execute(
        select(cash_ledger.c.occurred_at)
        .where(
            cash_ledger.c.portfolio_id == config["id"],
            cash_ledger.c.account == "EQUITY:OPENING_BALANCE",
        )
        .order_by(cash_ledger.c.occurred_at, cash_ledger.c.id)
        .limit(1)
    ).scalar_one_or_none()
    if initialized_at is not None:
        raise ApiError(
            409,
            "PORTFOLIO_ALREADY_INITIALIZED",
            "The singleton paper portfolio has already been initialized",
        )
    connection.execute(
        insert(portfolio_initialization_request).values(
            portfolio_id=config["id"],
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            effective_at=effective_at,
        )
    )
    PostgresPaperAccountingStore(connection).persist_ledger(
        initial_funding(
            config["id"],
            config["initial_cash"],
            config["currency"],
            effective_at,
        )
    )
    connection.execute(
        insert(portfolio_nav).values(
            portfolio_id=config["id"],
            nav=config["initial_cash"],
            event_time=effective_at,
            available_at=effective_at,
        )
    )
    response.headers["Idempotency-Replayed"] = "false"
    return {
        "status": "READY",
        "portfolio_id": config["id"],
        "name": config["name"],
        "initial_cash": config["initial_cash"],
        "currency": config["currency"],
        "initialized_at": effective_at,
    }


@router.post("/portfolio/rebalance-runs", response_model=RunResponse, status_code=202)
def create_portfolio_run(
    request: PortfolioRunRequest,
    response: Response,
    connection: ConnectionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RunResponse:
    admission = paper_market_data_admission(
        settings,
        cutoff=request.data_cutoff,
        purpose=DataPurpose.PAPER_EXECUTION,
    )
    if admission is not None and admission.outcome is PolicyOutcome.DENIED_NO_ACTION:
        raise ApiError(403, "MARKET_DATA_NOT_ENTITLED", admission.reason or "SIP required")
    payload = request.model_dump(mode="json")
    if admission is not None:
        payload.update(admission_payload(admission))
    return _create_run(
        connection,
        settings,
        response,
        run_type="PORTFOLIO",
        idempotency_key=idempotency_key,
        payload=payload,
        symbol=None,
        decision_time=request.decision_time,
        data_cutoff=request.data_cutoff,
    )


@router.get("/portfolio/orders", response_model=PaperOrderPage)
def list_orders(
    connection: ConnectionDependency,
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    rows = (
        connection.execute(
            select(paper_order)
            .where(
                paper_order.c.decision_time <= cutoff,
                paper_order.c.created_at <= cutoff,
                _cursor_filter(paper_order.c.decision_time, paper_order.c.id, cursor),
            )
            .order_by(paper_order.c.decision_time.desc(), paper_order.c.id.desc())
            .limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "decision_time")
    return {"decision_time": cutoff, "items": items, "next_cursor": next_cursor}


@router.get("/portfolio/fills", response_model=PaperFillPage)
def list_fills(
    connection: ConnectionDependency,
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    rows = (
        connection.execute(
            select(paper_fill)
            .where(
                paper_fill.c.filled_at <= cutoff,
                paper_fill.c.created_at <= cutoff,
                _cursor_filter(paper_fill.c.filled_at, paper_fill.c.id, cursor),
            )
            .order_by(paper_fill.c.filled_at.desc(), paper_fill.c.id.desc())
            .limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "filled_at")
    return {"decision_time": cutoff, "items": items, "next_cursor": next_cursor}


@router.get("/weekly-reviews", response_model=WeeklyReviewPage)
def list_weekly_reviews(
    connection: ConnectionDependency,
    decision_time: datetime,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    rows = (
        connection.execute(
            select(weekly_review_run)
            .where(
                weekly_review_run.c.decision_time <= cutoff,
                weekly_review_run.c.data_cutoff <= cutoff,
                weekly_review_run.c.created_at <= cutoff,
                _cursor_filter(weekly_review_run.c.decision_time, weekly_review_run.c.id, cursor),
            )
            .order_by(weekly_review_run.c.decision_time.desc(), weekly_review_run.c.id.desc())
            .limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "decision_time")
    return {"decision_time": cutoff, "items": items, "next_cursor": next_cursor}


@router.get("/weekly-reviews/{review_id}", response_model=WeeklyReviewDetail)
def get_weekly_review_detail(
    review_id: UUID,
    connection: ConnectionDependency,
    decision_time: datetime,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    review = (
        connection.execute(
            select(weekly_review_run).where(
                weekly_review_run.c.id == review_id,
                weekly_review_run.c.decision_time <= cutoff,
                weekly_review_run.c.data_cutoff <= cutoff,
                weekly_review_run.c.created_at <= cutoff,
            )
        )
        .mappings()
        .one_or_none()
    )
    if review is None:
        raise ApiError(404, "NOT_FOUND", "Weekly review not found")

    outcomes = (
        connection.execute(
            select(
                decision_outcome.c.id,
                decision_outcome.c.decision_id,
                decision_outcome.c.status,
                decision_outcome.c.returns,
                decision_outcome.c.excess_returns,
                decision_outcome.c.maximum_favorable_excursion,
                decision_outcome.c.maximum_adverse_excursion,
                decision_outcome.c.risk_adjusted_return,
                decision_outcome.c.calibration_error,
                decision_outcome.c.computed_at,
                decision_outcome.c.created_at,
                investment_thesis.c.symbol,
                investment_thesis.c.confidence,
                research_opinion.c.value.label("opinion"),
            )
            .select_from(
                decision_outcome.join(
                    decision_snapshot,
                    decision_outcome.c.decision_id == decision_snapshot.c.id,
                )
                .join(
                    investment_thesis,
                    decision_snapshot.c.thesis_id == investment_thesis.c.id,
                )
                .join(
                    research_opinion,
                    research_opinion.c.thesis_id == investment_thesis.c.id,
                )
            )
            .where(
                decision_outcome.c.weekly_review_run_id == review_id,
                decision_outcome.c.computed_at <= cutoff,
                decision_outcome.c.created_at <= cutoff,
                decision_snapshot.c.data_cutoff <= cutoff,
                decision_snapshot.c.available_at <= cutoff,
                investment_thesis.c.as_of <= cutoff,
                investment_thesis.c.created_at <= cutoff,
                research_opinion.c.created_at <= cutoff,
            )
            .order_by(decision_outcome.c.computed_at, decision_outcome.c.id)
        )
        .mappings()
        .all()
    )
    outcome_ids = tuple(item["id"] for item in outcomes)
    attributions = (
        connection.execute(
            select(error_attribution)
            .where(
                error_attribution.c.outcome_id.in_(outcome_ids),
                error_attribution.c.created_at <= cutoff,
            )
            .order_by(error_attribution.c.created_at, error_attribution.c.id)
        )
        .mappings()
        .all()
    )
    attribution_ids = tuple(item["id"] for item in attributions)
    lesson_ids = select(lesson_attribution_link.c.lesson_id).where(
        lesson_attribution_link.c.attribution_id.in_(attribution_ids),
        lesson_attribution_link.c.created_at <= cutoff,
    )
    lessons = (
        connection.execute(
            select(
                candidate_lesson.c.id,
                candidate_lesson.c.attribution_id,
                candidate_lesson.c.scope,
                candidate_lesson.c.statement,
                candidate_lesson.c.evidence,
                candidate_lesson.c.counter_evidence,
                candidate_lesson.c.confidence,
                candidate_lesson.c.replay_delta,
                candidate_lesson.c.creator,
                candidate_lesson.c.status,
                candidate_lesson.c.created_at,
            )
            .where(
                candidate_lesson.c.id.in_(lesson_ids),
                candidate_lesson.c.created_at <= cutoff,
            )
            .order_by(candidate_lesson.c.created_at, candidate_lesson.c.id)
        )
        .mappings()
        .all()
    )
    visible_lesson_ids = tuple(item["id"] for item in lessons)
    approvals = (
        connection.execute(
            select(lesson_approval)
            .where(
                lesson_approval.c.lesson_id.in_(visible_lesson_ids),
                lesson_approval.c.created_at <= cutoff,
            )
            .order_by(lesson_approval.c.created_at, lesson_approval.c.id)
        )
        .mappings()
        .all()
    )
    replays = (
        connection.execute(
            select(replay_run)
            .where(
                replay_run.c.lesson_id.in_(visible_lesson_ids),
                replay_run.c.data_cutoff <= cutoff,
                replay_run.c.created_at <= cutoff,
            )
            .order_by(replay_run.c.data_cutoff, replay_run.c.id)
        )
        .mappings()
        .all()
    )
    calibration = []
    for outcome in outcomes:
        returns = outcome["returns"] or {}
        final_return = None
        if returns:
            final_return = Decimal(str(returns[max(returns, key=lambda value: int(value))]))
        calibration.append(
            {
                "decision_id": outcome["decision_id"],
                "confidence": outcome["confidence"],
                "status": outcome["status"],
                "realized_return": final_return,
                "calibration_error": outcome["calibration_error"],
            }
        )
    return {
        "decision_time": cutoff,
        "review": review,
        "outcomes": outcomes,
        "attributions": attributions,
        "lessons": lessons,
        "approvals": approvals,
        "replays": replays,
        "calibration": calibration,
    }


def _lesson_action(
    connection: Connection,
    review_id: UUID,
    lesson_id: UUID,
    action: HumanAction,
    actor: HumanActor,
    disposition: Literal["APPROVE", "REJECT"],
) -> dict[str, Any]:
    try:
        row = record_lesson_decision(
            connection,
            review_id=review_id,
            lesson_id=lesson_id,
            actor=actor,
            action=disposition,
            rationale=action.rationale,
        )
    except LessonNotFound as exception:
        raise ApiError(404, "NOT_FOUND", "Lesson not found in weekly review") from exception
    return _row(row)


@router.post("/weekly-reviews/{review_id}/lessons/{lesson_id}/approve")
def approve_lesson(
    review_id: UUID,
    lesson_id: UUID,
    action: HumanAction,
    connection: ConnectionDependency,
    actor: ActorDependency,
) -> dict[str, Any]:
    return _lesson_action(connection, review_id, lesson_id, action, actor, "APPROVE")


@router.post("/weekly-reviews/{review_id}/lessons/{lesson_id}/reject")
def reject_lesson(
    review_id: UUID,
    lesson_id: UUID,
    action: HumanAction,
    connection: ConnectionDependency,
    actor: ActorDependency,
) -> dict[str, Any]:
    return _lesson_action(connection, review_id, lesson_id, action, actor, "REJECT")


def _policy_action(
    connection: Connection,
    policy_id: UUID,
    action: HumanAction,
    actor: HumanActor,
    operation: Literal["activate", "rollback"],
) -> dict[str, Any]:
    repository = PostgresPolicyRepository(connection, bootstrap_active_versions={})
    service = PolicyPromotionService(repository)
    try:
        result = getattr(service, operation)(
            policy_id, actor=actor, expected_revision=action.expected_revision
        )
    except PolicyPromotionForbidden as exception:
        raise ApiError(403, "FORBIDDEN", str(exception)) from exception
    except NoResultFound as exception:
        raise ApiError(404, "NOT_FOUND", "Policy candidate not found") from exception
    except VersionConflict as exception:
        raise ApiError(409, "VERSION_CONFLICT", str(exception)) from exception
    except (KeyError, ValueError) as exception:
        raise ApiError(409, "INVALID_POLICY_TRANSITION", str(exception)) from exception
    return cast(dict[str, Any], _value(asdict(result)))


@router.post("/policies/{policy_id}/activate")
def activate_policy(
    policy_id: UUID,
    action: HumanAction,
    connection: ConnectionDependency,
    actor: ActorDependency,
) -> dict[str, Any]:
    return _policy_action(connection, policy_id, action, actor, "activate")


@router.post("/policies/{policy_id}/rollback")
def rollback_policy(
    policy_id: UUID,
    action: HumanAction,
    connection: ConnectionDependency,
    actor: ActorDependency,
) -> dict[str, Any]:
    return _policy_action(connection, policy_id, action, actor, "rollback")


@router.get("/evals/runs", response_model=EvalRunPage)
def list_eval_runs(
    decision_time: datetime,
    connection: ConnectionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    audience: Literal["all", "operator"] = "all",
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    query = (
        select(eval_run)
        .where(eval_run.c.created_at <= cutoff)
        .where(_cursor_filter(eval_run.c.created_at, eval_run.c.id, cursor))
    )
    if audience == "operator":
        query = query.where(
            select(eval_metric.c.eval_run_id)
            .where(
                eval_metric.c.eval_run_id == eval_run.c.id,
                eval_metric.c.created_at <= cutoff,
            )
            .exists(),
            select(regression_gate_result.c.eval_run_id)
            .where(
                regression_gate_result.c.eval_run_id == eval_run.c.id,
                regression_gate_result.c.created_at <= cutoff,
            )
            .exists(),
        )
    rows = (
        connection.execute(
            query.order_by(eval_run.c.created_at.desc(), eval_run.c.id.desc()).limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items, next_cursor = _page(rows, limit, "created_at")
    return {"decision_time": cutoff, "items": items, "next_cursor": next_cursor}


@router.get("/evals/runs/{eval_run_id}", response_model=EvalRunDetail)
def get_eval_run(
    eval_run_id: UUID,
    decision_time: datetime,
    connection: ConnectionDependency,
) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    run = (
        connection.execute(
            select(eval_run).where(
                eval_run.c.id == eval_run_id,
                eval_run.c.created_at <= cutoff,
            )
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise ApiError(404, "NOT_FOUND", f"Evaluation run {eval_run_id} not found")
    metrics = (
        connection.execute(
            select(
                eval_metric.c.metric_name,
                eval_metric.c.metric_value,
                eval_metric.c.case_ids,
                eval_metric.c.case_hashes,
            )
            .where(eval_metric.c.eval_run_id == eval_run_id)
            .where(eval_metric.c.created_at <= cutoff)
            .order_by(eval_metric.c.metric_name)
        )
        .mappings()
        .all()
    )
    gates = (
        connection.execute(
            select(
                regression_gate_result.c.metric_name,
                regression_gate_result.c.comparison,
                regression_gate_result.c.threshold,
                regression_gate_result.c.observed,
                regression_gate_result.c.passed,
                regression_gate_result.c.reason,
            )
            .where(regression_gate_result.c.eval_run_id == eval_run_id)
            .where(regression_gate_result.c.created_at <= cutoff)
            .order_by(regression_gate_result.c.metric_name)
        )
        .mappings()
        .all()
    )
    return {
        "decision_time": cutoff,
        "run": _row(run),
        "metrics": [_row(row) for row in metrics],
        "gates": [_row(row) for row in gates],
    }
