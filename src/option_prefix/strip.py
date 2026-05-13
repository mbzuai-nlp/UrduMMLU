#!/usr/bin/env python3
"""Strip redundant option-letter prefixes from option values.

In the source data, option values often duplicate the dict key:
``"الف) TCP/IP"`` for option ``"A"``, ``"ب: کراچی"`` for option ``"B"``,
and so on. After this step the dict-key is the sole option marker and
values contain only the answer content.

A prefix is stripped only when its letter corresponds to the option's
**key**, e.g. ``الف`` is removed only from option A, ``ب`` only from
option B. This guards against stripping legitimate content that happens
to start with a single Urdu letter.

Number-prefixes such as ``0.``, ``1.``, ``12.`` are *not* stripped — they
are decimal numbers that belong to the answer content (e.g. ``1.698``).

Reads ``data/7-character-normalized/*.json`` and writes to
``data/8-option-prefix-stripped/*.json``.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "7-character-normalized"
DST_DIR = REPO_ROOT / "data" / "8-option-prefix-stripped"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

KEY_LETTERS = {
    "A": ["الف", "أ", "A"],
    "B": ["ب", "B"],
    "C": ["ج", "C"],
    "D": ["د", "D"],
    "E": ["ھ", "ہ", "E"],
}

SEPARATOR = r"[):\.\-۔]"
LEADING_NEUTRALS = r"[‏\s]*"


def strip_prefix(value: str, key: str) -> str:
    """Strip a `<letter><sep>` prefix from `value` when letter matches `key`.

    Preserves any leading RLM (U+200F) so the RTL alignment from step 4
    survives stripping.
    """
    if not isinstance(value, str) or not value:
        return value

    leading_rlm = "‏" if value.startswith("‏") else ""

    for letter in KEY_LETTERS.get(key, []):
        pat = rf"^{LEADING_NEUTRALS}{re.escape(letter)}\s*{SEPARATOR}\s*"
        if re.match(pat, value):
            stripped = re.sub(pat, "", value)
            return leading_rlm + stripped if leading_rlm and not stripped.startswith("‏") else stripped

    return value


def fix_item(item: dict, stats: dict) -> dict:
    options = item.get("options")
    correct_key = item.get("correct_key")

    if isinstance(options, dict):
        for key, value in list(options.items()):
            new_v = strip_prefix(value, key) if isinstance(value, str) else value
            if new_v != value:
                stats["options_stripped"] += 1
            options[key] = new_v

        # Re-derive correct_option from canonical invariant
        if correct_key and correct_key in options:
            new_co = options[correct_key]
            if item.get("correct_option") != new_co:
                stats["correct_option_updated"] += 1
            item["correct_option"] = new_co

    return item


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = {
        "total": len(data),
        "options_stripped": 0,
        "correct_option_updated": 0,
    }
    for item in data:
        fix_item(item, stats)

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
        print(f"{name}  (total {stats['total']})")
        print(f"  options stripped:        {stats['options_stripped']}")
        print(f"  correct_option updated:  {stats['correct_option_updated']}")
        print()


if __name__ == "__main__":
    main()
