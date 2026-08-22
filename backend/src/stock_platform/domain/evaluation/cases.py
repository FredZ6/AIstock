"""Strict, reproducible frozen evaluation-case contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_serializer,
    model_validator,
)

from stock_platform.domain.common.time import require_aware

from .results import EvalVerdict


class EvalLayer(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"
    L7 = "L7"


class JudgeKind(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    CALIBRATED_LLM = "CALIBRATED_LLM"


class PolicyVersions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: StrictStr = Field(min_length=1)
    execution: StrictStr = Field(min_length=1)
    research_scoring: StrictStr = Field(min_length=1)
    risk: StrictStr = Field(min_length=1)


def _canonical_time(value: Any) -> Any:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        return value
    return require_aware(parsed).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    return value


def case_payload_hash(payload: Mapping[str, Any]) -> str:
    unsigned = {
        key: _thaw_json(value)
        for key, value in payload.items()
        if key != "case_hash" and not (key == "judge_calibration_version" and value is None)
    }
    if "as_of" in unsigned:
        unsigned["as_of"] = _canonical_time(unsigned["as_of"])
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: StrictStr = Field(min_length=1)
    layer: EvalLayer
    category: Literal["tool", "research", "evidence", "security", "alert", "portfolio", "learning"]
    symbol: StrictStr = Field(pattern=r"^[A-Z.]{1,10}$")
    as_of: datetime
    fixture_manifest: StrictStr = Field(min_length=1)
    judge_kind: JudgeKind
    judge_version: StrictStr = Field(min_length=1)
    judge_calibration_version: StrictStr | None = None
    required_capabilities: tuple[StrictStr, ...]
    forbidden_tools: tuple[StrictStr, ...]
    expected_invariants: tuple[StrictStr, ...]
    dataset_version: StrictStr = Field(min_length=1)
    model_version: StrictStr = Field(min_length=1)
    prompt_version: StrictStr = Field(min_length=1)
    policy_versions: PolicyVersions
    random_seed: StrictInt
    raw_output: Mapping[str, Any]
    trace: tuple[Mapping[str, Any], ...]
    latency_ms: StrictInt = Field(ge=0)
    token_usage: StrictInt = Field(ge=0)
    cost_usd: StrictStr
    verdict: EvalVerdict
    case_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="before")
    @classmethod
    def verify_payload_hash(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            expected = value.get("case_hash")
            if isinstance(expected, str) and case_payload_hash(value) != expected:
                raise ValueError("case_hash does not match canonical payload")
        return value

    @model_validator(mode="after")
    def enforce_invariants(self) -> Self:
        aware = require_aware(self.as_of).astimezone(UTC)
        object.__setattr__(self, "as_of", aware)
        object.__setattr__(self, "raw_output", _freeze_json(self.raw_output))
        object.__setattr__(self, "trace", _freeze_json(self.trace))
        try:
            cost = Decimal(self.cost_usd)
        except InvalidOperation as error:
            raise ValueError("cost_usd must be a Decimal string") from error
        if not cost.is_finite() or cost < 0:
            raise ValueError("cost_usd must be finite and non-negative")
        if self.judge_kind is JudgeKind.CALIBRATED_LLM and not self.judge_calibration_version:
            raise ValueError("calibrated LLM judge requires a calibration version")
        if (
            self.judge_kind is JudgeKind.DETERMINISTIC
            and self.judge_calibration_version is not None
        ):
            raise ValueError("deterministic judge cannot carry LLM calibration")
        return self

    @field_serializer("raw_output", "trace")
    def serialize_frozen_json(self, value: Any) -> Any:
        return _thaw_json(value)

    def hashed_payload(self) -> dict[str, Any]:
        """Return the canonical JSON payload whose digest is ``case_hash``."""
        payload = self.model_dump(mode="json", exclude={"case_hash"}, exclude_none=True)
        payload["as_of"] = self.as_of.astimezone(UTC).isoformat().replace("+00:00", "Z")
        payload["case_hash"] = case_payload_hash(payload)
        return payload


def load_cases(paths: Iterable[Path]) -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = EvalCase.model_validate_json(line)
            if case.case_id in seen:
                raise ValueError(f"duplicate case_id: {case.case_id}")
            seen.add(case.case_id)
            cases.append(case)
    return tuple(cases)
