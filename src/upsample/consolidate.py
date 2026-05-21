#!/usr/bin/env python3
"""Copy the standardized upsample file from Stage 2 → Stage 3.

Reads  data/2-processed/upsample_mcqs.json
Writes data/3-consolidated/mcqs_upsampled.json

The upsample is a single-source dataset, so consolidation here is a
straight copy — Stage 3 is just the entry point used by Stage-4+
scripts.

Usage:
    python src/upsample/consolidate.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "2-processed" / "upsample_mcqs.json"
DST = REPO_ROOT / "data" / "3-consolidated" / "mcqs_upsampled.json"


def main() -> None:
    data = json.load(open(SRC, encoding="utf-8"))
    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DST.relative_to(REPO_ROOT)} ({len(data)} records)")


if __name__ == "__main__":
    main()
