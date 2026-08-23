"""Correlation context that can cross HTTP, Celery, MCP, provider, DB, and SSE boundaries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

_CURRENT: ContextVar[CorrelationContext | None] = ContextVar("correlation_context", default=None)


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    correlation_id: UUID
    run_id: UUID | None = None

    def to_headers(self) -> dict[str, str]:
        headers = {"x-correlation-id": str(self.correlation_id)}
        if self.run_id is not None:
            headers["x-run-id"] = str(self.run_id)
        return headers

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> CorrelationContext:
        try:
            correlation_id = UUID(headers["x-correlation-id"])
            run_id_value = headers.get("x-run-id")
            run_id = UUID(run_id_value) if run_id_value else None
        except (KeyError, TypeError, ValueError) as exception:
            raise ValueError("invalid correlation headers") from exception
        return cls(correlation_id=correlation_id, run_id=run_id)


@contextmanager
def correlation_scope(context: CorrelationContext) -> Iterator[None]:
    token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_correlation() -> CorrelationContext:
    context = _CURRENT.get()
    if context is None:
        raise RuntimeError("correlation context is not set")
    return context


def maybe_current_correlation() -> CorrelationContext | None:
    return _CURRENT.get()
