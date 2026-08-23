"""Replay authoritative agent events as Server-Sent Events."""

import json
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, select

from stock_platform.agents.harness.trace import redact_payload
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run


class InvalidLastEventId(RuntimeError):
    pass


def load_events(
    connection: Connection, run_id: UUID, after_event_id: UUID | None = None
) -> list[dict[str, Any]]:
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
    connection: Connection,
    run_id: UUID,
    after_event_id: UUID | None = None,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    cursor = after_event_id
    while True:
        events = load_events(connection, run_id, cursor)
        for event in events:
            cursor = event["event_id"]
            yield encode_event(event)
        status = connection.execute(
            select(agent_run.c.status).where(agent_run.c.id == run_id)
        ).scalar_one_or_none()
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return
        sleeper(0.25)
