#!/usr/bin/env python3
"""Normalize fill-in-the-blank placeholder runs to ``____``.

The source data uses many representations for "fill in the blank":

  - ASCII underscores of varying length (``___`` to ``__________``)
  - Em-dash runs (``————``)
  - En-dash runs (``–––––``)
  - Mixed sequences (``——_``)
  - Long ASCII hyphen runs (``----------``)

After this step every such run is exactly ``____`` (4 underscores). The
target form is universal, unambiguous, and trivially detectable by
downstream consumers.

Patterns:

  =================  =========================================
  Regex              What it matches
  =================  =========================================
  ``[_—–]{3,}``      3+ chars of any mix of underscore, em-dash,
                     en-dash. Catches the common case and any mix.
  ``-{4,}``          4+ ASCII hyphens. The threshold is higher
                     than 3 to avoid clobbering date ranges
                     (``2014-15``), list bullets (``- foo``), etc.
  =================  =========================================

LaTeX math segments delimited by ``$...$`` or ``$$...$$`` are passed
through untouched, so things like ``\\dots`` or arithmetic ``-``
inside equations are preserved.

Reads ``data/11-punctuation-normalized/*.json`` and writes to
``data/12-blanks-normalized/*.json``.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "11-punctuation-normalized"
DST_DIR = REPO_ROOT / "data" / "12-blanks-normalized"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

MATH_PATTERN = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.DOTALL)
BLANK_PATTERN = re.compile(r"[_—–]{3,}|-{4,}")
TARGET = "____"


def _transform_segment(s: str, counts: dict) -> str:
    def sub(m):
        counts["runs"] += 1
        counts["chars_collapsed"] += len(m.group()) - len(TARGET)
        return TARGET
    return BLANK_PATTERN.sub(sub, s)


def normalize(text: str, counts: dict) -> str:
    if not isinstance(text, str) or not text:
        return text

    parts = []
    last = 0
    for m in MATH_PATTERN.finditer(text):
        if m.start() > last:
            parts.append(_transform_segment(text[last:m.start()], counts))
        parts.append(m.group(0))
        last = m.end()
    if last < len(text):
        parts.append(_transform_segment(text[last:], counts))

    return "".join(parts)


def fix_item(item: dict, counts: dict) -> dict:
    q = item.get("question", "")
    item["question"] = normalize(q, counts)

    options = item.get("options")
    if isinstance(options, dict):
        for k, v in options.items():
            if isinstance(v, str):
                options[k] = normalize(v, counts)

    co = item.get("correct_option")
    if isinstance(co, str):
        item["correct_option"] = normalize(co, counts)

    return item


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    counts = {"runs": 0, "chars_collapsed": 0}
    for item in data:
        fix_item(item, counts)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return {"total": len(data), **counts}


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
        print(f"  runs collapsed → ____: {stats['runs']}")
        print(f"  chars removed:         {stats['chars_collapsed']}")
        print()


if __name__ == "__main__":
    main()
