"""Structured logging and OpenTelemetry construction with safe defaults."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from stock_platform.infrastructure.observability.context import current_correlation
from stock_platform.infrastructure.observability.redaction import redact


class JsonLogFormatter:
    """Produce JSON-ready structured records; serialization belongs to the log handler."""

    def format_event(self, event: str, fields: dict[str, object]) -> dict[str, Any]:
        context = current_correlation()
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "correlation_id": str(context.correlation_id),
            "run_id": str(context.run_id) if context.run_id is not None else None,
            "fields": redact(fields),
        }


def create_in_memory_tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """Construct an isolated tracer for deterministic tests and fixture-mode diagnostics."""

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("stock_platform"), exporter
