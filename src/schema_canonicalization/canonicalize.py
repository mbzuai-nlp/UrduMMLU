#!/usr/bin/env python3
"""Canonicalize the correct-answer fields across all sources.

Upstream sources disagree on what `correct_option` stores:
  - testpointpk / etest / examaunty / gotest store the letter (``'A'``..``'E'``).
  - mcqtimes / pakmcqs / native_mcqs store the full option *text*.

After this step the schema is:
  - ``correct_option`` — the full **text** of the correct answer
    (matches the corresponding value in ``options``).
  - ``correct_key``    — the **option key** (``'A'``..``'E'``) into ``options``.

The old ``correct_index`` field is removed (its 0-vs-1-based meaning was
ambiguous and the dict key carries the same information unambiguously).
Both fields are derived from the original ``correct_index`` (verified
consistent across schemas). Rows where the answer is unknown have
``correct_option = None`` and ``correct_key = None``.

Reads ``data/5-quote-normalized/*.json`` and writes to
``data/6-schema-canonicalized/*.json``.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "5-quote-normalized"
DST_DIR = REPO_ROOT / "data" / "6-schema-canonicalized"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json", "mcqs_upsampled.json"]


def canonicalize(item: dict, stats: dict) -> dict:
    opts = item.get("options")
    ci = item.get("correct_index")
    opt_keys = list(opts.keys()) if isinstance(opts, dict) else []

    if isinstance(ci, int) and 0 <= ci < len(opt_keys):
        key = opt_keys[ci]
        new_co = opts[key]
        new_ck = key
    else:
        new_co = None
        new_ck = None
        stats["no_answer"] += 1

    if item.get("correct_option") != new_co:
        stats["changed"] += 1

    item["correct_option"] = new_co
    item.pop("correct_index", None)

    # place `correct_key` right after `correct_option` for readability
    ordered = {}
    for k, v in item.items():
        ordered[k] = v
        if k == "correct_option":
            ordered["correct_key"] = new_ck
    if "correct_key" not in ordered:
        ordered["correct_key"] = new_ck
    item.clear()
    item.update(ordered)
    return item


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = {"total": len(data), "changed": 0, "no_answer": 0}
    for item in data:
        canonicalize(item, stats)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return stats


def main() -> None:
    print(f"Source:      {SRC_DIR}")
    print(f"Destination: {DST_DIR}\n")

    for name in FILES:
        src = SRC_DIR / name
        dst = DST_DIR / name
        if not src.exists():
            print(f"Skip (not found): {src}")
            continue

        stats = process_file(src, dst)
        print(f"{name}")
        print(f"  total items:            {stats['total']}")
        print(f"  correct_option changed: {stats['changed']}")
        print(f"  no answer recorded:     {stats['no_answer']}")
        print()


if __name__ == "__main__":
    main()
