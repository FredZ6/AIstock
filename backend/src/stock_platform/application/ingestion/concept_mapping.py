"""Versioned deterministic SEC concept mapping loaded from a local configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from stock_platform.domain.market_data.concepts import (
    ConceptMappingResult,
    FinancialFactInput,
    MappingStatus,
)

SourceConcept = tuple[str, str]


@dataclass(frozen=True, slots=True)
class DerivedRule:
    canonical: str
    operation: str
    inputs: tuple[SourceConcept, ...]


class ConceptMappingRegistry:
    def __init__(
        self,
        *,
        version: str,
        exact: dict[SourceConcept, str],
        ambiguous: frozenset[SourceConcept],
        derived: dict[str, DerivedRule],
    ) -> None:
        self.version = version
        self._exact = dict(exact)
        self._ambiguous = ambiguous
        self._derived = dict(derived)

    @classmethod
    def load(cls, path: Path) -> ConceptMappingRegistry:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("financial concept mapping configuration is invalid") from error
        if not isinstance(document, dict) or not isinstance(document.get("version"), str):
            raise ValueError("financial concept mapping version is required")
        exact: dict[SourceConcept, str] = {}
        for item in cls._objects(document.get("exact"), field="exact"):
            source = cls._source(item)
            if source in exact:
                raise ValueError("duplicate exact mapping source concept")
            exact[source] = str(item["canonical"])
        ambiguous = frozenset(
            cls._source(item) for item in cls._objects(document.get("ambiguous"), field="ambiguous")
        )
        if exact.keys() & ambiguous:
            raise ValueError("source concept cannot be both exact and ambiguous")
        derived: dict[str, DerivedRule] = {}
        for item in cls._objects(document.get("derived"), field="derived"):
            canonical = str(item["canonical"])
            raw_inputs = cls._objects(item.get("inputs"), field="derived inputs")
            if canonical in derived:
                raise ValueError("duplicate derived canonical concept")
            derived[canonical] = DerivedRule(
                canonical=canonical,
                operation=str(item["operation"]),
                inputs=tuple(cls._source(source) for source in raw_inputs),
            )
        return cls(
            version=str(document["version"]),
            exact=exact,
            ambiguous=ambiguous,
            derived=derived,
        )

    @staticmethod
    def _objects(value: object, *, field: str) -> list[dict[str, object]]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"financial concept mapping {field} must be a list of objects")
        return cast(list[dict[str, object]], value)

    @staticmethod
    def _source(item: dict[str, object]) -> SourceConcept:
        taxonomy = item.get("taxonomy")
        concept = item.get("concept")
        if not isinstance(taxonomy, str) or not isinstance(concept, str):
            raise ValueError("mapping source requires taxonomy and concept")
        return taxonomy, concept

    def map_fact(self, fact: FinancialFactInput) -> ConceptMappingResult:
        source = (fact.taxonomy, fact.concept)
        canonical = self._exact.get(source)
        status = (
            MappingStatus.EXACT
            if canonical is not None
            else MappingStatus.AMBIGUOUS
            if source in self._ambiguous
            else MappingStatus.UNMAPPED
        )
        return ConceptMappingResult(
            status=status,
            canonical_concept=canonical,
            value=fact.value,
            mapping_version=self.version,
            input_provenance=(source,),
            source_facts=(fact,),
        )

    def derive(
        self,
        canonical_concept: str,
        facts: tuple[FinancialFactInput, ...],
    ) -> ConceptMappingResult:
        try:
            rule = self._derived[canonical_concept]
        except KeyError as error:
            raise ValueError(f"unknown derived concept: {canonical_concept}") from error
        by_source = {(fact.taxonomy, fact.concept): fact for fact in facts}
        if set(by_source) != set(rule.inputs) or len(by_source) != len(facts):
            raise ValueError("derived concept inputs do not match the versioned rule")
        ordered = tuple(by_source[source] for source in rule.inputs)
        first = ordered[0]
        if any(
            (fact.unit, fact.currency, fact.period_start, fact.period_end)
            != (first.unit, first.currency, first.period_start, first.period_end)
            for fact in ordered[1:]
        ):
            raise ValueError("derived concept inputs must share unit, currency, and period")
        if rule.operation != "subtract" or len(ordered) != 2:
            raise ValueError("unsupported deterministic derived operation")
        value: Decimal = ordered[0].value - ordered[1].value
        return ConceptMappingResult(
            status=MappingStatus.DERIVED,
            canonical_concept=rule.canonical,
            value=value,
            mapping_version=self.version,
            input_provenance=rule.inputs,
            source_facts=ordered,
        )
