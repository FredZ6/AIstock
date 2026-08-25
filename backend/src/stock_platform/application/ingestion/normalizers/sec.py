"""Deterministic SEC submissions normalization without persistence side effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
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
        arrays = [recent.get(field) for field in self._FIELDS]
        if any(not isinstance(values, list) for values in arrays):
            raise ValueError("SEC recent filing fields must be parallel arrays")
        lengths = {len(cast(list[object], values)) for values in arrays}
        if len(lengths) != 1:
            raise ValueError("SEC recent filing fields must be parallel arrays")

        allowed = allowed_sec_forms(identity.regime)
        normalized: list[SecFiling] = []
        for index in range(next(iter(lengths), 0)):
            payload = {field: cast(list[object], recent[field])[index] for field in self._FIELDS}
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

        files = filings.get("files", [])
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise ValueError("SEC historical submission files must be objects")
        historical = tuple(str(item["name"]) for item in files if item.get("name"))
        return SecNormalizationResult(tuple(normalized), historical)
