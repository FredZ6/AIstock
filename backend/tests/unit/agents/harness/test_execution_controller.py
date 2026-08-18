from datetime import UTC, datetime, timedelta

import pytest
from stock_platform.agents.harness.budget import BudgetLimits, ExecutionController
from stock_platform.agents.harness.checkpoint import InMemoryCheckpointStore
from stock_platform.agents.harness.trace import TraceRecorder
from stock_platform.domain.common.errors import BudgetExceeded

START = datetime(2026, 8, 18, 6, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def controller(
    *, limits: BudgetLimits | None = None
) -> tuple[ExecutionController, Clock, InMemoryCheckpointStore, TraceRecorder]:
    clock = Clock()
    checkpoints = InMemoryCheckpointStore()
    trace = TraceRecorder(clock=clock)
    execution = ExecutionController(
        run_id="run-m2",
        limits=limits or BudgetLimits(),
        checkpoints=checkpoints,
        trace=trace,
        clock=clock,
    )
    return execution, clock, checkpoints, trace


def test_call_token_deadline_and_single_reflection_limits_are_enforced() -> None:
    execution, clock, _, _ = controller(
        limits=BudgetLimits(
            llm_calls=1,
            tool_calls=1,
            tokens=10,
            reflections=1,
            wall_time=timedelta(seconds=5),
        )
    )

    execution.record_llm_call(tokens=10)
    with pytest.raises(BudgetExceeded, match="llm_calls"):
        execution.record_llm_call(tokens=0)

    execution.record_tool_result("get_price_bars:NVDA", made_progress=True)
    with pytest.raises(BudgetExceeded, match="tool_calls"):
        execution.record_tool_result("get_company_facts:NVDA", made_progress=True)

    execution.record_reflection()
    with pytest.raises(BudgetExceeded, match="reflections"):
        execution.record_reflection()

    clock.now = START + timedelta(seconds=6)
    with pytest.raises(BudgetExceeded, match="wall_time"):
        execution.check_deadline()


def test_repeated_no_progress_action_terminates_with_checkpoint_and_complete_trace() -> None:
    execution, _, checkpoints, trace = controller()

    execution.record_tool_result("get_company_news:NVDA", made_progress=False)
    with pytest.raises(BudgetExceeded, match="repeated_tool"):
        execution.record_tool_result("get_company_news:NVDA", made_progress=False)

    latest = checkpoints.latest("run-m2")
    assert latest is not None
    assert latest.state["status"] == "BUDGET_EXHAUSTED"
    assert latest.state["reason"] == "repeated_tool"
    assert [event.sequence for event in trace.events] == list(range(1, len(trace.events) + 1))
    assert trace.events[-1].type == "run.budget_exhausted"


def test_two_different_steps_without_progress_are_stopped() -> None:
    execution, _, _, _ = controller()

    execution.record_tool_result("get_company_news:NVDA", made_progress=False)
    with pytest.raises(BudgetExceeded, match="no_progress"):
        execution.record_tool_result("get_company_facts:NVDA", made_progress=False)
