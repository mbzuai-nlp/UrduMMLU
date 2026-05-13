#!/usr/bin/env python3
"""Normalize ASCII punctuation to Urdu equivalents in non-math text.

Substitutions:

  =====  ========  ====================================
  From   To        Rule
  =====  ========  ====================================
  ``...``  ``…``   Always (outside math).
  ``?``    ``؟``   Always (outside math).
  ``,``    ``،``   Only when not between two digits — preserves ``1,000``.
  ``.``    ``۔``   Only when preceded by an Urdu letter — preserves
                   decimals (``1.698``), abbreviations (``Mr.``), etc.
  =====  ========  ====================================

LaTeX math segments delimited by ``$...$`` or ``$$...$$`` are passed
through untouched so equation content keeps its ASCII punctuation.

Reads ``data/10-structural-cleaned/*.json`` and writes to
``data/11-punctuation-normalized/*.json``.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "10-structural-cleaned"
DST_DIR = REPO_ROOT / "data" / "11-punctuation-normalized"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

MATH_PATTERN = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.DOTALL)
URDU_RANGE = r"؀-ۿ"


def _transform_segment(s: str, counts: dict) -> str:
    if "..." in s:
        counts["ellipsis"] += s.count("...")
        s = s.replace("...", "…")

    if "?" in s:
        counts["question_mark"] += s.count("?")
        s = s.replace("?", "؟")

    s, n = re.subn(r"(?<!\d),(?!\d)", "،", s)
    counts["comma"] += n

    s, n = re.subn(rf"([{URDU_RANGE}])\.", r"\1۔", s)
    counts["period"] += n

    return s


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

    counts = {"ellipsis": 0, "question_mark": 0, "comma": 0, "period": 0}
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
        print(f"  ...     → …   {stats['ellipsis']}")
        print(f"  ?       → ؟   {stats['question_mark']}")
        print(f"  ,       → ،   {stats['comma']}")
        print(f"  Urdu+.  → Urdu+۔   {stats['period']}")
        print()


if __name__ == "__main__":
    main()
