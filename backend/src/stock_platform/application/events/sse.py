"""Replay authoritative agent events as Server-Sent Events."""

import json
import time
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, select

from stock_platform.agents.harness.trace import redact_payload
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run


class InvalidLastEventId(RuntimeError):
    pass


def load_events(
    connection: Connection,
    run_id: UUID,
    after_event_id: UUID | None = None,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 1000:
        raise ValueError("SSE event batch limit must be between 1 and 1000")
    after_sequence = 0
    if after_event_id is not None:
        after_sequence_value = connection.execute(
            select(agent_event.c.sequence).where(
                agent_event.c.id == after_event_id,
                agent_event.c.run_id == run_id,
            )
        ).scalar_one_or_none()
        if after_sequence_value is None:
            raise InvalidLastEventId
        after_sequence = after_sequence_value
    rows = connection.execute(
        select(agent_event)
        .where(
            agent_event.c.run_id == run_id,
            agent_event.c.sequence > after_sequence,
        )
        .order_by(agent_event.c.sequence)
        .limit(limit)
    ).mappings()
    return [
        {
            "event_id": row["id"],
            "correlation_id": row["correlation_id"],
            "run_id": row["run_id"],
            "sequence": row["sequence"],
            "event_time": row["created_at"],
            "type": row["event_type"],
            "schema_version": "1.0",
            "payload": redact_payload(row["payload"]),
        }
        for row in rows
    ]


def encode_event(event: dict[str, Any]) -> str:
    def serialize(value: Any) -> str:
        if isinstance(value, (UUID, datetime)):
            return value.isoformat() if isinstance(value, datetime) else str(value)
        raise TypeError(f"Cannot serialize {type(value).__name__}")

    data = json.dumps(event, default=serialize, separators=(",", ":"))
    return f"id: {event['event_id']}\nevent: {event['type']}\ndata: {data}\n\n"


def stream_events(
    connect: Callable[[], AbstractContextManager[Connection]],
    run_id: UUID,
    after_event_id: UUID | None = None,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    batch_size: int = 100,
    clock: Callable[[], float] = time.monotonic,
    heartbeat_interval: float = 15.0,
) -> Generator[str, None, None]:
    if heartbeat_interval <= 0:
        raise ValueError("SSE heartbeat interval must be positive")
    cursor = after_event_id
    last_activity = clock()
    while True:
        with connect() as connection:
            events = load_events(connection, run_id, cursor, limit=batch_size)
            status = connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == run_id)
            ).scalar_one_or_none()
        for event in events:
            cursor = event["event_id"]
            yield encode_event(event)
        if events:
            last_activity = clock()
        if status in {"COMPLETED", "FAILED", "CANCELLED"} and len(events) < batch_size:
            return
        if not events:
            now = clock()
            if now - last_activity >= heartbeat_interval:
                yield ": keepalive\n\n"
                last_activity = now
            sleeper(0.25)
