from datetime import UTC, datetime

import pytest
from stock_platform.agents.harness.approval import HumanApprovalGateway
from stock_platform.agents.harness.completion import CompletionVerifier
from stock_platform.agents.harness.failure import FailureCategory, FailureClassifier
from stock_platform.domain.common.errors import ProviderUnavailable, ToolPolicyDenied

NOW = datetime(2026, 8, 18, 6, tzinfo=UTC)


def test_failure_classifier_distinguishes_retryable_policy_evidence_and_defects() -> None:
    classifier = FailureClassifier()

    assert classifier.classify(ProviderUnavailable("timeout")) is FailureCategory.RETRYABLE
    assert classifier.classify(ToolPolicyDenied("denied")) is FailureCategory.POLICY_DENIED
    assert classifier.classify(ValueError("invalid arguments")) is FailureCategory.INVALID_ARGUMENTS
    assert (
        classifier.classify(LookupError("insufficient evidence"))
        is FailureCategory.INSUFFICIENT_EVIDENCE
    )
    assert classifier.classify(RuntimeError("bug")) is FailureCategory.INTERNAL_DEFECT


def test_human_approval_requires_a_named_human_and_is_auditable() -> None:
    gateway = HumanApprovalGateway(clock=lambda: NOW)
    request = gateway.request("run-m2", "increase_budget", "Need one more provider call")

    with pytest.raises(PermissionError):
        gateway.decide(request.id, approved=True, actor="agent:model")

    decision = gateway.decide(request.id, approved=False, actor="human:fred")
    assert decision.approved is False
    assert decision.actor == "human:fred"
    assert gateway.decisions == (decision,)


def test_completion_verifier_names_missing_rules() -> None:
    result = CompletionVerifier().verify(
        completed=frozenset({"citations_verified"}),
        required=frozenset({"citations_verified", "decision_persisted"}),
    )

    assert result.complete is False
    assert result.missing == ("decision_persisted",)
