"""Immutable evidence, gaps, conflicts, and thesis relationships."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid5

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware

_EVIDENCE_NAMESPACE = UUID("12fc0dd8-f175-468b-ad71-79d3698aa9be")


class FrozenDict(dict[str, object]):
    """Checkpoint-serializable immutable mapping for evidence payloads."""

    def _immutable(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("evidence payload is immutable")

    __delitem__ = _immutable
    __setitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable  # type: ignore[assignment]


class EvidenceGapKind(StrEnum):
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTED = "CONFLICTED"


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    id: UUID
    symbol: Symbol
    provider: str
    feed_type: str
    available_at: datetime
    content_hash: str
    raw_object_key: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", FrozenDict(self.payload))

    @classmethod
    def from_source(
        cls,
        *,
        symbol: str,
        provider: str,
        feed_type: str,
        available_at: datetime,
        content_hash: str,
        raw_object_key: str,
        payload: Mapping[str, object],
    ) -> EvidenceItem:
        if len(content_hash) != 64:
            raise ValueError("content_hash must be SHA-256")
        normalized_symbol = Symbol(symbol)
        stable_id = uuid5(
            _EVIDENCE_NAMESPACE,
            f"{normalized_symbol}:{provider}:{feed_type}:{content_hash}",
        )
        return cls(
            id=stable_id,
            symbol=normalized_symbol,
            provider=provider,
            feed_type=feed_type,
            available_at=require_aware(available_at),
            content_hash=content_hash,
            raw_object_key=raw_object_key,
            payload=FrozenDict(payload),
        )


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    id: UUID
    kind: EvidenceGapKind
    field: str
    domain: str
    reason: str
    provider: str | None
    observed_at: datetime

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        kind: EvidenceGapKind,
        field: str,
        domain: str,
        reason: str,
        provider: str | None,
        observed_at: datetime,
    ) -> EvidenceGap:
        return cls(
            id=uuid5(_EVIDENCE_NAMESPACE, f"{run_id}:{kind}:{domain}:{field}:{reason}"),
            kind=kind,
            field=field,
            domain=domain,
            reason=reason,
            provider=provider,
            observed_at=require_aware(observed_at),
        )


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    field: str
    evidence_ids: tuple[UUID, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ThesisEvidenceLink:
    thesis_id: UUID
    evidence_id: UUID
    relation: EvidenceRelation
    weight: Decimal
    rationale: str
