#!/usr/bin/env python3
"""Remove parse-fail records from a predictions.json file.

A record is a parse fail when neither the pattern-based parser nor the
option-text fallback can extract an A/B/C/D key from the prediction field.
Records with API errors (prediction starts with ERROR/CONNECTION_FAILED) are
kept, since they are tracked separately from parse failures.

Usage:
    python src/analysis/filter_parse_fails.py predictions.json
    python src/analysis/filter_parse_fails.py predictions.json --output cleaned.json
    python src/analysis/filter_parse_fails.py predictions.json --inplace
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval import parse_key, parse_key_from_options


def is_parse_fail(record: dict) -> bool:
    pred = record.get("prediction") or ""
    if str(pred).startswith(("ERROR", "CONNECTION_FAILED")):
        return False
    key = parse_key(pred)
    if key is None:
        key = parse_key_from_options(pred, record.get("options") or {})
    return key is None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to predictions.json")
    parser.add_argument("--output", "-o", help="Write filtered results here (default: <input>_filtered.json)")
    parser.add_argument("--inplace", action="store_true", help="Overwrite the input file")
    args = parser.parse_args()

    input_path = Path(args.input)
    records: list[dict] = json.loads(input_path.read_text(encoding="utf-8"))

    before = len(records)
    filtered = [r for r in records if not is_parse_fail(r)]
    removed = before - len(filtered)

    if args.inplace:
        out_path = input_path
    elif args.output:
        out_path = Path(args.output)
    else:
        out_path = input_path.with_stem(input_path.stem + "_filtered")

    out_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Records before : {before}")
    print(f"Parse fails removed: {removed}")
    print(f"Records after  : {len(filtered)}")
    print(f"Written to     : {out_path}")


if __name__ == "__main__":
    main()
