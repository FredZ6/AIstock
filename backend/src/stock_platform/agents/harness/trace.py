"""Structured trace events with deterministic sequencing and redaction."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from stock_platform.domain.common.time import require_aware

_SENSITIVE_FRAGMENTS = ("secret", "token", "key", "password", "authorization")


def redact_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                "[REDACTED]"
                if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS)
                else redact_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_payload(item) for item in value]
    if isinstance(value, str) and value.lower().startswith("bearer "):
        return "[REDACTED]"
    return value


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_id: str
    run_id: str
    sequence: int
    event_time: datetime
    type: str
    schema_version: str
    payload: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event_time": self.event_time.isoformat(),
            "type": self.type,
            "schema_version": self.schema_version,
            "payload": dict(self.payload),
        }


class TraceRecorder:
    def __init__(
        self,
        *,
        run_id: str = "run-m2",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def record(self, event_type: str, payload: Mapping[str, object]) -> TraceEvent:
        sequence = len(self._events) + 1
        event = TraceEvent(
            event_id=f"{self._run_id}:{sequence}",
            run_id=self._run_id,
            sequence=sequence,
            event_time=require_aware(self._clock()),
            type=event_type,
            schema_version="1.0",
            payload=MappingProxyType(redact_payload(payload)),
        )
        self._events.append(event)
        return event

    @staticmethod
    def load_contract(name: str) -> dict[str, object]:
        repository_root = Path(__file__).resolve().parents[5]
        value = json.loads((repository_root / "contracts" / "agent-events" / name).read_text())
        if not isinstance(value, dict):
            raise ValueError("agent event contract must be a JSON object")
        return cast(dict[str, object], value)
