"""Render only verified structured research data and force deterministic abstention."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType

from stock_platform.agents.harness.task_spec import PolicyVersions
from stock_platform.application.research.citation_verifier import CitationVerification
from stock_platform.application.research.numeric_verifier import NumericVerification
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.claims import (
    Claim,
    InvestmentThesis,
    ResearchOpinion,
    ResearchOpinionValue,
)
from stock_platform.domain.research.evidence import (
    EvidenceGap,
    EvidenceItem,
    EvidenceRelation,
    ThesisEvidenceLink,
)


@dataclass(frozen=True, slots=True)
class RenderedReport:
    opinion: ResearchOpinion
    content: str
    document: Mapping[str, object]


class ReportRenderer:
    def render(
        self,
        *,
        thesis: InvestmentThesis,
        opinion: ResearchOpinion,
        claims: tuple[Claim, ...],
        evidence: tuple[EvidenceItem, ...],
        links: tuple[ThesisEvidenceLink, ...],
        gaps: tuple[EvidenceGap, ...],
        citation_verification: CitationVerification,
        numeric_verification: NumericVerification,
        decision_diff: Mapping[str, object],
        policy_versions: PolicyVersions,
        data_cutoff: datetime,
    ) -> RenderedReport:
        cutoff = require_aware(data_cutoff)
        verified = citation_verification.verified and numeric_verification.verified
        final_opinion = (
            opinion
            if verified or opinion.value is ResearchOpinionValue.ABSTAIN
            else replace(opinion, value=ResearchOpinionValue.ABSTAIN)
        )
        evidence_by_id = {item.id: item for item in evidence}

        def related(relation: EvidenceRelation) -> list[dict[str, object]]:
            return [
                {
                    "evidence_id": str(link.evidence_id),
                    "relation": link.relation.value,
                    "weight": str(link.weight),
                    "rationale": link.rationale,
                    "provider": evidence_by_id[link.evidence_id].provider,
                    "available_at": evidence_by_id[link.evidence_id].available_at.isoformat(),
                    "content_hash": evidence_by_id[link.evidence_id].content_hash,
                    "raw_object_key": evidence_by_id[link.evidence_id].raw_object_key,
                }
                for link in links
                if link.relation is relation and link.evidence_id in evidence_by_id
            ]

        document: dict[str, object] = {
            "product_boundary": "research signal for a paper portfolio; not investment advice",
            "symbol": str(thesis.symbol),
            "data_cutoff": cutoff.isoformat(),
            "thesis": {
                "summary": thesis.summary,
                "direction": thesis.direction,
                "catalysts": list(thesis.catalysts),
                "risks": list(thesis.risks),
                "invalidation_conditions": list(thesis.invalidation_conditions),
                "horizon": thesis.horizon,
                "confidence": str(thesis.confidence),
            },
            "research_opinion": final_opinion.value.value,
            "claims": [
                {
                    "claim_id": str(claim.id),
                    "statement": claim.statement,
                    "evidence_id": str(claim.evidence_id),
                }
                for claim in claims
            ],
            "supporting_evidence": related(EvidenceRelation.SUPPORTS),
            "counter_evidence": related(EvidenceRelation.CONTRADICTS),
            "context_evidence": related(EvidenceRelation.CONTEXT),
            "uncertainty": {
                "gaps": [
                    {
                        "kind": gap.kind.value,
                        "field": gap.field,
                        "domain": gap.domain,
                        "reason": gap.reason,
                    }
                    for gap in gaps
                ],
                "citation_issues": [issue.code.value for issue in citation_verification.issues],
                "numeric_issues": [issue.code.value for issue in numeric_verification.issues],
            },
            "sources": [
                {
                    "evidence_id": str(item.id),
                    "provider": item.provider,
                    "feed_type": item.feed_type,
                    "available_at": item.available_at.isoformat(),
                    "content_hash": item.content_hash,
                    "raw_object_key": item.raw_object_key,
                }
                for item in evidence
            ],
            "decision_diff": dict(decision_diff),
            "policy_versions": {
                "research_scoring": policy_versions.research_scoring,
                "risk": policy_versions.risk,
                "execution": policy_versions.execution,
                "confidence": policy_versions.confidence,
                "prompt": policy_versions.prompt,
                "model": policy_versions.model,
            },
        }
        return RenderedReport(
            opinion=final_opinion,
            content=json.dumps(document, sort_keys=True),
            document=MappingProxyType(document),
        )
