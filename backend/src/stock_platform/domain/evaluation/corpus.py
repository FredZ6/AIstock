"""Integrity-checked frozen evaluation corpus loading."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .cases import EvalCase, JudgeKind, load_cases

LOCKED_DISTRIBUTION = {
    "alert": 20,
    "evidence": 30,
    "learning": 20,
    "portfolio": 20,
    "research": 40,
    "security": 30,
    "tool": 40,
}
LOCKED_LAYERS = {
    "L0": 20,
    "L1": 20,
    "L2": 40,
    "L3": 30,
    "L4": 20,
    "L5": 20,
    "L6": 20,
    "L7": 30,
}
LOCKED_DATASET_VERSION = "eval-v0.2.0"


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: StrictInt = Field(ge=1)
    corpus_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_version: StrictStr
    distribution: dict[StrictStr, StrictInt]
    file_sha256: dict[StrictStr, StrictStr]
    layers: dict[StrictStr, StrictInt]
    license: StrictStr
    mode: StrictStr
    provenance: StrictStr


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_sha256(file_hashes: dict[str, str]) -> str:
    payload = "".join(f"{name}\0{digest}\n" for name, digest in sorted(file_hashes.items()))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_corpus(dataset_dir: Path) -> tuple[CorpusManifest, tuple[EvalCase, ...]]:
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("evaluation corpus manifest is missing")
    manifest = CorpusManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    paths = sorted(dataset_dir.glob("*.jsonl"))
    actual_names = {path.name for path in paths}
    expected_names = {f"{category}.jsonl" for category in LOCKED_DISTRIBUTION}
    if actual_names != expected_names:
        raise ValueError("evaluation corpus manifest file set does not match locked datasets")
    actual_hashes = {path.name: file_sha256(path) for path in paths}
    if actual_hashes != manifest.file_sha256:
        raise ValueError("evaluation corpus manifest file hash mismatch")
    if corpus_sha256(actual_hashes) != manifest.corpus_sha256:
        raise ValueError("evaluation corpus manifest digest mismatch")
    cases = load_cases(paths)
    distribution = dict(sorted(Counter(case.category for case in cases).items()))
    layers = dict(sorted(Counter(case.layer.value for case in cases).items()))
    versions = {case.dataset_version for case in cases}
    if (
        manifest.case_count != 200
        or len(cases) != manifest.case_count
        or manifest.dataset_version != LOCKED_DATASET_VERSION
        or versions != {LOCKED_DATASET_VERSION}
        or manifest.distribution != LOCKED_DISTRIBUTION
        or distribution != LOCKED_DISTRIBUTION
        or manifest.layers != LOCKED_LAYERS
        or layers != LOCKED_LAYERS
        or manifest.mode != "fixture"
        or any(case.fixture_manifest != "manifest.json" for case in cases)
        or any(case.judge_kind is not JudgeKind.DETERMINISTIC for case in cases)
    ):
        if any(case.judge_kind is not JudgeKind.DETERMINISTIC for case in cases):
            raise ValueError("fixture corpus requires a deterministic judge for every case")
        raise ValueError("evaluation corpus manifest does not match locked contract")
    return manifest, cases
