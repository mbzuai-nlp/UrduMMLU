#!/usr/bin/env python3
"""Fix bidi alignment issues in Urdu MCQ JSON files.

Strings that contain Urdu but start with a neutral character (e.g. ``____``,
digits, punctuation) or a Latin letter are rendered with an LTR paragraph
base direction by the Unicode bidi algorithm. The fix is to prepend a
Right-to-Left Mark (U+200F) so the renderer treats the paragraph as RTL.

Reads ``data/3-consolidated/*.json``, writes the fixed copies to
``data/4-rtl-aligned/*.json``, and prints how many strings were changed.
"""

import json
import re
from pathlib import Path

RLM = "‏"
URDU_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "3-consolidated"
DST_DIR = REPO_ROOT / "data" / "4-rtl-aligned"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json", "mcqs_upsampled.json"]


def needs_rlm(text: str) -> bool:
    """True if `text` contains Urdu but doesn't start with a strong RTL char.

    Strings whose first character is already strong RTL render correctly
    regardless of surrounding context. Everything else — leading neutrals
    (``____``, digits, punctuation) or leading Latin letters — risks being
    rendered with LTR direction by an embedding viewer, so we prepend RLM.
    """
    if not isinstance(text, str) or not text or text.startswith(RLM):
        return False
    if not URDU_RE.search(text):
        return False
    first = text[0]
    if "؀" <= first <= "ۿ" or "ݐ" <= first <= "ݿ":
        return False
    return True


def fix_string(text: str) -> str:
    return RLM + text if needs_rlm(text) else text


def fix_item(item: dict, stats: dict) -> dict:
    q = item.get("question", "")
    fixed_q = fix_string(q)
    if fixed_q != q:
        stats["questions"] += 1
    item["question"] = fixed_q

    options = item.get("options")
    if isinstance(options, dict):
        for key, value in options.items():
            fixed_v = fix_string(value) if isinstance(value, str) else value
            if fixed_v != value:
                stats["options"] += 1
            options[key] = fixed_v

    correct = item.get("correct_option")
    if isinstance(correct, str):
        fixed_c = fix_string(correct)
        if fixed_c != correct:
            stats["correct_options"] += 1
        item["correct_option"] = fixed_c

    return item


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = {"total": len(data), "questions": 0, "options": 0, "correct_options": 0}
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
        print(f"{name}")
        print(f"  total items:           {stats['total']}")
        print(f"  questions fixed:       {stats['questions']}")
        print(f"  options fixed:         {stats['options']}")
        print(f"  correct_options fixed: {stats['correct_options']}")
        print()


if __name__ == "__main__":
    main()
