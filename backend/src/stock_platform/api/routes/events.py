from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse

from stock_platform.api.routes.rest import ConnectionDependency
from stock_platform.api.schemas.errors import ApiError
from stock_platform.application.events.sse import InvalidLastEventId, load_events, stream_events
from stock_platform.infrastructure.db.models.tables import agent_run

router = APIRouter(prefix="/api/v1")


@router.get("/events")
def events(
    connection: ConnectionDependency,
    run_id: Annotated[UUID, Query()],
    last_event_id: Annotated[UUID | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    if (
        connection.execute(
            agent_run.select().with_only_columns(agent_run.c.id).where(agent_run.c.id == run_id)
        ).scalar_one_or_none()
        is None
    ):
        raise ApiError(404, "NOT_FOUND", "Agent run not found")
    try:
        load_events(connection, run_id, last_event_id)
    except InvalidLastEventId as exception:
        raise ApiError(
            409, "INVALID_LAST_EVENT_ID", "Last-Event-ID does not belong to this run"
        ) from exception
    return StreamingResponse(
        stream_events(connection, run_id, last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
