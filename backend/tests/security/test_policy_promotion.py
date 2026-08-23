from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import SecretStr
from stock_platform.api.dependencies import authenticate_human_actor
from stock_platform.api.schemas.errors import ApiError
from stock_platform.application.learning.promotion import (
    HumanActor,
    InMemoryPolicyRepository,
    PolicyPromotionForbidden,
    PolicyPromotionService,
)
from stock_platform.domain.learning.policy import PolicyCandidate
from stock_platform.settings import Settings


def test_unauthenticated_or_agent_promotion_returns_403_and_is_audited() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    candidate = PolicyCandidate(
        id=uuid4(),
        policy_kind="RISK",
        version="risk-v2",
        base_version="risk-v1",
        lesson_ids=(uuid4(),),
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    with pytest.raises(PolicyPromotionForbidden) as denied:
        service.approve(
            candidate, actor=HumanActor("weekly-agent", authenticated=False), expected_revision=0
        )

    assert denied.value.status_code == 403
    assert repository.audit_events[-1].action == "DENY_APPROVE"
    assert repository.active_version("RISK") == "risk-v1"


def test_authenticated_non_human_actor_still_cannot_promote() -> None:
    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    candidate = PolicyCandidate(
        id=uuid4(),
        policy_kind="RISK",
        version="risk-v2",
        base_version="risk-v1",
        lesson_ids=(uuid4(),),
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    with pytest.raises(PolicyPromotionForbidden) as denied:
        service.approve(
            candidate,
            actor=HumanActor("automation-42", authenticated=True, is_human=False),
            expected_revision=0,
        )

    assert denied.value.status_code == 403
    assert repository.audit_events[-1].action == "DENY_APPROVE"


def test_human_actor_requires_accountable_identity() -> None:
    with pytest.raises(ValueError, match="actor id"):
        HumanActor("   ", authenticated=True)


def test_admin_authentication_is_server_configured_and_constant_time_compared() -> None:
    settings = Settings(
        admin_api_token=SecretStr("fixture-admin-token"),
        admin_actor_id="reviewer-42",
    )

    actor = authenticate_human_actor(settings, "Bearer fixture-admin-token")

    assert actor == HumanActor("reviewer-42", authenticated=True, is_human=True)
    with pytest.raises(ApiError) as denied:
        authenticate_human_actor(settings, "Bearer wrong")
    assert denied.value.status_code == 403


def test_partial_admin_identity_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="configured together"):
        Settings(admin_api_token=SecretStr("token"))
