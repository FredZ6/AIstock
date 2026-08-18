"""Append-only in-memory checkpoint contract used by the execution harness."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from stock_platform.domain.common.time import require_aware


@dataclass(frozen=True, slots=True)
class Checkpoint:
    run_id: str
    sequence: int
    saved_at: datetime
    state: Mapping[str, object]


class InMemoryCheckpointStore:
    """Deterministic test implementation; durable storage is wired in later tasks."""

    def __init__(self) -> None:
        self._records: dict[str, list[Checkpoint]] = {}

    def save(
        self,
        run_id: str,
        state: Mapping[str, object],
        *,
        saved_at: datetime | None = None,
    ) -> Checkpoint:
        records = self._records.setdefault(run_id, [])
        checkpoint = Checkpoint(
            run_id=run_id,
            sequence=len(records) + 1,
            saved_at=require_aware(saved_at or datetime.now(UTC)),
            state=MappingProxyType(dict(state)),
        )
        records.append(checkpoint)
        return checkpoint

    def latest(self, run_id: str) -> Checkpoint | None:
        records = self._records.get(run_id, [])
        return records[-1] if records else None
