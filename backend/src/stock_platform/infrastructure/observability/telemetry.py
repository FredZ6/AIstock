"""Structured logging and loopback-only OpenTelemetry with safe defaults."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from stock_platform.infrastructure.observability.context import (
    current_correlation,
    maybe_current_correlation,
)
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


class OperationalTelemetry:
    """One correlated trace/log boundary used by real application paths."""

    def __init__(
        self,
        *,
        exporter: SpanExporter | None = None,
        log_sink: Callable[[str], None] | None = None,
    ) -> None:
        provider = TracerProvider()
        if exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        self.tracer = provider.get_tracer("stock_platform")
        self._log_sink = log_sink or logging.getLogger("stock_platform.operations").info

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, str] | None = None) -> Iterator[Any]:
        with self.tracer.start_as_current_span(name) as span:
            context = maybe_current_correlation()
            if context is not None:
                span.set_attribute("correlation.id", str(context.correlation_id))
                if context.run_id is not None:
                    span.set_attribute("run.id", str(context.run_id))
            for key, value in (attributes or {}).items():
                span.set_attribute(key, value)
            yield span

    def log(self, event: str, fields: dict[str, object]) -> None:
        self._log_sink(json.dumps(JsonLogFormatter().format_event(event, fields), sort_keys=True))

    @classmethod
    def loopback_from_environment(cls) -> OperationalTelemetry:
        enabled = os.getenv("OTEL_EXPORT_ENABLED", "false").lower() == "true"
        exporter = OTLPSpanExporter(endpoint="http://127.0.0.1:4318/v1/traces") if enabled else None
        return cls(exporter=exporter)


def create_in_memory_tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """Construct an isolated tracer for deterministic tests and fixture-mode diagnostics."""

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("stock_platform"), exporter


operational_telemetry = OperationalTelemetry.loopback_from_environment()
