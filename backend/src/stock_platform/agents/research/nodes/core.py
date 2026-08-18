"""Node implementations for the v0.2 daily research route."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from stock_platform.agents.research.state import ResearchResult, ResearchState, ResearchStatus
from stock_platform.application.research.persistence import ResearchStore
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.research.claims import (
    Claim,
    InvestmentThesis,
    ResearchOpinion,
    ResearchOpinionValue,
    stable_research_id,
)
from stock_platform.domain.research.decision_diff import build_decision_diff
from stock_platform.domain.research.evidence import (
    EvidenceConflict,
    EvidenceGap,
    EvidenceGapKind,
    EvidenceItem,
    EvidenceRelation,
    ThesisEvidenceLink,
)
from stock_platform.domain.research.scores import deterministic_scores
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderResponse,
    ProviderStatus,
)


class ResearchCollectionProvider(Protocol):
    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse: ...


_RESEARCH_FEEDS = (
    FeedType.COMPANY_FACTS,
    FeedType.PRICE_BARS,
    FeedType.COMPANY_NEWS,
    FeedType.OPTION_AGGREGATES,
    FeedType.TARGET_CONSENSUS,
)


def _route(name: str) -> dict[str, object]:
    return {"route": (name,)}


class ResearchNodes:
    def __init__(self, *, provider: ResearchCollectionProvider, store: ResearchStore) -> None:
        self._provider = provider
        self._store = store

    def preflight(self, state: ResearchState) -> dict[str, object]:
        update = _route("preflight")
        if state["cancelled"]:
            update["status"] = ResearchStatus.CANCELLED
        return update

    def planner(self, state: ResearchState) -> dict[str, object]:
        del state
        return _route("planner")

    def parallel_collection(self, state: ResearchState) -> dict[str, object]:
        task = state["specification"]
        responses: list[ProviderResponse] = []
        for feed in _RESEARCH_FEEDS:
            if feed.value in task.allowed_tools:
                responses.append(self._provider.fetch(feed, task.symbols[0], task.data_cutoff))
        warnings = tuple(warning for response in responses for warning in response.warnings)
        return {
            **_route("parallel_collection"),
            "responses": tuple(responses),
            "warnings": warnings,
        }

    def normalize_freshness_lineage(self, state: ResearchState) -> dict[str, object]:
        evidence: list[EvidenceItem] = []
        gaps: list[EvidenceGap] = []
        for response in state["responses"]:
            for record in response.records:
                if record.available_at > state["specification"].data_cutoff:
                    continue
                evidence.append(
                    EvidenceItem.from_source(
                        symbol=str(record.symbol),
                        provider=record.provider,
                        feed_type=record.feed_type.value,
                        available_at=record.available_at,
                        content_hash=record.content_hash,
                        raw_object_key=record.raw_object_key,
                        payload=record.payload,
                    )
                )
            if response.status is not ProviderStatus.OK:
                kind = (
                    EvidenceGapKind.UNAVAILABLE
                    if response.status is ProviderStatus.UNAVAILABLE
                    else EvidenceGapKind.MISSING
                )
                gaps.append(
                    EvidenceGap.create(
                        run_id=state["run_id"],
                        kind=kind,
                        field=response.feed_type.value,
                        domain="market_data",
                        reason=response.missingness or response.status.value,
                        provider=response.provider,
                        observed_at=state["specification"].decision_time,
                    )
                )
        return {
            **_route("normalize_freshness_lineage"),
            "evidence": tuple(evidence),
            "gaps": tuple(gaps),
        }

    def parallel_analysts(self, state: ResearchState) -> dict[str, object]:
        claims = tuple(
            Claim.create(
                symbol=str(item.symbol),
                statement=(
                    f"{item.feed_type} evidence {item.content_hash[:12]} was available "
                    f"at {item.available_at.isoformat()}"
                ),
                evidence_id=item.id,
            )
            for item in state["evidence"]
        )
        return {**_route("parallel_analysts"), "claims": claims}

    def evidence_judge(self, state: ResearchState) -> dict[str, object]:
        targets = [item for item in state["evidence"] if item.feed_type == "target_consensus"]
        target_values: dict[str, list[EvidenceItem]] = {}
        for item in targets:
            value = str(item.payload.get("median_target"))
            target_values.setdefault(value, []).append(item)
        if len(target_values) <= 1:
            return _route("evidence_judge")
        evidence_ids = tuple(item.id for item in targets)
        conflict = EvidenceConflict(
            field="median_target",
            evidence_ids=evidence_ids,
            reason="provider target values disagree",
        )
        gap = EvidenceGap.create(
            run_id=state["run_id"],
            kind=EvidenceGapKind.CONFLICTED,
            field="median_target",
            domain="analyst",
            reason=conflict.reason,
            provider="FIXTURE",
            observed_at=state["specification"].decision_time,
        )
        return {
            **_route("evidence_judge"),
            "conflicts": (conflict,),
            "gaps": (gap,),
        }

    def reflect(self, state: ResearchState) -> dict[str, object]:
        return {**_route("reflect"), "reflections": state["reflections"] + 1}

    def deterministic_score_confidence(self, state: ResearchState) -> dict[str, object]:
        versions = state["specification"].policy_versions
        score, confidence = deterministic_scores(
            evidence=state["evidence"],
            gaps=state["gaps"],
            conflicts=state["conflicts"],
            scoring_version=versions.research_scoring,
            confidence_version=versions.confidence,
        )
        return {
            **_route("deterministic_score_confidence"),
            "score": score,
            "confidence": confidence,
        }

    def investment_thesis(self, state: ResearchState) -> dict[str, object]:
        score = state["score"]
        confidence = state["confidence"]
        if score is None or confidence is None:
            raise ValueError("scores must exist before thesis construction")
        direction = "BULLISH" if score.value > Decimal("0.50") else "NEUTRAL"
        thesis_id = stable_research_id(state["run_id"], "thesis")
        thesis = InvestmentThesis(
            id=thesis_id,
            run_id=UUID(state["run_id"]),
            symbol=Symbol(state["specification"].symbols[0]),
            as_of=state["specification"].decision_time,
            direction=direction,
            summary=f"Deterministic {direction.lower()} research thesis",
            catalysts=("Evidence-backed operating or market improvement",),
            risks=tuple(gap.reason for gap in state["gaps"]) or ("Fixture uncertainty",),
            invalidation_conditions=("Material evidence becomes stale or contradicted",),
            horizon="20_TRADING_DAYS",
            confidence=confidence.value,
            confidence_policy_version=confidence.policy_version,
            supersedes_thesis_id=None,
            created_at=datetime.now(UTC),
        )
        conflicted_ids = {
            evidence_id for conflict in state["conflicts"] for evidence_id in conflict.evidence_ids
        }
        links = tuple(
            ThesisEvidenceLink(
                thesis_id=thesis_id,
                evidence_id=item.id,
                relation=(
                    EvidenceRelation.CONTRADICTS
                    if item.id in conflicted_ids
                    else EvidenceRelation.SUPPORTS
                ),
                weight=Decimal("1.00"),
                rationale="Deterministic evidence relation",
            )
            for item in state["evidence"]
        )
        return {
            **_route("investment_thesis"),
            "thesis": thesis,
            "evidence_links": links,
        }

    def research_opinion(self, state: ResearchState) -> dict[str, object]:
        thesis = state["thesis"]
        if thesis is None:
            raise ValueError("thesis must exist before opinion")
        if not state["evidence"]:
            value = ResearchOpinionValue.ABSTAIN
        elif thesis.direction == "BULLISH":
            value = ResearchOpinionValue.BULLISH
        else:
            value = ResearchOpinionValue.NEUTRAL
        opinion = ResearchOpinion(
            id=stable_research_id(state["run_id"], "opinion"),
            thesis_id=thesis.id,
            value=value,
        )
        return {**_route("research_opinion"), "opinion": opinion}

    def writer(self, state: ResearchState) -> dict[str, object]:
        thesis = state["thesis"]
        opinion = state["opinion"]
        if thesis is None or opinion is None:
            raise ValueError("thesis and opinion are required before rendering")
        report = json.dumps(
            {
                "product_boundary": "research signal for a paper portfolio; not investment advice",
                "symbol": str(thesis.symbol),
                "thesis": thesis.summary,
                "opinion": opinion.value.value,
                "claim_ids": [str(item.id) for item in state["claims"]],
                "evidence_ids": [str(item.id) for item in state["evidence"]],
                "gaps": [gap.kind.value for gap in state["gaps"]],
            },
            sort_keys=True,
        )
        return {**_route("writer"), "report": report}

    def citation_verifier(self, state: ResearchState) -> dict[str, object]:
        evidence_ids = {item.id for item in state["evidence"]}
        verified = all(item.evidence_id in evidence_ids for item in state["claims"])
        return {**_route("citation_verifier"), "citations_verified": verified}

    def decision_diff(self, state: ResearchState) -> dict[str, object]:
        thesis = state["thesis"]
        opinion = state["opinion"]
        current: Mapping[str, object] = {
            "thesis": thesis.summary if thesis else None,
            "opinion": opinion.value.value if opinion else None,
            "confidence": str(thesis.confidence) if thesis else None,
            "evidence_ids": sorted(str(item.id) for item in state["evidence"]),
            "gap_kinds": sorted(gap.kind.value for gap in state["gaps"]),
            "invalidation_conditions": list(thesis.invalidation_conditions) if thesis else [],
        }
        return {
            **_route("decision_diff"),
            "decision_diff": build_decision_diff({}, current),
        }

    def persist_decision(self, state: ResearchState) -> dict[str, object]:
        opinion = state["opinion"]
        limited = opinion is None or opinion.value is ResearchOpinionValue.ABSTAIN
        status = ResearchStatus.COMPLETED_WITH_LIMITATIONS if limited else ResearchStatus.COMPLETED
        update: dict[str, object] = {
            **_route("persist_decision"),
            "status": status,
            "decision_id": stable_research_id(state["run_id"], "decision"),
        }
        complete_state = dict(state)
        complete_state.update(update)
        complete_state["route"] = state["route"] + ("persist_decision",)
        self._store.persist(ResearchResult.from_state(complete_state))  # type: ignore[arg-type]
        return update
