"""Idempotent deterministic alert worker; explanations are non-authoritative."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from stock_platform.application.alerting.dedup import AlertIdentity
from stock_platform.application.alerting.features import (
    AnomalyFeatures,
    FeatureCalculator,
    MinuteBar,
)
from stock_platform.application.alerting.outbox import (
    AlertContext,
    BarPersistence,
    NotificationChannel,
)
from stock_platform.application.alerting.rules import AlertRule, RuleEvaluation
from stock_platform.infrastructure.messaging.market_stream import StreamMessage


class ExplanationStatus(StrEnum):
    DISABLED = "DISABLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AlertStream(Protocol):
    def acknowledge(self, *, group: str, message_id: str) -> None: ...


class AlertStore(Protocol):
    def persist_bar(self, item: MinuteBar) -> BarPersistence | bool: ...

    def recent_bars(
        self, *, symbol: str, through: datetime, limit: int
    ) -> tuple[MinuteBar, ...]: ...

    def persist_alert(
        self,
        *,
        alert_id: UUID,
        alert_key: str,
        features: AnomalyFeatures,
        evaluation: RuleEvaluation,
        context: AlertContext,
        review_action: str,
        channels: tuple[NotificationChannel, ...],
    ) -> bool: ...

    def record_explanation(
        self,
        *,
        alert_id: UUID,
        status: ExplanationStatus,
        content: str | None,
        error_code: str | None,
    ) -> None: ...


class AlertExplainer(Protocol):
    def explain(self, **values: object) -> str: ...


@dataclass(frozen=True, slots=True)
class ProcessResult:
    outcome: str
    alert_id: UUID | None
    features: AnomalyFeatures | None


class AlertWorker:
    def __init__(
        self,
        *,
        stream: AlertStream,
        store: AlertStore,
        rule: AlertRule,
        context_resolver: Callable[[str, datetime], AlertContext],
        explainer: AlertExplainer | None,
        channels: tuple[NotificationChannel, ...],
        cooldown: timedelta = timedelta(minutes=15),
        explanation_timeout_seconds: int = 20,
    ) -> None:
        self._stream = stream
        self._store = store
        self._rule = rule
        self._context_resolver = context_resolver
        self._explainer = explainer
        self._channels = channels
        self._cooldown = cooldown
        self._explanation_timeout_seconds = explanation_timeout_seconds
        self._calculator = FeatureCalculator(lookback=5)

    def process(self, message: StreamMessage, *, group: str) -> ProcessResult:
        persistence = self._store.persist_bar(message.bar)
        if persistence is BarPersistence.OUT_OF_ORDER:
            self._stream.acknowledge(group=group, message_id=message.id)
            return ProcessResult("OUT_OF_ORDER", None, None)
        history = self._store.recent_bars(
            symbol=str(message.bar.symbol),
            through=message.bar.event_time,
            limit=6,
        )
        if len(history) < 6:
            self._stream.acknowledge(group=group, message_id=message.id)
            return ProcessResult("INSUFFICIENT_HISTORY", None, None)
        features = self._calculator.calculate(history, evaluated_at=message.bar.ingested_at)
        evaluation = self._rule.evaluate(features)
        if not evaluation.triggered:
            self._stream.acknowledge(group=group, message_id=message.id)
            return ProcessResult("NO_ALERT", None, features)
        identity = AlertIdentity.for_trigger(
            symbol=str(features.symbol),
            rule_id=evaluation.rule_id,
            event_time=features.event_time,
            cooldown=self._cooldown,
        )
        context = self._context_resolver(str(features.symbol), features.event_time)
        review_action = (
            "REVIEW_INVALIDATION_CONDITION"
            if context.invalidation_condition
            else "REVIEW_ACTIVE_THESIS"
        )
        self._store.persist_alert(
            alert_id=identity.id,
            alert_key=identity.key,
            features=features,
            evaluation=evaluation,
            context=context,
            review_action=review_action,
            channels=self._channels,
        )
        if self._explainer is None:
            self._store.record_explanation(
                alert_id=identity.id,
                status=ExplanationStatus.DISABLED,
                content=None,
                error_code=None,
            )
        else:
            try:
                explanation = self._explainer.explain(
                    features=features,
                    evaluation=evaluation,
                    context=context,
                    timeout_seconds=self._explanation_timeout_seconds,
                )
            except TimeoutError:
                self._store.record_explanation(
                    alert_id=identity.id,
                    status=ExplanationStatus.FAILED,
                    content=None,
                    error_code="TIMEOUT",
                )
            except Exception:  # noqa: BLE001 - explanation cannot suppress deterministic alert
                self._store.record_explanation(
                    alert_id=identity.id,
                    status=ExplanationStatus.FAILED,
                    content=None,
                    error_code="EXPLANATION_ERROR",
                )
            else:
                self._store.record_explanation(
                    alert_id=identity.id,
                    status=ExplanationStatus.SUCCEEDED,
                    content=explanation,
                    error_code=None,
                )
        self._stream.acknowledge(group=group, message_id=message.id)
        return ProcessResult("ALERT", identity.id, features)
