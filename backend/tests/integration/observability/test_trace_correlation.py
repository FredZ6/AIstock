from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, insert, select
from stock_platform.api.main import app
from stock_platform.application.events.sse import load_events
from stock_platform.application.runs import admit_run, append_run_event, execute_run
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run, tool_call
from stock_platform.infrastructure.observability.context import (
    CorrelationContext,
    correlation_scope,
    current_correlation,
)
from stock_platform.infrastructure.observability.metrics import PlatformMetrics
from stock_platform.infrastructure.observability.telemetry import (
    JsonLogFormatter,
    OperationalTelemetry,
    create_in_memory_tracer,
)


def test_correlation_context_propagates_across_protocol_boundaries() -> None:
    correlation_id = uuid4()
    context = CorrelationContext(correlation_id=correlation_id, run_id=uuid4())

    with correlation_scope(context):
        headers = current_correlation().to_headers()
        restored = CorrelationContext.from_headers(headers)

    assert restored == context
    assert UUID(headers["x-correlation-id"]) == correlation_id


def test_invalid_correlation_headers_are_rejected() -> None:
    with pytest.raises(ValueError, match="correlation"):
        CorrelationContext.from_headers({"x-correlation-id": "not-a-uuid"})


def test_platform_metrics_expose_required_families_without_unbounded_labels() -> None:
    metrics = PlatformMetrics()

    metrics.observe_request(service="api", route="/api/v1/research-runs", status="202")
    metrics.observe_provider(provider="fixture", outcome="ok")
    metrics.observe_tool(tool="get_prices", outcome="completed")
    metrics.observe_graph(graph="research", node="synthesize", outcome="completed")
    metrics.observe_alert(rule="market_anomaly", outcome="created")
    metrics.set_queue(queue="research", depth=2)
    metrics.observe_cost(kind="tokens", amount=12)
    metrics.observe_evaluation(suite="offline", outcome="passed")

    output = metrics.render()
    for family in (
        "platform_service_requests_total",
        "platform_provider_calls_total",
        "platform_tool_calls_total",
        "platform_graph_nodes_total",
        "platform_alerts_total",
        "platform_queue_depth",
        "platform_cost_total",
        "platform_evaluation_runs_total",
    ):
        assert family in output
    assert "symbol=" not in output
    assert "run_id=" not in output


def test_platform_metrics_reject_unbounded_label_dimensions() -> None:
    metrics = PlatformMetrics()
    with pytest.raises(ValueError, match="unbounded"):
        metrics.observe("service_requests", {"run_id": "run-1"})
    with pytest.raises(ValueError, match="unbounded"):
        metrics.observe("provider_calls", {"symbol": "NVDA"})


def test_http_response_and_error_envelope_keep_the_request_correlation_id() -> None:
    client = TestClient(app)
    correlation_id = uuid4()

    healthy = client.get("/api/v1/health", headers={"x-correlation-id": str(correlation_id)})
    missing = client.get("/api/v1/not-a-route", headers={"x-correlation-id": str(correlation_id)})

    assert healthy.headers["x-correlation-id"] == str(correlation_id)
    assert missing.headers["x-correlation-id"] == str(correlation_id)
    assert missing.json()["error"]["correlation_id"] == str(correlation_id)


def test_invalid_inbound_correlation_id_uses_locked_error_envelope() -> None:
    response = TestClient(app).get("/api/v1/health", headers={"x-correlation-id": "not-a-uuid"})

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "INVALID_CORRELATION_ID"
    assert payload["retryable"] is False
    assert payload["details"] == {}
    assert UUID(payload["correlation_id"]) == UUID(response.headers["x-correlation-id"])


def test_structured_logs_and_spans_share_redacted_correlation_attributes() -> None:
    correlation_id = uuid4()
    context = CorrelationContext(correlation_id=correlation_id, run_id=uuid4())
    formatter = JsonLogFormatter()
    tracer, exporter = create_in_memory_tracer()

    with correlation_scope(context), tracer.start_as_current_span("provider.call") as span:
        span.set_attribute("correlation.id", str(current_correlation().correlation_id))
        record = formatter.format_event("provider.call", {"api_key": "secret", "outcome": "ok"})

    assert record["correlation_id"] == str(correlation_id)
    assert record["fields"] == {"api_key": "[REDACTED]", "outcome": "ok"}
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes is not None
    assert spans[0].attributes["correlation.id"] == str(correlation_id)


def test_operational_telemetry_emits_correlated_redacted_logs_and_spans() -> None:
    exporter = InMemorySpanExporter()
    logs: list[str] = []
    telemetry = OperationalTelemetry(exporter=exporter, log_sink=logs.append)
    context = CorrelationContext(uuid4(), uuid4())

    with correlation_scope(context), telemetry.span("provider.fetch", {"provider": "fixture"}):
        telemetry.log("provider.fetch", {"private_key": "secret", "outcome": "ok"})

    span = exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["correlation.id"] == str(context.correlation_id)
    assert span.attributes["run.id"] == str(context.run_id)
    assert '"private_key": "[REDACTED]"' in logs[0]


def test_run_db_events_and_sse_replay_keep_one_correlation_path(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    correlation_id = uuid4()
    decision_time = datetime(2026, 8, 23, 4, tzinfo=UTC)

    with engine.begin() as connection:
        admitted = admit_run(
            connection,
            max_active_runs=2,
            run_type="RESEARCH",
            idempotency_key=f"correlation-{correlation_id}",
            payload={"symbol": "NVDA"},
            symbol="NVDA",
            decision_time=decision_time,
            data_cutoff=decision_time,
            correlation_id=correlation_id,
        )
        append_run_event(connection, admitted.id, "run.queued", {"status": "QUEUED"})

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(agent_run.c.correlation_id).where(agent_run.c.id == admitted.id)
            ).scalar_one()
            == correlation_id
        )
        event = load_events(connection, admitted.id)[0]
        assert event["correlation_id"] == correlation_id
    engine.dispose()


def test_worker_graph_boundary_restores_persisted_correlation_context(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    correlation_id = uuid4()
    decision_time = datetime(2026, 8, 23, 4, tzinfo=UTC)
    with engine.begin() as connection:
        admitted = admit_run(
            connection,
            max_active_runs=2,
            run_type="RESEARCH",
            idempotency_key=f"worker-correlation-{correlation_id}",
            payload={"symbol": "NVDA"},
            symbol="NVDA",
            decision_time=decision_time,
            data_cutoff=decision_time,
            correlation_id=correlation_id,
        )

    observed: list[CorrelationContext] = []

    def work(_connection: object, _row: object, control: object) -> None:
        observed.append(current_correlation())

    assert execute_run(isolated_database_url, admitted.id, "RESEARCH", work) is True
    assert observed == [CorrelationContext(correlation_id, admitted.id)]
    engine.dispose()


def test_0024_backfills_existing_event_and_tool_rows_from_their_run(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "0023_run_execution_guards")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    now = datetime(2026, 8, 23, 4, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"legacy-{run_id}",
                request_hash="b" * 64,
                request_payload={},
                decision_time=now,
                data_cutoff=now,
            )
        )
        connection.execute(
            insert(agent_event).values(run_id=run_id, sequence=1, event_type="legacy", payload={})
        )
        connection.execute(
            insert(tool_call).values(
                run_id=run_id, tool_name="legacy", request_fingerprint="c" * 64
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        run_correlation = connection.execute(
            select(agent_run.c.correlation_id).where(agent_run.c.id == run_id)
        ).scalar_one()
        assert (
            connection.execute(
                select(agent_event.c.correlation_id).where(agent_event.c.run_id == run_id)
            ).scalar_one()
            == run_correlation
        )
        assert (
            connection.execute(
                select(tool_call.c.correlation_id).where(tool_call.c.run_id == run_id)
            ).scalar_one()
            == run_correlation
        )
    engine.dispose()
