"""Explicit human approval records; agents cannot self-approve."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from stock_platform.domain.common.time import require_aware


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    run_id: str
    action: str
    reason: str
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    actor: str
    decided_at: datetime


class HumanApprovalGateway:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._requests: dict[str, ApprovalRequest] = {}
        self._decisions: list[ApprovalDecision] = []

    @property
    def decisions(self) -> tuple[ApprovalDecision, ...]:
        return tuple(self._decisions)

    def request(self, run_id: str, action: str, reason: str) -> ApprovalRequest:
        request = ApprovalRequest(
            id=str(uuid4()),
            run_id=run_id,
            action=action,
            reason=reason,
            requested_at=require_aware(self._clock()),
        )
        self._requests[request.id] = request
        return request

    def decide(self, request_id: str, *, approved: bool, actor: str) -> ApprovalDecision:
        if not actor.startswith("human:"):
            raise PermissionError("approval actor must be an authenticated human")
        if request_id not in self._requests:
            raise KeyError("unknown approval request")
        if any(decision.request_id == request_id for decision in self._decisions):
            raise ValueError("approval request already decided")
        decision = ApprovalDecision(
            request_id=request_id,
            approved=approved,
            actor=actor,
            decided_at=require_aware(self._clock()),
        )
        self._decisions.append(decision)
        return decision
