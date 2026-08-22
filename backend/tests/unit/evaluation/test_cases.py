from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from stock_platform.domain.evaluation import EvalCase, case_payload_hash, load_cases


def _canonical_hash(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "case_hash"}
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _case_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": "tool-001",
        "layer": "L1",
        "category": "tool",
        "symbol": "NVDA",
        "as_of": "2026-08-21T20:00:00Z",
        "fixture_manifest": "fixture-m1-v1",
        "judge_kind": "DETERMINISTIC",
        "judge_version": "deterministic-v1",
        "required_capabilities": ["market.price_bars"],
        "forbidden_tools": ["live_broker"],
        "expected_invariants": ["available_at_lte_decision_time"],
        "dataset_version": "eval-v0.2.0",
        "model_version": "fixture-model-v1",
        "prompt_version": "research-v1",
        "policy_versions": {
            "confidence": "confidence-v1",
            "execution": "execution-v1",
            "research_scoring": "research-scoring-v1",
            "risk": "risk-v1",
        },
        "random_seed": 16001,
        "raw_output": {
            "actual_tools": ["market.price_bars"],
            "expected_tools": ["market.price_bars"],
            "schema_valid": True,
        },
        "trace": [{"event": "tool.completed", "sequence": 1}],
        "latency_ms": 125,
        "token_usage": 0,
        "cost_usd": "0.0000",
        "verdict": "PASS",
    }
    payload.update(overrides)
    payload["case_hash"] = _canonical_hash(payload)
    return payload


def test_case_contract_preserves_all_reproducibility_pins() -> None:
    case = EvalCase.model_validate(_case_payload())

    assert case.case_id == "tool-001"
    assert case.as_of.isoformat() == "2026-08-21T20:00:00+00:00"
    assert case.cost_usd == "0.0000"
    assert case.judge_kind.value == "DETERMINISTIC"
    assert case.policy_versions.risk == "risk-v1"
    assert case.case_hash == _case_payload()["case_hash"]


def test_case_hash_is_stable_after_equivalent_offset_is_normalized_to_utc() -> None:
    payload = _case_payload(as_of="2026-08-22T04:00:00+08:00")
    payload["case_hash"] = case_payload_hash(payload)

    case = EvalCase.model_validate(payload)

    assert case.as_of.isoformat() == "2026-08-21T20:00:00+00:00"
    assert case.hashed_payload()["case_hash"] == case.case_hash


def test_case_hash_treats_explicit_optional_null_as_canonical_absence() -> None:
    payload = _case_payload(judge_calibration_version=None)
    payload["case_hash"] = case_payload_hash(payload)

    case = EvalCase.model_validate(payload)

    assert case.hashed_payload()["case_hash"] == case.case_hash


def test_case_raw_output_and_trace_are_deeply_immutable() -> None:
    case = EvalCase.model_validate(_case_payload())

    with pytest.raises(TypeError):
        cast(Any, case.raw_output)["schema_valid"] = False
    with pytest.raises(TypeError):
        cast(Any, case.trace[0])["event"] = "mutated"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"as_of": "2026-08-21T20:00:00"}, "timezone-aware"),
        ({"cost_usd": 0.0}, "string"),
        ({"layer": "L8"}, "layer"),
        ({"unexpected": "field"}, "Extra inputs"),
        ({"judge_kind": "CALIBRATED_LLM"}, "calibration"),
        (
            {
                "policy_versions": {
                    "confidence": "",
                    "execution": "execution-v1",
                    "research_scoring": "research-scoring-v1",
                    "risk": "risk-v1",
                }
            },
            "at least 1 character",
        ),
    ],
)
def test_case_contract_rejects_unsafe_or_unknown_values(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        EvalCase.model_validate(_case_payload(**overrides))


def test_case_contract_rejects_mutation_after_hashing() -> None:
    payload = _case_payload()
    payload["symbol"] = "AAPL"

    with pytest.raises(ValidationError, match="case_hash"):
        EvalCase.model_validate(payload)


def test_dataset_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "tool.jsonl"
    line = json.dumps(_case_payload(), sort_keys=True)
    dataset.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case_id: tool-001"):
        load_cases([dataset])
