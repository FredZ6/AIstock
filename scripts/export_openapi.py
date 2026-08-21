#!/usr/bin/env python3
"""Export the deterministic FastAPI contract (JSON is valid YAML)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_platform.api.main import app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/api/openapi.yaml"


def rendered_contract() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_contract()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != rendered:
            print(f"OpenAPI contract is stale: {OUTPUT}")
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
