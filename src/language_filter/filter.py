#!/usr/bin/env python3
"""Stage 14 — drop English-prose questions sneaking into the Urdu dataset.

Some FBISE source rows were OCR'd / scraped as English text even though
the original PDF was Urdu (e.g. ``"When Akber died؟"`` in the
``art and drawing`` subdomain). This step removes those rows.

Rule:
  drop if  (question reads as English prose)  AND  (source includes "FBISE")

"English prose" = the question contains ≥2 English function words
(``the``, ``is``, ``a``, ``of``, ``in``, ``what``, ``who``, ``when``,
``which``, etc.) after stripping any ``$...$`` math segments. The
function-word heuristic avoids false positives on:
  - math expressions ("a + b = ?", "log5 8 × log8 125 =")
  - Urdu translation MCQs that legitimately quote an English idiom
    ("Out of the frying pan into the fire"), since the quoted text
    contains content words but very few function words.

The non-FBISE source restriction protects valid translation MCQs from
``etest`` / ``examaunty`` / ``Ustad 360`` which intentionally mix Urdu
and English.

Reads ``data/13-correlation-deduplicated/*.json`` and writes to
``data/14-english-filtered/*.json``. Dropped rows go to
``data/14-english-filtered/dropped.json`` for transparency.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "14-bidi-isolated"
DST_DIR = REPO_ROOT / "data" / "15-english-filtered"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json", "mcqs_upsampled.json"]

ENGLISH_FUNCTION_WORDS = frozenset({
    "the", "is", "are", "was", "were", "be", "been", "a", "an", "and", "or", "not",
    "of", "in", "on", "at", "to", "for", "with", "from", "by", "as", "this", "that",
    "these", "those", "what", "who", "whom", "where", "when", "why", "which", "how",
    "has", "have", "had", "do", "does", "did", "will", "would", "should", "could",
    "can", "may", "might", "must", "i", "you", "he", "she", "it", "we", "they", "us",
    "our", "his", "her", "their", "my", "your", "one", "two", "three", "all", "some",
})
WORD_RE = re.compile(r"[A-Za-z]{2,}")
MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.DOTALL)


def is_english_prose(question: str) -> bool:
    s = MATH_RE.sub(" ", (question or "").replace("‏", ""))
    fn_hits = sum(1 for t in WORD_RE.findall(s) if t.lower() in ENGLISH_FUNCTION_WORDS)
    return fn_hits >= 2


def should_drop(item: dict) -> bool:
    if not is_english_prose(item.get("question", "")):
        return False
    sources = item.get("source") or []
    if isinstance(sources, str):
        sources = [sources]
    return "FBISE" in sources


def process_file(src: Path, dst: Path) -> tuple[int, int, list]:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    kept, dropped = [], []
    for item in data:
        if should_drop(item):
            dropped.append(item)
        else:
            kept.append(item)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=4)
    return len(data), len(kept), dropped


def main() -> None:
    print(f"Source:      {SRC_DIR}")
    print(f"Destination: {DST_DIR}\n")
    DST_DIR.mkdir(parents=True, exist_ok=True)

    all_dropped = []
    for name in FILES:
        src = SRC_DIR / name
        dst = DST_DIR / name
        if not src.exists():
            print(f"Skip (not found): {src}")
            continue
        total, kept, dropped = process_file(src, dst)
        print(f"{name}")
        print(f"  input:    {total}")
        print(f"  kept:     {kept}")
        print(f"  dropped:  {len(dropped)}  ({100*len(dropped)/total:.2f}%)")
        if dropped:
            print(f"  examples:")
            for it in dropped[:3]:
                print(f"    id={it['id']} src={it.get('source')} sub={it.get('subdomain')}")
                print(f"      Q: {it['question'][:120]}")
        all_dropped.extend(dropped)
        print()

    if all_dropped:
        with open(DST_DIR / "dropped.json", "w", encoding="utf-8") as f:
            json.dump(all_dropped, f, ensure_ascii=False, indent=4)
        print(f"  wrote {DST_DIR / 'dropped.json'} ({len(all_dropped)} rows)")


if __name__ == "__main__":
    main()
