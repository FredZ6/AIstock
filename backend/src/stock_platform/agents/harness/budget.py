"""Deterministic execution budgets, loop detection, and progress limits."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from stock_platform.agents.harness.checkpoint import InMemoryCheckpointStore
from stock_platform.agents.harness.trace import TraceRecorder
from stock_platform.domain.common.errors import BudgetExceeded
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.observability.metrics import platform_metrics


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    llm_calls: int = 10
    tool_calls: int = 16
    tokens: int = 50_000
    reflections: int = 1
    wall_time: timedelta = timedelta(minutes=5)

    def __post_init__(self) -> None:
        if min(self.llm_calls, self.tool_calls, self.tokens, self.reflections) < 0:
            raise ValueError("budget limits cannot be negative")
        if self.wall_time <= timedelta(0):
            raise ValueError("wall_time must be positive")


@dataclass(slots=True)
class BudgetState:
    llm_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0
    reflections: int = 0
    consecutive_no_progress: int = 0
    last_tool_fingerprint: str | None = None


class ExecutionController:
    def __init__(
        self,
        *,
        run_id: str,
        limits: BudgetLimits,
        checkpoints: InMemoryCheckpointStore,
        trace: TraceRecorder,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._run_id = run_id
        self._limits = limits
        self._checkpoints = checkpoints
        self._trace = trace
        self._clock = clock or (lambda: datetime.now(UTC))
        self._started_at = require_aware(self._clock())
        self.state = BudgetState()

    def _snapshot(self, *, status: str = "RUNNING", reason: str | None = None) -> dict[str, object]:
        snapshot: dict[str, object] = {
            "status": status,
            "llm_calls": self.state.llm_calls,
            "tool_calls": self.state.tool_calls,
            "tokens": self.state.tokens,
            "reflections": self.state.reflections,
            "consecutive_no_progress": self.state.consecutive_no_progress,
        }
        if reason is not None:
            snapshot["reason"] = reason
        return snapshot

    def _save(self, event_type: str, payload: dict[str, object]) -> None:
        self._trace.record(event_type, payload)
        self._checkpoints.save(self._run_id, self._snapshot(), saved_at=self._clock())

    def _exhaust(self, reason: str) -> None:
        payload = {"reason": reason}
        self._trace.record("run.budget_exhausted", payload)
        self._checkpoints.save(
            self._run_id,
            self._snapshot(status="BUDGET_EXHAUSTED", reason=reason),
            saved_at=self._clock(),
        )
        raise BudgetExceeded(reason)

    def check_deadline(self) -> None:
        now = require_aware(self._clock())
        if now - self._started_at > self._limits.wall_time:
            self._exhaust("wall_time")

    def record_llm_call(self, *, tokens: int) -> None:
        self.check_deadline()
        if tokens < 0:
            raise ValueError("tokens cannot be negative")
        if self.state.llm_calls + 1 > self._limits.llm_calls:
            self._exhaust("llm_calls")
        if self.state.tokens + tokens > self._limits.tokens:
            self._exhaust("tokens")
        self.state.llm_calls += 1
        self.state.tokens += tokens
        platform_metrics.observe_cost(kind="tokens", amount=tokens)
        self._save("llm.completed", {"tokens": tokens})

    def record_tool_result(self, fingerprint: str, *, made_progress: bool) -> None:
        self.check_deadline()
        if self.state.tool_calls + 1 > self._limits.tool_calls:
            self._exhaust("tool_calls")

        repeated_without_progress = (
            not made_progress and fingerprint == self.state.last_tool_fingerprint
        )
        self.state.tool_calls += 1
        self.state.last_tool_fingerprint = fingerprint
        self.state.consecutive_no_progress = (
            0 if made_progress else self.state.consecutive_no_progress + 1
        )

        if repeated_without_progress:
            self._exhaust("repeated_tool")
        if self.state.consecutive_no_progress >= 2:
            self._exhaust("no_progress")
        self._save(
            "tool.completed",
            {"fingerprint": fingerprint, "made_progress": made_progress},
        )

    def record_reflection(self) -> None:
        self.check_deadline()
        if self.state.reflections + 1 > self._limits.reflections:
            self._exhaust("reflections")
        self.state.reflections += 1
        self._save("reflection.completed", {"count": self.state.reflections})
