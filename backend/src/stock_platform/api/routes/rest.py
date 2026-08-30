from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import Connection, and_, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoResultFound

from stock_platform.api.dependencies import get_connection, get_human_actor, get_settings
from stock_platform.api.schemas.errors import ApiError
from stock_platform.api.schemas.rest import (
    DataQualityResponse,
    HumanAction,
    MarketDataResponse,
    PortfolioRunRequest,
    ProviderHealthResponse,
    ResearchRunRequest,
    RunResponse,
    WatchlistPatch,
    WatchlistRequest,
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
    data_quality_observation,
    ingestion_job,
    investment_thesis,
    paper_fill,
    paper_order,
    portfolio_nav,
    raw_data_object,
    research_opinion,
    security,
    security_identifier_version,
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


def _coverage(settings: Settings) -> MarketDataCoverage:
    configured = settings.alpaca_entitlement_coverage or ""
    return (
        MarketDataCoverage.SIP if "SIP" in configured.upper().split(",") else MarketDataCoverage.IEX
    )


def _market_record(record: Any) -> dict[str, Any]:
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
                **record.payload,
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
    latest_quality = (
        connection.execute(
            select(
                data_quality_observation.c.status,
                data_quality_observation.c.observed_at,
            )
            .where(
                data_quality_observation.c.provider == "ALPACA",
                data_quality_observation.c.dataset == "price_bars",
                data_quality_observation.c.coverage == coverage.value,
            )
            .order_by(data_quality_observation.c.observed_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    latest_quality_status = latest_quality["status"] if latest_quality else None
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
        datetime.now(UTC) - latest_quality["observed_at"] if latest_quality is not None else None
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
            },
            "alpaca": {
                "configured": alpaca_configured,
                "mode": "read_only" if alpaca_configured else "unavailable",
                "status": alpaca_status,
                "coverage": settings.alpaca_entitlement_coverage,
                "latest_job_state": latest_job,
                "latest_quality_status": latest_quality_status,
            },
            "fmp": {
                "configured": bool(settings.fmp_api_key),
                "mode": "read_only" if settings.fmp_api_key else "unavailable",
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


@router.get("/research-runs/{run_id}", response_model=RunResponse)
def get_research_run(run_id: UUID, connection: ConnectionDependency) -> RunResponse:
    row = (
        connection.execute(select(agent_run).where(agent_run.c.id == run_id))
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


@router.get("/research-runs/{run_id}/report")
def get_research_report(run_id: UUID, connection: ConnectionDependency) -> dict[str, Any]:
    row = (
        connection.execute(
            select(investment_thesis, research_opinion.c.value.label("opinion"))
            .outerjoin(research_opinion, research_opinion.c.thesis_id == investment_thesis.c.id)
            .where(investment_thesis.c.run_id == run_id)
            .order_by(investment_thesis.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Research report not found")
    return _row(row)


@router.get("/stocks/{symbol}/research")
def get_stock_research(
    symbol: str, connection: ConnectionDependency, decision_time: datetime
) -> list[dict[str, Any]]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    rows = (
        connection.execute(
            select(investment_thesis, research_opinion.c.value.label("opinion"))
            .outerjoin(
                research_opinion,
                and_(
                    research_opinion.c.thesis_id == investment_thesis.c.id,
                    research_opinion.c.created_at <= cutoff,
                ),
            )
            .where(
                investment_thesis.c.symbol == _symbol(symbol),
                investment_thesis.c.as_of <= cutoff,
                investment_thesis.c.created_at <= cutoff,
            )
            .order_by(investment_thesis.c.as_of.desc())
        )
        .mappings()
        .all()
    )
    return [_row(row) for row in rows]


@router.get("/alerts")
def list_alerts(connection: ConnectionDependency) -> list[dict[str, Any]]:
    return [
        _row(row)
        for row in connection.execute(
            select(alert_event).order_by(alert_event.c.event_time.desc())
        ).mappings()
    ]


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


@router.get("/portfolio")
def get_portfolio(connection: ConnectionDependency, decision_time: datetime) -> dict[str, Any]:
    cutoff = _aware_query_time(decision_time, "decision_time")
    latest_nav = (
        connection.execute(
            select(portfolio_nav)
            .where(
                portfolio_nav.c.event_time <= cutoff,
                portfolio_nav.c.available_at <= cutoff,
            )
            .order_by(portfolio_nav.c.event_time.desc(), portfolio_nav.c.available_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return {"latest_nav": _row(latest_nav) if latest_nav else None, "trading": "paper_only"}


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


@router.get("/portfolio/orders")
def list_orders(connection: ConnectionDependency) -> list[dict[str, Any]]:
    return [
        _row(row)
        for row in connection.execute(
            select(paper_order).order_by(paper_order.c.created_at.desc())
        ).mappings()
    ]


@router.get("/portfolio/fills")
def list_fills(connection: ConnectionDependency) -> list[dict[str, Any]]:
    return [
        _row(row)
        for row in connection.execute(
            select(paper_fill).order_by(paper_fill.c.filled_at.desc())
        ).mappings()
    ]


@router.get("/weekly-reviews")
def list_weekly_reviews(connection: ConnectionDependency) -> list[dict[str, Any]]:
    return [
        _row(row)
        for row in connection.execute(
            select(weekly_review_run).order_by(weekly_review_run.c.created_at.desc())
        ).mappings()
    ]


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


@router.get("/evals/runs")
def list_eval_runs() -> list[dict[str, Any]]:
    return []


@router.get("/evals/runs/{eval_run_id}")
def get_eval_run(eval_run_id: UUID) -> dict[str, Any]:
    raise ApiError(404, "NOT_FOUND", f"Evaluation run {eval_run_id} not found")
