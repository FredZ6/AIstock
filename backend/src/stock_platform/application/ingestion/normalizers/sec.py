"""Deterministic SEC submissions normalization without persistence side effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.market_data.concepts import FinancialFactInput
from stock_platform.infrastructure.providers.base import ProviderBatch
from stock_platform.infrastructure.providers.sec import SecIdentity, allowed_sec_forms


def _date(value: object, *, required: bool) -> date | None:
    if value in (None, ""):
        if required:
            raise ValueError("SEC filing date is required")
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("SEC filing date is invalid") from error


def _timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("SEC acceptance timestamp is invalid") from error
    return require_aware(parsed).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SecFiling:
    symbol: Symbol
    cik: str
    accession_number: str
    form: str
    base_form: str
    filing_date: date
    report_date: date | None
    accepted_at: datetime
    available_at: datetime
    primary_document: str
    description: str
    is_amendment: bool
    payload: dict[str, object]

    @classmethod
    def from_values(
        cls,
        *,
        symbol: str,
        cik: str,
        accession_number: str,
        form: str,
        filing_date: str,
        report_date: str | None,
        accepted_at: datetime,
        primary_document: str,
        description: str,
        payload: dict[str, object] | None = None,
    ) -> SecFiling:
        accepted = require_aware(accepted_at).astimezone(UTC)
        normalized_form = form.strip().upper()
        is_amendment = normalized_form.endswith("/A")
        normalized_cik = cik.removeprefix("CIK").zfill(10)
        if not normalized_cik.isdigit() or len(normalized_cik) != 10:
            raise ValueError("SEC CIK must contain at most ten digits")
        return cls(
            symbol=Symbol(symbol),
            cik=normalized_cik,
            accession_number=accession_number,
            form=normalized_form,
            base_form=normalized_form.removesuffix("/A"),
            filing_date=cast(date, _date(filing_date, required=True)),
            report_date=_date(report_date, required=False),
            accepted_at=accepted,
            available_at=accepted,
            primary_document=primary_document,
            description=description,
            is_amendment=is_amendment,
            payload=dict(payload or {}),
        )


@dataclass(frozen=True, slots=True)
class SecNormalizationResult:
    filings: tuple[SecFiling, ...]
    historical_submission_files: tuple[str, ...]


class SecNormalizer:
    _FIELDS = (
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "reportDate",
        "form",
        "primaryDocument",
        "primaryDocDescription",
    )

    def normalize_submissions(
        self,
        batch: ProviderBatch,
        *,
        identity: SecIdentity,
    ) -> SecNormalizationResult:
        try:
            document = json.loads(batch.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("SEC submissions payload is invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("SEC submissions payload must be an object")
        response_cik = document.get("cik")
        if (
            response_cik is not None
            and str(response_cik).removeprefix("CIK").zfill(10) != identity.cik
        ):
            raise ValueError("SEC submissions CIK does not match requested identity")
        filings = document.get("filings")
        if not isinstance(filings, dict) or not isinstance(filings.get("recent"), dict):
            raise ValueError("SEC submissions payload is missing recent filings")
        recent = cast(dict[str, object], filings["recent"])
        normalized = self._normalize_filing_arrays(recent, identity=identity)

        files = filings.get("files", [])
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise ValueError("SEC historical submission files must be objects")
        historical = tuple(str(item["name"]) for item in files if item.get("name"))
        return SecNormalizationResult(normalized, historical)

    def normalize_historical_submissions(
        self,
        batch: ProviderBatch,
        *,
        identity: SecIdentity,
    ) -> tuple[SecFiling, ...]:
        try:
            document = json.loads(batch.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("SEC historical submissions payload is invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("SEC historical submissions payload must be an object")
        return self._normalize_filing_arrays(cast(dict[str, object], document), identity=identity)

    def _normalize_filing_arrays(
        self,
        values_by_field: dict[str, object],
        *,
        identity: SecIdentity,
    ) -> tuple[SecFiling, ...]:
        arrays = [values_by_field.get(field) for field in self._FIELDS]
        if any(not isinstance(values, list) for values in arrays):
            raise ValueError("SEC recent filing fields must be parallel arrays")
        lengths = {len(cast(list[object], values)) for values in arrays}
        if len(lengths) != 1:
            raise ValueError("SEC recent filing fields must be parallel arrays")

        allowed = allowed_sec_forms(identity.regime)
        normalized: list[SecFiling] = []
        for index in range(next(iter(lengths), 0)):
            payload = {
                field: cast(list[object], values_by_field[field])[index] for field in self._FIELDS
            }
            form = str(payload["form"]).strip().upper()
            if form not in allowed:
                continue
            normalized.append(
                SecFiling.from_values(
                    symbol=str(identity.symbol),
                    cik=identity.cik,
                    accession_number=str(payload["accessionNumber"]),
                    form=form,
                    filing_date=str(payload["filingDate"]),
                    report_date=str(payload["reportDate"]) or None,
                    accepted_at=_timestamp(payload["acceptanceDateTime"]),
                    primary_document=str(payload["primaryDocument"]),
                    description=str(payload["primaryDocDescription"]),
                    payload=payload,
                )
            )

        return tuple(normalized)

    def normalize_company_facts(
        self,
        batch: ProviderBatch,
        *,
        identity: SecIdentity,
    ) -> tuple[FinancialFactInput, ...]:
        try:
            document = json.loads(batch.body, parse_float=str, parse_int=str)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("SEC company facts payload is invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("SEC company facts payload must be an object")
        response_cik = document.get("cik")
        if str(response_cik).removeprefix("CIK").zfill(10) != identity.cik:
            raise ValueError("SEC company facts CIK does not match requested identity")
        facts = document.get("facts")
        if not isinstance(facts, dict):
            raise ValueError("SEC company facts payload is missing facts")
        allowed = allowed_sec_forms(identity.regime)
        normalized: list[FinancialFactInput] = []
        seen: set[tuple[str, str, str, str, str, str]] = set()
        for taxonomy, concepts in facts.items():
            if not isinstance(concepts, dict):
                raise ValueError("SEC company facts taxonomy must contain concepts")
            for concept, concept_payload in concepts.items():
                if not isinstance(concept_payload, dict) or not isinstance(
                    concept_payload.get("units"), dict
                ):
                    raise ValueError("SEC company fact must contain units")
                for unit, observations in cast(dict[str, object], concept_payload["units"]).items():
                    if not isinstance(observations, list):
                        raise ValueError("SEC company fact observations must be a list")
                    for observation in observations:
                        if not isinstance(observation, dict):
                            raise ValueError("SEC company fact observation must be an object")
                        if str(observation.get("form", "")).upper() not in allowed:
                            continue
                        required = ("start", "end", "val", "accn")
                        if any(observation.get(field) in (None, "") for field in required):
                            continue
                        identity_key = (
                            str(taxonomy),
                            str(concept),
                            str(unit),
                            str(observation["start"]),
                            str(observation["end"]),
                            str(observation["accn"]),
                        )
                        if identity_key in seen:
                            continue
                        seen.add(identity_key)
                        normalized.append(
                            FinancialFactInput.from_values(
                                taxonomy=str(taxonomy),
                                concept=str(concept),
                                value=str(observation["val"]),
                                unit=str(unit),
                                currency=str(unit) if len(str(unit)) == 3 else None,
                                period_start=str(observation["start"]),
                                period_end=str(observation["end"]),
                                accession_number=str(observation["accn"]),
                            )
                        )
        return tuple(normalized)
