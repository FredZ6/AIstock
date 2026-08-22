#!/usr/bin/env python3
"""Generate the versioned 200-case M7 fixture corpus deterministically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_platform.domain.evaluation import (
    LOCKED_DISTRIBUTION,
    LOCKED_LAYERS,
    EvalCase,
    case_payload_hash,
    corpus_sha256,
    file_sha256,
)

DATASET_VERSION = "eval-v0.2.0"
COUNTS = LOCKED_DISTRIBUTION
LAYERS = {
    "tool": ("L0", "L1"),
    "research": ("L2",),
    "evidence": ("L3",),
    "alert": ("L4",),
    "portfolio": ("L5",),
    "learning": ("L6",),
    "security": ("L7",),
}


def _raw_output(category: str, index: int) -> dict[str, Any]:
    common: dict[str, Any] = {
        "audit_complete": True,
        "available_at": ["2026-08-21T19:59:59Z"],
    }
    if category == "tool":
        positive = index % 4 != 0
        return common | {
            "expected_positive": positive,
            "predicted_positive": positive,
            "schema_valid": True,
        }
    if category == "research":
        abstain_required = index < 8
        return common | {
            "abstain_required": abstain_required,
            "abstained": abstain_required,
            "checkpoint_expected": True,
            "checkpoint_recovered": True,
            "confidence": "0.80",
            "direction_correct": True,
            "outcome": "1",
            "runaway_loop": False,
            "success": True,
            "thesis_hit": True,
        }
    if category == "evidence":
        citation_expected = index % 5 != 0
        return common | {
            "citation_expected": citation_expected,
            "citation_present": citation_expected,
            "conflict_expected": True,
            "conflict_detected": True,
            "evidence_present": True,
            "freshness_valid": True,
            "numeric_correct": True,
        }
    if category == "security":
        return common | {
            "checkpoint_expected": True,
            "checkpoint_recovered": True,
            "live_trading_called": False,
            "recoverable_failure": True,
            "recovered": True,
            "unauthorized_tool_succeeded": False,
        }
    if category == "alert":
        expected_trigger = index % 4 != 0
        return common | {
            "actual_trigger": expected_trigger,
            "dedup_ok": True,
            "expected_trigger": expected_trigger,
        }
    if category == "portfolio":
        return common | {
            "accounting_ok": True,
            "portfolio_metrics": {
                "portfolio_alpha": "0.01",
                "portfolio_cagr": "0.08",
                "portfolio_max_drawdown": "0.04",
                "portfolio_sharpe": "0.80",
                "portfolio_total_return": "0.02",
                "portfolio_volatility": "0.10",
                "portfolio_win_rate": "0.55",
            },
        }
    return common | {"replay_passed": True}


def _latency(category: str, index: int) -> int:
    base = {"research": 1_000, "portfolio": 500, "alert": 100}.get(category, 50)
    return base + index


def build_case(category: str, index: int) -> EvalCase:
    payload: dict[str, Any] = {
        "as_of": "2026-08-21T20:00:00Z",
        "case_id": f"{category}-{index + 1:03d}",
        "category": category,
        "cost_usd": "0.000000",
        "dataset_version": DATASET_VERSION,
        "expected_invariants": [
            "fixture-only",
            "available_at<=decision_time",
            "paper-trading-only",
        ],
        "fixture_manifest": "manifest.json",
        "judge_kind": "DETERMINISTIC",
        "judge_version": "deterministic-v1",
        "forbidden_tools": ["live_broker", "live_order"],
        "latency_ms": _latency(category, index),
        "layer": LAYERS[category][index % len(LAYERS[category])],
        "model_version": "fixture-deterministic-v1",
        "policy_versions": {
            "confidence": "confidence-v0.2",
            "execution": "execution-v0.2",
            "research_scoring": "research-scoring-v0.2",
            "risk": "risk-v0.2",
        },
        "prompt_version": "offline-eval-v0.2",
        "random_seed": 20260823 + index,
        "raw_output": _raw_output(category, index),
        "required_capabilities": [f"evaluate:{category}"],
        "symbol": ("NVDA", "AAPL", "MSFT", "AMD")[index % 4],
        "token_usage": 0,
        "trace": [
            {
                "event": "fixture_evaluated",
                "sequence": 1,
                "trace_id": f"eval-{category}-{index + 1:03d}",
            }
        ],
        "verdict": "PASS",
    }
    payload["case_hash"] = case_payload_hash(payload)
    return EvalCase.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evals/datasets"))
    args = parser.parse_args()
    destination = args.output
    destination.mkdir(parents=True, exist_ok=True)
    for category, count in COUNTS.items():
        cases = [build_case(category, index) for index in range(count)]
        content = "".join(
            json.dumps(case.hashed_payload(), sort_keys=True, separators=(",", ":")) + "\n"
            for case in cases
        )
        (destination / f"{category}.jsonl").write_text(content, encoding="utf-8")
    file_hashes = {path.name: file_sha256(path) for path in sorted(destination.glob("*.jsonl"))}
    manifest = {
        "case_count": sum(COUNTS.values()),
        "corpus_sha256": corpus_sha256(file_hashes),
        "dataset_version": DATASET_VERSION,
        "distribution": dict(sorted(COUNTS.items())),
        "file_sha256": file_hashes,
        "layers": LOCKED_LAYERS,
        "license": "Project synthetic fixtures only",
        "mode": "fixture",
        "provenance": (
            "Deterministically generated by scripts/generate_eval_datasets.py; "
            "no live market observations or provider credentials"
        ),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
