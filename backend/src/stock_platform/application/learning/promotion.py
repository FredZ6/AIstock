"""Human-only, compare-and-swap policy promotion with denial audit."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import Connection, func, select, update
from sqlalchemy.dialects.postgresql import insert

from stock_platform.domain.learning.policy import (
    PolicyCandidate,
    PolicyStatus,
    PromotionAuditEvent,
)
from stock_platform.infrastructure.db.models.tables import (
    candidate_lesson,
    lesson_approval,
    policy_control,
    policy_promotion_audit,
    replay_run,
)
from stock_platform.infrastructure.db.models.tables import (
    policy_candidate as policy_candidate_table,
)


@dataclass(frozen=True, slots=True)
class HumanActor:
    id: str
    authenticated: bool
    is_human: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("actor id is required")


class PolicyPromotionForbidden(PermissionError):
    status_code = 403


class VersionConflict(RuntimeError):
    pass


class PolicyRepository(Protocol):
    def active_version(self, policy_kind: str) -> str: ...

    def candidate(self, candidate_id: UUID) -> PolicyCandidate: ...

    def transact(
        self,
        *,
        candidate: PolicyCandidate,
        actor: HumanActor,
        action: str,
        expected_revision: int,
        next_status: PolicyStatus,
    ) -> PolicyCandidate: ...

    def deny(
        self, candidate: PolicyCandidate, actor: HumanActor, action: str, expected_revision: int
    ) -> None: ...


class InMemoryPolicyRepository:
    def __init__(self, *, active_versions: dict[str, str]) -> None:
        self._active_versions = dict(active_versions)
        self._candidates: dict[UUID, PolicyCandidate] = {}
        self._revision = 0
        self._lock = RLock()
        self.audit_events: list[PromotionAuditEvent] = []

    @property
    def revision(self) -> int:
        return self._revision

    def active_version(self, policy_kind: str) -> str:
        return self._active_versions[policy_kind]

    def candidate(self, candidate_id: UUID) -> PolicyCandidate:
        return self._candidates[candidate_id]

    def transact(
        self,
        *,
        candidate: PolicyCandidate,
        actor: HumanActor,
        action: str,
        expected_revision: int,
        next_status: PolicyStatus,
    ) -> PolicyCandidate:
        with self._lock:
            if expected_revision != self._revision:
                raise VersionConflict("policy revision changed concurrently")
            prior = self._candidates.get(candidate.id, candidate)
            if action in {"APPROVE", "REJECT"} and prior.status is not PolicyStatus.CANDIDATE:
                raise ValueError("only candidate policies can be approved or rejected")
            active_version = self._active_versions[prior.policy_kind]
            if action == "APPROVE" and active_version != prior.base_version:
                raise VersionConflict("candidate base version is no longer active")
            updated = replace(prior, status=next_status)
            if action == "ACTIVATE":
                if prior.status is not PolicyStatus.APPROVED:
                    raise ValueError("only approved policy candidates can be activated")
                if self._active_versions[prior.policy_kind] != prior.base_version:
                    raise VersionConflict("active policy no longer matches candidate base version")
                self._active_versions[prior.policy_kind] = prior.version
            elif action == "ROLLBACK":
                if prior.status is not PolicyStatus.ACTIVE:
                    raise ValueError("only active policy candidates can be rolled back")
                if self._active_versions[prior.policy_kind] != prior.version:
                    raise VersionConflict("policy candidate is no longer active")
                self._active_versions[prior.policy_kind] = prior.base_version
            self._candidates[updated.id] = updated
            self._revision += 1
            self.audit_events.append(
                PromotionAuditEvent(
                    candidate_id=updated.id,
                    actor_id=actor.id,
                    action=action,
                    outcome="COMPLETED",
                    expected_revision=expected_revision,
                    observed_revision=self._revision,
                    created_at=datetime.now(UTC),
                )
            )
            return updated

    def deny(
        self, candidate: PolicyCandidate, actor: HumanActor, action: str, expected_revision: int
    ) -> None:
        self.audit_events.append(
            PromotionAuditEvent(
                candidate_id=candidate.id,
                actor_id=actor.id,
                action=f"DENY_{action}",
                outcome="FORBIDDEN",
                expected_revision=expected_revision,
                observed_revision=self._revision,
                created_at=datetime.now(UTC),
            )
        )


class PostgresPolicyRepository:
    """Durable policy pointer and audit updates under one row-level CAS lock."""

    def __init__(
        self,
        connection: Connection,
        *,
        bootstrap_active_versions: dict[str, str],
        denial_audit_connection: Connection | None = None,
    ) -> None:
        self.connection = connection
        self._bootstrap_active_versions = dict(bootstrap_active_versions)
        self._denial_audit_connection = denial_audit_connection
        with connection.engine.begin() as bootstrap_connection:
            for policy_kind, active_version in bootstrap_active_versions.items():
                bootstrap_connection.execute(
                    insert(policy_control)
                    .values(
                        policy_kind=policy_kind,
                        active_version=active_version,
                        revision=0,
                    )
                    .on_conflict_do_nothing(index_elements=[policy_control.c.policy_kind])
                )

    def active_version(self, policy_kind: str) -> str:
        return cast(
            str,
            self.connection.execute(
                select(policy_control.c.active_version).where(
                    policy_control.c.policy_kind == policy_kind
                )
            ).scalar_one(),
        )

    def candidate(self, candidate_id: UUID) -> PolicyCandidate:
        row = (
            self.connection.execute(
                select(policy_candidate_table).where(policy_candidate_table.c.id == candidate_id)
            )
            .mappings()
            .one()
        )
        return PolicyCandidate(
            id=cast(UUID, row["id"]),
            policy_kind=cast(str, row["policy_kind"]),
            version=cast(str, row["version"]),
            base_version=cast(str, row["base_version"]),
            lesson_ids=tuple(UUID(item) for item in row["lesson_ids"]),
            created_at=row["created_at"],
            status=PolicyStatus(row["status"]),
        )

    def _control(self, policy_kind: str) -> tuple[str, int]:
        row = (
            self.connection.execute(
                select(policy_control)
                .where(policy_control.c.policy_kind == policy_kind)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return cast(str, row["active_version"]), cast(int, row["revision"])

    def _validate_learning_lineage(self, lesson_ids: tuple[UUID, ...]) -> None:
        for lesson_id in lesson_ids:
            lesson_exists = self.connection.execute(
                select(candidate_lesson.c.id).where(candidate_lesson.c.id == lesson_id)
            ).scalar_one_or_none()
            latest_approval_action = self.connection.execute(
                select(lesson_approval.c.action)
                .where(lesson_approval.c.lesson_id == lesson_id)
                .order_by(lesson_approval.c.created_at.desc(), lesson_approval.c.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            replay_exists = self.connection.execute(
                select(replay_run.c.id).where(
                    replay_run.c.lesson_id == lesson_id,
                    func.jsonb_array_length(replay_run.c.decision_ids) > 0,
                )
            ).scalar_one_or_none()
            if (
                lesson_exists is None
                or latest_approval_action != "APPROVE"
                or replay_exists is None
            ):
                raise ValueError("policy requires an approved and replayed lesson")

    def transact(
        self,
        *,
        candidate: PolicyCandidate,
        actor: HumanActor,
        action: str,
        expected_revision: int,
        next_status: PolicyStatus,
    ) -> PolicyCandidate:
        active_version, observed_revision = self._control(candidate.policy_kind)
        if expected_revision != observed_revision:
            raise VersionConflict("policy revision changed concurrently")
        if action in {"APPROVE", "ACTIVATE"}:
            self._validate_learning_lineage(candidate.lesson_ids)
        persisted = (
            self.connection.execute(
                select(policy_candidate_table)
                .where(policy_candidate_table.c.id == candidate.id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        prior = self.candidate(candidate.id) if persisted is not None else candidate
        if action in {"APPROVE", "REJECT"} and prior.status is not PolicyStatus.CANDIDATE:
            raise ValueError("only candidate policies can be approved or rejected")
        if action == "APPROVE" and active_version != prior.base_version:
            raise VersionConflict("candidate base version is no longer active")
        if action == "ACTIVATE":
            if prior.status is not PolicyStatus.APPROVED:
                raise ValueError("only approved policy candidates can be activated")
            if active_version != prior.base_version:
                raise VersionConflict("active policy no longer matches candidate base version")
            active_version = prior.version
        elif action == "ROLLBACK":
            if prior.status is not PolicyStatus.ACTIVE:
                raise ValueError("only active policy candidates can be rolled back")
            if active_version != prior.version:
                raise VersionConflict("policy candidate is no longer active")
            active_version = prior.base_version
        updated = replace(prior, status=next_status)
        next_revision = observed_revision + 1
        values = {
            "id": updated.id,
            "policy_kind": updated.policy_kind,
            "version": updated.version,
            "base_version": updated.base_version,
            "lesson_ids": [str(item) for item in updated.lesson_ids],
            "status": updated.status.value,
            "revision": next_revision,
            "created_at": updated.created_at,
        }
        if persisted is None:
            self.connection.execute(insert(policy_candidate_table).values(**values))
        else:
            self.connection.execute(
                update(policy_candidate_table)
                .where(policy_candidate_table.c.id == updated.id)
                .values(status=updated.status.value, revision=next_revision)
            )
        control_update = self.connection.execute(
            update(policy_control)
            .where(
                policy_control.c.policy_kind == updated.policy_kind,
                policy_control.c.revision == expected_revision,
            )
            .values(
                active_version=active_version,
                revision=next_revision,
                updated_at=datetime.now(UTC),
            )
        )
        if control_update.rowcount != 1:
            raise VersionConflict("policy revision changed concurrently")
        self.connection.execute(
            insert(policy_promotion_audit).values(
                policy_candidate_id=updated.id,
                actor_id=actor.id,
                action=action,
                outcome="COMPLETED",
                expected_revision=expected_revision,
                observed_revision=next_revision,
            )
        )
        return updated

    def deny(
        self, candidate: PolicyCandidate, actor: HumanActor, action: str, expected_revision: int
    ) -> None:
        if self._denial_audit_connection is not None:
            self._write_denial(
                self._denial_audit_connection,
                candidate=candidate,
                actor=actor,
                action=action,
                expected_revision=expected_revision,
            )
            return
        with self.connection.engine.begin() as audit_connection:
            self._write_denial(
                audit_connection,
                candidate=candidate,
                actor=actor,
                action=action,
                expected_revision=expected_revision,
            )

    def _write_denial(
        self,
        connection: Connection,
        *,
        candidate: PolicyCandidate,
        actor: HumanActor,
        action: str,
        expected_revision: int,
    ) -> None:
        control = (
            connection.execute(
                select(policy_control.c.active_version, policy_control.c.revision).where(
                    policy_control.c.policy_kind == candidate.policy_kind
                )
            )
            .mappings()
            .one_or_none()
        )
        if control is None:
            active_version = self._bootstrap_active_versions.get(candidate.policy_kind)
            if active_version is None:
                raise ValueError("policy control must exist before denial audit")
            connection.execute(
                insert(policy_control).values(
                    policy_kind=candidate.policy_kind,
                    active_version=active_version,
                    revision=0,
                )
            )
            observed_revision = 0
        else:
            observed_revision = cast(int, control["revision"])
        connection.execute(
            insert(policy_candidate_table)
            .values(
                id=candidate.id,
                policy_kind=candidate.policy_kind,
                version=candidate.version,
                base_version=candidate.base_version,
                lesson_ids=[str(item) for item in candidate.lesson_ids],
                status=candidate.status.value,
                revision=observed_revision,
                created_at=candidate.created_at,
            )
            .on_conflict_do_nothing(index_elements=[policy_candidate_table.c.id])
        )
        connection.execute(
            insert(policy_promotion_audit).values(
                policy_candidate_id=candidate.id,
                actor_id=actor.id,
                action=f"DENY_{action}",
                outcome="FORBIDDEN",
                expected_revision=expected_revision,
                observed_revision=observed_revision,
            )
        )


class PolicyPromotionService:
    def __init__(self, repository: PolicyRepository) -> None:
        self._repository = repository

    def _authorize(
        self, candidate: PolicyCandidate, *, actor: HumanActor, action: str, expected_revision: int
    ) -> None:
        if not actor.authenticated or not actor.is_human or actor.id.casefold().endswith("agent"):
            self._repository.deny(candidate, actor, action, expected_revision)
            raise PolicyPromotionForbidden("authenticated human approval required")

    def approve(
        self, candidate: PolicyCandidate, *, actor: HumanActor, expected_revision: int
    ) -> PolicyCandidate:
        self._authorize(
            candidate, actor=actor, action="APPROVE", expected_revision=expected_revision
        )
        return self._repository.transact(
            candidate=candidate,
            actor=actor,
            action="APPROVE",
            expected_revision=expected_revision,
            next_status=PolicyStatus.APPROVED,
        )

    def reject(
        self, candidate: PolicyCandidate, *, actor: HumanActor, expected_revision: int
    ) -> PolicyCandidate:
        self._authorize(
            candidate, actor=actor, action="REJECT", expected_revision=expected_revision
        )
        return self._repository.transact(
            candidate=candidate,
            actor=actor,
            action="REJECT",
            expected_revision=expected_revision,
            next_status=PolicyStatus.REJECTED,
        )

    def activate(
        self, candidate_id: UUID, *, actor: HumanActor, expected_revision: int
    ) -> PolicyCandidate:
        candidate = self._repository.candidate(candidate_id)
        self._authorize(
            candidate, actor=actor, action="ACTIVATE", expected_revision=expected_revision
        )
        return self._repository.transact(
            candidate=candidate,
            actor=actor,
            action="ACTIVATE",
            expected_revision=expected_revision,
            next_status=PolicyStatus.ACTIVE,
        )

    def rollback(
        self, candidate_id: UUID, *, actor: HumanActor, expected_revision: int
    ) -> PolicyCandidate:
        candidate = self._repository.candidate(candidate_id)
        self._authorize(
            candidate, actor=actor, action="ROLLBACK", expected_revision=expected_revision
        )
        return self._repository.transact(
            candidate=candidate,
            actor=actor,
            action="ROLLBACK",
            expected_revision=expected_revision,
            next_status=PolicyStatus.ROLLED_BACK,
        )
