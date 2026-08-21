"""Versioned policy candidates and immutable promotion audit facts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.time import require_aware


class PolicyStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True, slots=True)
class PolicyCandidate:
    id: UUID
    policy_kind: str
    version: str
    base_version: str
    lesson_ids: tuple[UUID, ...]
    created_at: datetime
    status: PolicyStatus = PolicyStatus.CANDIDATE

    def __post_init__(self) -> None:
        if (
            not self.policy_kind.strip()
            or not self.version.strip()
            or not self.base_version.strip()
        ):
            raise ValueError("policy kind and versions are required")
        if not self.lesson_ids:
            raise ValueError("policy candidate requires lessons")
        object.__setattr__(self, "created_at", require_aware(self.created_at).astimezone(UTC))
        object.__setattr__(self, "status", PolicyStatus(self.status))


@dataclass(frozen=True, slots=True)
class PromotionAuditEvent:
    candidate_id: UUID
    actor_id: str
    action: str
    outcome: str
    expected_revision: int
    observed_revision: int
    created_at: datetime
