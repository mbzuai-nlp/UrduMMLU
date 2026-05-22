#!/usr/bin/env python3
"""Drop ``error: true`` rows from a predictions.json so the next run
re-attempts those MCQs.

Walks ``output/<lang>/<model>/predictions.json`` and removes rows whose
``error`` field is truthy. Other rows are preserved untouched.

Usage:
    python src/analysis/clean_errors.py                          # all langs / models
    python src/analysis/clean_errors.py --lang ur
    python src/analysis/clean_errors.py --model claude-haiku-4-5 --model claude-sonnet-4-6
    python src/analysis/clean_errors.py --dry-run                # report without writing
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", help="Restrict to a single language directory")
    parser.add_argument(
        "--model", action="append", default=[],
        help="Restrict to model name substring (repeatable). Default = all models.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    langs = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())
    total_dropped = 0
    for lang in langs:
        if args.lang and lang != args.lang:
            continue
        for path in sorted((OUTPUT_DIR / lang).glob("*/predictions.json")):
            model = path.parent.name
            if args.model and not any(m in model for m in args.model):
                continue
            records = json.load(open(path, encoding="utf-8"))
            cleaned = [r for r in records if not r.get("error")]
            dropped = len(records) - len(cleaned)
            total_dropped += dropped
            tag = "dry-run" if args.dry_run else "wrote"
            print(f"[{lang}/{model:<32}] {tag}: kept {len(cleaned):,}, dropped {dropped}")
            if dropped and not args.dry_run:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(f"\nTotal dropped: {total_dropped}")


if __name__ == "__main__":
    main()
