from datetime import UTC, datetime, timedelta

import pytest
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification

NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


def policy_versions() -> PolicyVersions:
    return PolicyVersions(
        research_scoring="research-v1",
        risk="risk-v1",
        execution="execution-v1",
        confidence="confidence-v1",
        prompt="prompt-v1",
        model="fixture-model-v1",
    )


def test_task_specification_freezes_scope_cutoff_tools_budgets_and_versions() -> None:
    specification = TaskSpecification(
        objective="Research the frozen NVDA snapshot",
        symbols=("nvda",),
        decision_time=NOW,
        data_cutoff=NOW - timedelta(minutes=1),
        allowed_tools=frozenset({"get_price_bars", "get_company_facts"}),
        budgets=BudgetLimits(llm_calls=10, tool_calls=16, tokens=50_000),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted", "citations_verified"}),
        policy_versions=policy_versions(),
    )

    assert specification.symbols == ("NVDA",)
    assert specification.allowed_tools == frozenset({"get_price_bars", "get_company_facts"})
    assert specification.policy_versions.confidence == "confidence-v1"

    with pytest.raises((AttributeError, TypeError)):
        specification.objective = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("decision_time", "data_cutoff"),
    [
        (datetime(2026, 8, 18, 6), NOW),
        (NOW, datetime(2026, 8, 18, 5, 59)),
        (NOW, NOW + timedelta(seconds=1)),
    ],
)
def test_task_specification_rejects_naive_or_future_cutoffs(
    decision_time: datetime, data_cutoff: datetime
) -> None:
    with pytest.raises(ValueError):
        TaskSpecification(
            objective="Research NVDA",
            symbols=("NVDA",),
            decision_time=decision_time,
            data_cutoff=data_cutoff,
            allowed_tools=frozenset({"get_price_bars"}),
            budgets=BudgetLimits(),
            output_schema="research-decision-v1",
            completion_rules=frozenset({"decision_persisted"}),
            policy_versions=policy_versions(),
        )
