from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from stock_platform.application.learning.promotion import (
    HumanActor,
    InMemoryPolicyRepository,
    PolicyPromotionService,
    VersionConflict,
)
from stock_platform.domain.learning.policy import PolicyCandidate, PolicyStatus

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def candidate(version: str = "risk-v2") -> PolicyCandidate:
    return PolicyCandidate(
        id=uuid4(),
        policy_kind="RISK",
        version=version,
        base_version="risk-v1",
        lesson_ids=(uuid4(),),
        created_at=NOW,
    )


def test_human_can_approve_activate_reject_and_rollback_with_audit() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    human = HumanActor("human-42", authenticated=True)
    approved = service.approve(candidate(), actor=human, expected_revision=0)
    active = service.activate(approved.id, actor=human, expected_revision=1)
    rolled_back = service.rollback(active.id, actor=human, expected_revision=2)
    rejected = service.reject(candidate("risk-v3"), actor=human, expected_revision=3)

    assert approved.status is PolicyStatus.APPROVED
    assert active.status is PolicyStatus.ACTIVE
    assert rolled_back.status is PolicyStatus.ROLLED_BACK
    assert rejected.status is PolicyStatus.REJECTED
    assert repository.active_version("RISK") == "risk-v1"
    assert [event.action for event in repository.audit_events] == [
        "APPROVE",
        "ACTIVATE",
        "ROLLBACK",
        "REJECT",
    ]


def test_concurrent_promotion_uses_compare_and_swap_revision() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    human = HumanActor("human-42", authenticated=True)
    service.approve(candidate(), actor=human, expected_revision=0)

    with pytest.raises(VersionConflict):
        service.approve(candidate("risk-v3"), actor=human, expected_revision=0)


def test_policy_state_machine_rejects_reapproval_and_rejecting_active_policy() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    human = HumanActor("human-42", authenticated=True)
    approved = service.approve(candidate(), actor=human, expected_revision=0)

    with pytest.raises(ValueError, match="candidate"):
        service.approve(approved, actor=human, expected_revision=1)

    active = service.activate(approved.id, actor=human, expected_revision=1)
    with pytest.raises(ValueError, match="candidate"):
        service.reject(active, actor=human, expected_revision=2)
    assert repository.active_version("RISK") == "risk-v2"


def test_real_concurrent_approvals_allow_exactly_one_cas_winner() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    human = HumanActor("human-42", authenticated=True)
    barrier = Barrier(2)

    def approve(version: str) -> str:
        barrier.wait()
        try:
            service.approve(candidate(version), actor=human, expected_revision=0)
        except VersionConflict:
            return "CONFLICT"
        return "APPROVED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(approve, ("risk-v2", "risk-v3")))

    assert sorted(results) == ["APPROVED", "CONFLICT"]
