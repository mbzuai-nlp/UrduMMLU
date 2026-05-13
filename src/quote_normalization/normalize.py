#!/usr/bin/env python3
"""Normalize quotation marks in Urdu MCQ JSON files.

The source data has artifacts like ``دادِ سخن”” کے مصنف کون ہیں`` where
the opening quote was lost during OCR/scraping and the closing quote was
duplicated. This step:

1. Replaces curly quotes (U+201C, U+201D) with ASCII straight ``"``.
2. Collapses runs of adjacent ``"`` into a single ``"``.
3. If the result has an odd number of ``"``, prepends one to the string
   (covers the dominant case where the quoted phrase begins at the start
   of the question).

Reads ``data/4-rtl-aligned/*.json`` and writes to
``data/5-quote-normalized/*.json``.
"""

import json
import re
from pathlib import Path

CURLY_OPEN = "“"
CURLY_CLOSE = "”"
STRAIGHT = '"'

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "4-rtl-aligned"
DST_DIR = REPO_ROOT / "data" / "5-quote-normalized"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]


def normalize_quotes(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    out = text.replace(CURLY_OPEN, STRAIGHT).replace(CURLY_CLOSE, STRAIGHT)
    out = re.sub(r'"{2,}', STRAIGHT, out)
    if out.count(STRAIGHT) % 2 == 1:
        out = STRAIGHT + out
    return out


def fix_item(item: dict, stats: dict) -> dict:
    q = item.get("question", "")
    new_q = normalize_quotes(q)
    if new_q != q:
        stats["questions"] += 1
    item["question"] = new_q

    options = item.get("options")
    if isinstance(options, dict):
        for key, value in options.items():
            if isinstance(value, str):
                new_v = normalize_quotes(value)
                if new_v != value:
                    stats["options"] += 1
                options[key] = new_v
    elif isinstance(options, list):
        for i, value in enumerate(options):
            if isinstance(value, str):
                new_v = normalize_quotes(value)
                if new_v != value:
                    stats["options"] += 1
                options[i] = new_v

    correct = item.get("correct_option")
    if isinstance(correct, str):
        new_c = normalize_quotes(correct)
        if new_c != correct:
            stats["correct_options"] += 1
        item["correct_option"] = new_c

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
        print(f"  questions changed:     {stats['questions']}")
        print(f"  options changed:       {stats['options']}")
        print(f"  correct_options changed: {stats['correct_options']}")
        print()


if __name__ == "__main__":
    main()
