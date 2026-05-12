#!/usr/bin/env python3
"""
Merge ahmer_mcqs.json + native_urdu_mcqs.json → mcqs_with_answers.json
=======================================================================

Schema differences handled
---------------------------
ahmer_mcqs.json
  - correct_option : answer TEXT  (e.g. "محمد رفیع سودا")
    → letter derived from correct_index  (0→"A", 1→"B", ...)
  - source_url     : URL field name
  - subdomain      : already a slug  (e.g. "urdu_literature")
  - domain         : top-level name  (e.g. "Humanities")

native_urdu_mcqs.json
  - correct_answer : answer LETTER  (e.g. "A")
  - url            : URL field name  → renamed to source_url
  - subdomain      : display text    (e.g. "Everyday Science MCQs")
  - std_subdomain  : canonical slug  (e.g. "everyday_science")  ← used
  - std_domain     : canonical name  (e.g. "STEM")              ← used

Deduplication
-------------
ahmer entries are loaded first and take priority.
Any native question whose text already exists in the ahmer set is dropped.

Output schema  (mcqs_with_answers.json)
---------------------------------------
{
  "question":       str,
  "options":        {"A": str, "B": str, "C": str, "D": str},
  "correct_answer": str | null,   # letter A/B/C/D
  "correct_index":  int | null,   # 0-based
  "domain":         str,          # top-level domain
  "subdomain":      str,          # slug
  "level":          str,
  "source_url":     str,
  "language":       str           # "ur" for all
}

Usage
-----
  python scrape/merge_native_ahmer.py
  python scrape/merge_native_ahmer.py --ahmer data/ahmer_mcqs.json \
      --native data/native_urdu_mcqs.json --output data/mcqs_with_answers.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AHMER  = BASE_DIR / "data" / "ahmer_mcqs.json"
DEFAULT_NATIVE = BASE_DIR / "data" / "native_urdu_mcqs.json"
DEFAULT_OUTPUT = BASE_DIR / "data" / "mcqs_with_answers.json"

LETTERS = ["A", "B", "C", "D"]


def normalize_ahmer(q: dict) -> dict:
    idx = q.get("correct_index")
    return {
        "question":       q["question"],
        "options":        q["options"],
        "correct_answer": LETTERS[idx] if idx is not None and 0 <= idx <= 3 else None,
        "correct_index":  idx,
        "domain":         q["domain"],
        "subdomain":      q["subdomain"],
        "level":          q.get("level", ""),
        "source_url":     q.get("source_url", ""),
        "language":       "ur",
    }


def normalize_native(q: dict) -> dict:
    return {
        "question":       q["question"],
        "options":        q["options"],
        "correct_answer": q.get("correct_answer"),
        "correct_index":  q.get("correct_index"),
        "domain":         q["std_domain"],
        "subdomain":      q["std_subdomain"],
        "level":          q.get("level", ""),
        "source_url":     q.get("url", ""),
        "language":       q.get("language", "ur"),
    }


def print_stats(merged: list[dict], ahmer_count: int, native_total: int, dupes: int) -> None:
    print(f"\n{'='*55}")
    print(f"  Merge summary")
    print(f"{'='*55}")
    print(f"  ahmer_mcqs       : {ahmer_count:>6,}")
    print(f"  native_urdu_mcqs : {native_total:>6,}")
    print(f"  duplicates       : {dupes:>6,}  (native entries dropped)")
    print(f"  merged total     : {len(merged):>6,}")
    print(f"\n  Domain / Subdomain breakdown")
    print(f"  {'-'*50}")
    counts = Counter((q["domain"], q["subdomain"]) for q in merged)
    domain_totals: Counter = Counter()
    for (dom, sub), cnt in sorted(counts.items()):
        print(f"  {dom:<30}  {sub:<30}  {cnt:>5,}")
        domain_totals[dom] += cnt
    print(f"  {'-'*50}")
    for dom, cnt in sorted(domain_totals.items()):
        print(f"  {dom:<30}  {'(total)':<30}  {cnt:>5,}")
    print(f"{'='*55}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ahmer",  default=str(DEFAULT_AHMER),  help="Path to ahmer_mcqs.json")
    p.add_argument("--native", default=str(DEFAULT_NATIVE), help="Path to native_urdu_mcqs.json")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    ahmer_raw  = json.loads(Path(args.ahmer).read_text(encoding="utf-8"))
    native_raw = json.loads(Path(args.native).read_text(encoding="utf-8"))

    normalized_ahmer  = [normalize_ahmer(q)  for q in ahmer_raw]
    normalized_native = [normalize_native(q) for q in native_raw]

    seen = {q["question"] for q in normalized_ahmer}
    deduped_native = [q for q in normalized_native if q["question"] not in seen]
    dupes = len(normalized_native) - len(deduped_native)

    merged = normalized_ahmer + deduped_native

    print_stats(merged, len(normalized_ahmer), len(normalized_native), dupes)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
