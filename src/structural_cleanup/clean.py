#!/usr/bin/env python3
"""Drop structurally-broken MCQs and normalize `options` to a dict.

For each row we:

  1. If `options` is a list of strings, convert it to ``{'A': v0, 'B': v1, ...}``.
  2. Drop the row if any of:

     a. The question text is empty or whitespace-only.
     b. `options` is missing or not convertible to a dict.
     c. The option count is not 4 or 5 (legitimate 5-option MCQs use ``E``).
     d. Any option value is empty / whitespace-only (after stripping
        the leading RLM marker added in step 4).
     e. Two or more options have identical content.
     f. `correct_option` is set but no longer matches any option value
        (defensive — canonicalization should already guarantee this).

The 46 legitimate 5-option MCQs (key ``E`` present, all options
distinct) survive.

Reads ``data/9-comparison-deduplicated/*.json`` and writes to
``data/10-structural-cleaned/*.json``.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "9-comparison-deduplicated"
DST_DIR = REPO_ROOT / "data" / "10-structural-cleaned"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

ALLOWED_OPTION_COUNTS = {4, 5}


def squashed(text):
    """Strip leading RLM (U+200F) and surrounding whitespace for emptiness checks."""
    if not isinstance(text, str):
        return ""
    return text.replace("‏", "").strip()


def normalize_options(item, stats):
    """Convert list-shaped `options` to a dict in place."""
    options = item.get("options")
    if isinstance(options, list) and all(isinstance(v, str) for v in options):
        if len(options) in ALLOWED_OPTION_COUNTS:
            keys = [chr(ord("A") + i) for i in range(len(options))]
            item["options"] = {k: v for k, v in zip(keys, options)}
            stats["normalized_list_to_dict"] = stats.get("normalized_list_to_dict", 0) + 1


def drop_reason(item):
    if not squashed(item.get("question", "")):
        return "empty_question"

    options = item.get("options")
    if not isinstance(options, dict):
        return "non_dict_options"
    if len(options) not in ALLOWED_OPTION_COUNTS:
        return "wrong_option_count"

    values = list(options.values())
    if any(not squashed(v) for v in values):
        return "empty_option"

    # Duplicate detection uses the squashed form so trivial whitespace
    # differences don't escape it.
    normalized = [squashed(v) for v in values]
    if len(set(normalized)) != len(normalized):
        return "duplicate_options"

    co = item.get("correct_option")
    if co is not None and squashed(co) not in {squashed(v) for v in values}:
        return "correct_option_unresolved"

    return None


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    out = []
    drop_counts = {}
    normalize_stats = {}
    for item in data:
        normalize_options(item, normalize_stats)
        reason = drop_reason(item)
        if reason is None:
            out.append(item)
        else:
            drop_counts[reason] = drop_counts.get(reason, 0) + 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)

    return {
        "input_rows": len(data),
        "output_rows": len(out),
        "dropped": sum(drop_counts.values()),
        "by_reason": drop_counts,
        "normalized_list_to_dict": normalize_stats.get("normalized_list_to_dict", 0),
    }


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
        print(f"  input rows:                {stats['input_rows']}")
        print(f"  output rows:               {stats['output_rows']}")
        print(f"  options list→dict:         {stats['normalized_list_to_dict']}")
        print(f"  dropped:                   {stats['dropped']}")
        for reason, n in sorted(stats["by_reason"].items(), key=lambda x: -x[1]):
            print(f"    {reason:<28} {n}")
        print()


if __name__ == "__main__":
    main()
