"""Idempotent deterministic alert worker; explanations are non-authoritative."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from queue import Empty, Queue
from threading import Thread
from typing import Protocol
from uuid import UUID

from stock_platform.application.alerting.dedup import AlertIdentity
from stock_platform.application.alerting.features import (
    AnomalyFeatures,
    FeatureCalculator,
    GapContext,
    MinuteBar,
)
from stock_platform.application.alerting.outbox import (
    AlertContext,
    BarPersistence,
    NotificationChannel,
)
from stock_platform.application.alerting.rules import AlertRule, RuleEvaluation
from stock_platform.infrastructure.messaging.market_stream import StreamMessage

_MAX_EXPLANATION_LENGTH = 4000


class InvalidExplanationOutput(ValueError):
    pass


def _validate_explanation_output(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidExplanationOutput("explanation must be a string")
    normalized = value.strip()
    if not normalized:
        raise InvalidExplanationOutput("explanation cannot be empty")
    if len(normalized) > _MAX_EXPLANATION_LENGTH:
        raise InvalidExplanationOutput("explanation exceeds maximum length")
    return normalized


class ExplanationStatus(StrEnum):
    DISABLED = "DISABLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AlertStream(Protocol):
    def acknowledge(self, *, group: str, message_id: str) -> None: ...


class AlertStore(Protocol):
    def persist_bar(self, item: MinuteBar) -> BarPersistence | bool: ...

    def recent_bars(
        self, *, symbol: str, through: datetime, available_by: datetime, limit: int
    ) -> tuple[MinuteBar, ...]: ...

    def gap_context(
        self, *, symbol: str, through: datetime, available_by: datetime
    ) -> GapContext | None: ...

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

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


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
        explanation_timeout_seconds: float = 20,
    ) -> None:
        if explanation_timeout_seconds <= 0:
            raise ValueError("explanation_timeout_seconds must be positive")
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
        try:
            result = self._process(message)
        except Exception:
            self._store.rollback()
            raise
        self._store.commit()
        self._stream.acknowledge(group=group, message_id=message.id)
        return result

    def _process(self, message: StreamMessage) -> ProcessResult:
        persistence = self._store.persist_bar(message.bar)
        if persistence is BarPersistence.OUT_OF_ORDER:
            return ProcessResult("OUT_OF_ORDER", None, None)
        history = self._store.recent_bars(
            symbol=str(message.bar.symbol),
            through=message.bar.event_time,
            available_by=message.bar.ingested_at,
            limit=6,
        )
        if len(history) < 6:
            return ProcessResult("INSUFFICIENT_HISTORY", None, None)
        gap_context = self._store.gap_context(
            symbol=str(message.bar.symbol),
            through=message.bar.event_time,
            available_by=message.bar.ingested_at,
        )
        features = self._calculator.calculate(
            history,
            evaluated_at=message.bar.ingested_at,
            gap_context=gap_context,
        )
        evaluation = self._rule.evaluate(features)
        if not evaluation.triggered:
            return ProcessResult("NO_ALERT", None, features)
        identity = AlertIdentity.for_trigger(
            symbol=str(features.symbol),
            rule_id=evaluation.rule_id,
            event_time=features.event_time,
            cooldown=self._cooldown,
        )
        context = self._context_resolver(str(features.symbol), message.bar.ingested_at)
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
                explanation = self._explain_with_deadline(features, evaluation, context)
            except TimeoutError:
                self._store.record_explanation(
                    alert_id=identity.id,
                    status=ExplanationStatus.FAILED,
                    content=None,
                    error_code="TIMEOUT",
                )
            except InvalidExplanationOutput:
                self._store.record_explanation(
                    alert_id=identity.id,
                    status=ExplanationStatus.FAILED,
                    content=None,
                    error_code="INVALID_OUTPUT",
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
        return ProcessResult("ALERT", identity.id, features)

    def _explain_with_deadline(
        self,
        features: AnomalyFeatures,
        evaluation: RuleEvaluation,
        context: AlertContext,
    ) -> str:
        assert self._explainer is not None
        explainer = self._explainer
        result: Queue[tuple[object | None, Exception | None]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                explanation = explainer.explain(
                    features=features,
                    evaluation=evaluation,
                    context=context,
                    timeout_seconds=self._explanation_timeout_seconds,
                )
            except Exception as error:  # noqa: BLE001 - forwarded to the worker boundary
                result.put((None, error))
            else:
                result.put((explanation, None))

        Thread(target=invoke, name="alert-explanation", daemon=True).start()
        try:
            explanation, error = result.get(timeout=self._explanation_timeout_seconds)
        except Empty as timeout:
            raise TimeoutError("explanation exceeded budget") from timeout
        if error is not None:
            raise error
        return _validate_explanation_output(explanation)
