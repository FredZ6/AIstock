"""Immutable inputs that define one bounded agent run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware


@dataclass(frozen=True, slots=True)
class PolicyVersions:
    research_scoring: str
    risk: str
    execution: str
    confidence: str
    prompt: str
    model: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in self.as_tuple()):
            raise ValueError("all policy, prompt, and model versions are required")

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.research_scoring,
            self.risk,
            self.execution,
            self.confidence,
            self.prompt,
            self.model,
        )


@dataclass(frozen=True, slots=True)
class TaskSpecification:
    objective: str
    symbols: tuple[str, ...]
    decision_time: datetime
    data_cutoff: datetime
    allowed_tools: frozenset[str]
    budgets: BudgetLimits
    output_schema: str
    completion_rules: frozenset[str]
    policy_versions: PolicyVersions

    def __post_init__(self) -> None:
        decision_time = require_aware(self.decision_time)
        data_cutoff = require_aware(self.data_cutoff)
        if data_cutoff > decision_time:
            raise ValueError("data_cutoff cannot be after decision_time")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if not self.output_schema.strip():
            raise ValueError("output_schema is required")
        if not self.completion_rules:
            raise ValueError("at least one completion rule is required")
        object.__setattr__(self, "symbols", tuple(str(Symbol(symbol)) for symbol in self.symbols))
