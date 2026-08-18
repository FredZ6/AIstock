from datetime import UTC, datetime, timedelta

import jsonschema  # type: ignore[import-untyped]
import pytest
from stock_platform.agents.harness.checkpoint import InMemoryCheckpointStore
from stock_platform.agents.harness.trace import TraceRecorder

NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


def test_checkpoint_store_recovers_latest_monotonic_state() -> None:
    store = InMemoryCheckpointStore()
    store.save("run-m2", {"node": "preflight"}, saved_at=NOW)
    store.save("run-m2", {"node": "planner"}, saved_at=NOW + timedelta(seconds=1))

    latest = store.latest("run-m2")
    assert latest is not None
    assert latest.sequence == 2
    assert latest.state == {"node": "planner"}


def test_trace_is_monotonic_redacted_and_matches_frozen_contract() -> None:
    recorder = TraceRecorder(clock=lambda: NOW)
    first = recorder.record("tool.started", {"tool": "get_company_news", "api_key": "secret"})
    second = recorder.record("tool.completed", {"authorization": "Bearer hidden", "records": 2})

    assert (first.sequence, second.sequence) == (1, 2)
    assert first.payload["api_key"] == "[REDACTED]"
    assert second.payload["authorization"] == "[REDACTED]"

    schema = TraceRecorder.load_contract("agent-event-v1.json")
    jsonschema.validate(first.to_dict(), schema)
    jsonschema.validate(second.to_dict(), schema)


def test_trace_rejects_naive_clock_values() -> None:
    recorder = TraceRecorder(clock=lambda: datetime(2026, 8, 18, 6))
    with pytest.raises(ValueError):
        recorder.record("run.started", {})
