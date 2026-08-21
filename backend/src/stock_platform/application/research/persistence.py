"""Research decision persistence with complete normalized lineage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Table, and_, func, insert, select

from stock_platform.agents.research.state import ResearchResult
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    claim,
    confidence_policy_version,
    decision_diff,
    decision_snapshot,
    derived_metric,
    evidence_gap,
    evidence_item,
    execution_policy_version,
    investment_thesis,
    normalized_record,
    raw_data_object,
    research_opinion,
    research_scoring_policy_version,
    risk_policy_version,
    thesis_evidence_link,
)


class ResearchStore(Protocol):
    def latest(self, run_id: str) -> ResearchResult | None: ...

    def persist(self, result: ResearchResult) -> None: ...


class InMemoryResearchStore:
    def __init__(self) -> None:
        self._results: dict[str, ResearchResult] = {}
        self.persist_count = 0

    def latest(self, run_id: str) -> ResearchResult | None:
        return self._results.get(run_id)

    def persist(self, result: ResearchResult) -> None:
        if result.run_id in self._results:
            return
        self._results[result.run_id] = result
        self.persist_count += 1


class PostgresResearchStore:
    def __init__(
        self,
        connection: Connection,
        *,
        available_at: datetime | None = None,
        record_events: bool = True,
    ) -> None:
        self.connection = connection
        self._results: dict[str, ResearchResult] = {}
        self.available_at = available_at
        self.record_events = record_events

    def latest(self, run_id: str) -> ResearchResult | None:
        return self._results.get(run_id)

    def _policy_id(self, policy_table: Table, version: str) -> UUID:
        existing = cast(
            UUID | None,
            self.connection.execute(
                select(policy_table.c.id).where(policy_table.c.version == version)
            ).scalar_one_or_none(),
        )
        if existing is not None:
            return existing
        policy: dict[str, str] = {"source": "task_specification"}
        if policy_table.name == "risk_policy_version":
            policy = {
                "max_position_weight": "0.20",
                "max_gross_exposure": "1",
                "min_cash_reserve": "0.05",
                "max_daily_turnover": "0.25",
                "max_drawdown": "0.20",
                "max_research_age_days": "2",
                "earnings_blackout_days": "1",
            }
        elif policy_table.name == "execution_policy_version":
            policy = {
                "spread_bps": "0",
                "slippage_bps": "0",
                "fee_per_share": "0",
                "minimum_fee": "0",
                "volume_participation": "1",
            }
        return cast(
            UUID,
            self.connection.execute(
                insert(policy_table)
                .values(version=version, policy=policy)
                .returning(policy_table.c.id)
            ).scalar_one(),
        )

    def persist(self, result: ResearchResult) -> None:
        if result.run_id in self._results:
            return
        if result.thesis is None or result.opinion is None or result.decision_id is None:
            raise ValueError("cannot persist an incomplete research decision")

        evidence_ids: set[UUID] = set()
        for evidence in result.evidence:
            existing_evidence = self.connection.execute(
                select(evidence_item.c.id).where(evidence_item.c.id == evidence.id)
            ).scalar_one_or_none()
            if existing_evidence is not None:
                evidence_ids.add(evidence.id)
                continue
            normalized_id = self.connection.execute(
                select(normalized_record.c.id)
                .select_from(
                    normalized_record.join(
                        raw_data_object,
                        normalized_record.c.raw_data_object_id == raw_data_object.c.id,
                    )
                )
                .where(
                    and_(
                        raw_data_object.c.raw_object_key == evidence.raw_object_key,
                        raw_data_object.c.content_hash == evidence.content_hash,
                    )
                )
            ).scalar_one()
            metric_id = uuid4()
            self.connection.execute(
                insert(derived_metric).values(
                    id=metric_id,
                    normalized_record_id=normalized_id,
                    metric_name=f"research_input:{evidence.feed_type}",
                    metric_value=0,
                    algorithm_version="research-normalize-v1",
                )
            )
            self.connection.execute(
                insert(evidence_item).values(
                    id=evidence.id,
                    derived_metric_id=metric_id,
                    provider=evidence.provider,
                    coverage=1,
                    conflict=any(
                        evidence.id in conflict.evidence_ids for conflict in result.conflicts
                    ),
                    content={
                        "symbol": str(evidence.symbol),
                        "feed_type": evidence.feed_type,
                        "available_at": evidence.available_at.isoformat(),
                        "content_hash": evidence.content_hash,
                        "raw_object_key": evidence.raw_object_key,
                        "payload": dict(evidence.payload),
                    },
                )
            )
            evidence_ids.add(evidence.id)

        for claim_item in result.claims:
            existing_claim = self.connection.execute(
                select(claim.c.id).where(claim.c.id == claim_item.id)
            ).scalar_one_or_none()
            if claim_item.evidence_id in evidence_ids and existing_claim is None:
                self.connection.execute(
                    insert(claim).values(
                        id=claim_item.id,
                        evidence_id=claim_item.evidence_id,
                        statement=claim_item.statement,
                    )
                )
        for gap in result.gaps:
            self.connection.execute(
                insert(evidence_gap).values(
                    id=gap.id,
                    kind=gap.kind.value,
                    field=gap.field,
                    domain=gap.domain,
                    reason=gap.reason,
                    provider=gap.provider,
                    observed_at=gap.observed_at,
                )
            )

        versions = result.specification.policy_versions
        scoring_policy_id = self._policy_id(
            research_scoring_policy_version, versions.research_scoring
        )
        risk_policy_id = self._policy_id(risk_policy_version, versions.risk)
        execution_policy_id = self._policy_id(execution_policy_version, versions.execution)
        confidence_policy_id = self._policy_id(confidence_policy_version, versions.confidence)
        thesis = result.thesis
        self.connection.execute(
            insert(investment_thesis).values(
                id=thesis.id,
                run_id=thesis.run_id,
                symbol=str(thesis.symbol),
                as_of=thesis.as_of,
                direction=thesis.direction,
                summary=thesis.summary,
                catalysts=list(thesis.catalysts),
                risks=list(thesis.risks),
                invalidation_conditions=list(thesis.invalidation_conditions),
                horizon=thesis.horizon,
                confidence=thesis.confidence,
                confidence_policy_version_id=confidence_policy_id,
                supersedes_thesis_id=thesis.supersedes_thesis_id,
                created_at=thesis.created_at,
            )
        )
        for link in result.evidence_links:
            self.connection.execute(
                insert(thesis_evidence_link).values(
                    thesis_id=link.thesis_id,
                    evidence_id=link.evidence_id,
                    relation=link.relation.value,
                    weight=link.weight,
                    rationale=link.rationale,
                )
            )
        self.connection.execute(
            insert(research_opinion).values(
                id=result.opinion.id,
                thesis_id=result.opinion.thesis_id,
                value=result.opinion.value.value,
            )
        )
        self.connection.execute(
            insert(decision_snapshot).values(
                id=result.decision_id,
                thesis_id=thesis.id,
                research_scoring_policy_version_id=scoring_policy_id,
                risk_policy_version_id=risk_policy_id,
                execution_policy_version_id=execution_policy_id,
                confidence_policy_version_id=confidence_policy_id,
                prompt_version=versions.prompt,
                model_version=versions.model,
                data_cutoff=result.specification.data_cutoff,
                available_at=self.available_at or datetime.now(UTC),
            )
        )
        self.connection.execute(
            insert(decision_diff).values(
                decision_id=result.decision_id,
                previous_decision_id=None,
                generator="DETERMINISTIC_CODE",
                changes=dict(result.decision_diff or {}),
            )
        )
        run_uuid = UUID(result.run_id)
        if not self.record_events:
            self._results[result.run_id] = result
            return
        next_sequence = (
            int(
                self.connection.execute(
                    select(func.coalesce(func.max(agent_event.c.sequence), 0)).where(
                        agent_event.c.run_id == run_uuid
                    )
                ).scalar_one()
            )
            + 1
        )
        for sequence, node in enumerate(result.route, start=next_sequence):
            self.connection.execute(
                insert(agent_event).values(
                    run_id=run_uuid,
                    sequence=sequence,
                    event_type="node.completed",
                    payload={"node": node, "status": result.status.value},
                )
            )
        self._results[result.run_id] = result
