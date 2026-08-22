from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoResultFound

from stock_platform.api.dependencies import get_connection, get_human_actor, get_settings
from stock_platform.api.schemas.errors import ApiError
from stock_platform.api.schemas.rest import (
    HumanAction,
    PortfolioRunRequest,
    ResearchRunRequest,
    RunResponse,
    WatchlistPatch,
    WatchlistRequest,
)
from stock_platform.application.learning.promotion import (
    HumanActor,
    PolicyPromotionForbidden,
    PolicyPromotionService,
    PostgresPolicyRepository,
    VersionConflict,
)
from stock_platform.application.runs import (
    IdempotencyConflict,
    RunAdmissionLimit,
    admit_run,
    append_run_event,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    alert_event,
    candidate_lesson,
    decision_outcome,
    error_attribution,
    investment_thesis,
    lesson_approval,
    paper_fill,
    paper_order,
    portfolio_nav,
    research_opinion,
    watchlist_item,
    weekly_review_run,
)
from stock_platform.infrastructure.observability.context import current_correlation
from stock_platform.settings import Settings

router = APIRouter(prefix="/api/v1")
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


@router.get("/providers/health")
def provider_health(settings: SettingsDependency) -> dict[str, Any]:
    return {
        "mode": settings.environment,
        "providers": {
            "sec": {"configured": bool(settings.sec_user_agent), "mode": "fixture"},
            "alpaca": {"configured": bool(settings.alpaca_data_key), "mode": "fixture"},
            "fmp": {"configured": bool(settings.fmp_api_key), "mode": "fixture"},
        },
    }


@router.get("/watchlist")
def list_watchlist(connection: ConnectionDependency) -> list[dict[str, Any]]:
    rows = connection.execute(select(watchlist_item).order_by(watchlist_item.c.symbol)).mappings()
    return [_row(row) for row in rows]


@router.post("/watchlist", status_code=201)
def add_watchlist(request: WatchlistRequest, connection: ConnectionDependency) -> dict[str, Any]:
    row = (
        connection.execute(
            pg_insert(watchlist_item)
            .values(**request.model_dump())
            .on_conflict_do_update(
                index_elements=[watchlist_item.c.symbol],
                set_={
                    "daily_research": request.daily_research,
                    "intraday_monitoring": request.intraday_monitoring,
                    "thresholds": request.thresholds,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(watchlist_item)
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
            .returning(watchlist_item)
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
    return _create_run(
        connection,
        settings,
        response,
        run_type="RESEARCH",
        idempotency_key=idempotency_key,
        payload=request.model_dump(mode="json"),
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
def get_stock_research(symbol: str, connection: ConnectionDependency) -> list[dict[str, Any]]:
    rows = (
        connection.execute(
            select(investment_thesis, research_opinion.c.value.label("opinion"))
            .outerjoin(research_opinion, research_opinion.c.thesis_id == investment_thesis.c.id)
            .where(investment_thesis.c.symbol == _symbol(symbol))
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
def get_portfolio(connection: ConnectionDependency) -> dict[str, Any]:
    latest_nav = (
        connection.execute(
            select(portfolio_nav).order_by(portfolio_nav.c.event_time.desc()).limit(1)
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
    return _create_run(
        connection,
        settings,
        response,
        run_type="PORTFOLIO",
        idempotency_key=idempotency_key,
        payload=request.model_dump(mode="json"),
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
    exists = connection.execute(
        select(candidate_lesson.c.id)
        .join(error_attribution, candidate_lesson.c.attribution_id == error_attribution.c.id)
        .join(decision_outcome, error_attribution.c.outcome_id == decision_outcome.c.id)
        .where(
            candidate_lesson.c.id == lesson_id, decision_outcome.c.weekly_review_run_id == review_id
        )
    ).scalar_one_or_none()
    if exists is None:
        raise ApiError(404, "NOT_FOUND", "Lesson not found in weekly review")
    row = (
        connection.execute(
            insert(lesson_approval)
            .values(
                lesson_id=lesson_id,
                actor_id=actor.id,
                action=disposition,
                rationale=action.rationale,
            )
            .returning(lesson_approval)
        )
        .mappings()
        .one()
    )
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
