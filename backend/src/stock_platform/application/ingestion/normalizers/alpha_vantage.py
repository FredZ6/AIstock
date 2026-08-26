"""Deterministic Alpha Vantage earnings-calendar CSV normalization."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.providers.base import ProviderBatch


@dataclass(frozen=True, slots=True)
class EarningsEvent:
    symbol: Symbol
    provider_symbol: str
    event_date: date
    fiscal_date_end: date
    estimate: Decimal | None
    currency: str | None
    available_at: datetime
    payload: dict[str, object]

    @classmethod
    def from_values(
        cls,
        *,
        symbol: str,
        provider_symbol: str,
        event_date: str,
        fiscal_date_end: str,
        estimate: str | None,
        currency: str | None,
        available_at: datetime,
        payload: dict[str, object],
    ) -> EarningsEvent:
        parsed_estimate: Decimal | None = None
        if estimate is not None and estimate != "":
            try:
                parsed_estimate = Decimal(estimate)
            except InvalidOperation as error:
                raise ValueError("Alpha earnings estimate is invalid") from error
        if parsed_estimate is not None and not parsed_estimate.is_finite():
            raise ValueError("Alpha earnings estimate must be finite")
        return cls(
            symbol=Symbol(symbol),
            provider_symbol=provider_symbol,
            event_date=date.fromisoformat(event_date),
            fiscal_date_end=date.fromisoformat(fiscal_date_end),
            estimate=parsed_estimate,
            currency=currency or None,
            available_at=require_aware(available_at).astimezone(UTC),
            payload=dict(payload),
        )


class AlphaVantageNormalizer:
    _REQUIRED = {
        "symbol",
        "name",
        "reportDate",
        "fiscalDateEnding",
        "estimate",
        "currency",
    }

    def normalize_calendar(
        self,
        batch: ProviderBatch,
        *,
        provider_to_canonical: dict[str, str],
    ) -> tuple[EarningsEvent, ...]:
        try:
            text = batch.body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Alpha earnings calendar is not valid UTF-8 CSV") from error
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None or not self._REQUIRED <= set(reader.fieldnames):
            raise ValueError("Alpha earnings calendar schema drift")
        events: list[EarningsEvent] = []
        seen: dict[tuple[str, str], EarningsEvent] = {}
        for raw_row in reader:
            provider_symbol = raw_row["symbol"].strip().upper()
            canonical = provider_to_canonical.get(provider_symbol)
            if canonical is None:
                continue
            event = EarningsEvent.from_values(
                symbol=canonical,
                provider_symbol=provider_symbol,
                event_date=raw_row["reportDate"],
                fiscal_date_end=raw_row["fiscalDateEnding"],
                estimate=raw_row["estimate"],
                currency=raw_row["currency"],
                available_at=batch.observed_at,
                payload={str(key): value for key, value in raw_row.items()},
            )
            key = (str(event.symbol), event.fiscal_date_end.isoformat())
            previous = seen.get(key)
            if previous is not None and previous != event:
                raise ValueError("conflicting earnings rows in one Alpha snapshot")
            if previous is None:
                seen[key] = event
                events.append(event)
        return tuple(events)
