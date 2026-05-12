#!/usr/bin/env python3
"""
Merge pipeline outputs → data/ahmer_STEM.json
==============================================

Steps
-----
1. Load pipeline_output/BISE_Multan_25.json and pipeline_output/fbise.json
2. Concatenate both lists
3. Drop questions where has_image is True
4. Set subdomain = original domain value  (e.g. "Chemistry SSC-II")
5. Set domain    = "STEM"
6. Deduplicate by question text (BISE_Multan_25 entries take priority)
7. Save to data/ahmer_STEM.json

Usage
-----
  python ocr/clean_stem.py
  python ocr/clean_stem.py --output data/custom.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUTS = [
    BASE_DIR / "pipeline_output" / "BISE_Multan_25.json",
    BASE_DIR / "pipeline_output" / "fbise.json",
]
DEFAULT_OUTPUT = BASE_DIR / "data" / "ahmer_STEM.json"


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean(questions: list[dict]) -> list[dict]:
    """Filter has_image=True, reassign domain/subdomain."""
    cleaned = []
    for q in questions:
        if q.get("has_image"):
            continue
        q["subdomain"] = q.get("domain", "")
        q["domain"] = "STEM"
        cleaned.append(q)
    return cleaned


def deduplicate(questions: list[dict]) -> tuple[list[dict], int]:
    """Keep first occurrence of each question text."""
    seen: set[str] = set()
    result = []
    for q in questions:
        text = q["question"]
        if text not in seen:
            seen.add(text)
            result.append(q)
    dupes = len(questions) - len(result)
    return result, dupes


def print_stats(merged: list[dict], per_file: list[tuple[str, int, int]], dupes: int) -> None:
    print(f"\n{'='*60}")
    print("  Merge summary")
    print(f"{'='*60}")
    for name, total, kept in per_file:
        dropped = total - kept
        print(f"  {name:<35} {total:>5,} total  →  {kept:>5,} kept  ({dropped} has_image=True)")
    print(f"  {'Duplicates removed':<35} {dupes:>5,}")
    print(f"  {'Final total':<35} {len(merged):>5,}")
    print(f"\n  Subdomain breakdown (original domain values)")
    print(f"  {'-'*55}")
    for sub, cnt in sorted(Counter(q["subdomain"] for q in merged).items(), key=lambda x: -x[1]):
        print(f"  {cnt:>5,}  {sub}")
    print(f"{'='*60}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--inputs", nargs="+",
        default=[str(p) for p in DEFAULT_INPUTS],
        help="Input JSON files to merge (default: BISE_Multan_25.json fbise.json)",
    )
    p.add_argument(
        "--output", default=str(DEFAULT_OUTPUT),
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    all_cleaned: list[dict] = []
    per_file_stats: list[tuple[str, int, int]] = []

    for input_path in args.inputs:
        raw = load(Path(input_path))
        cleaned = clean(raw)
        per_file_stats.append((Path(input_path).name, len(raw), len(cleaned)))
        all_cleaned.extend(cleaned)

    merged, dupes = deduplicate(all_cleaned)

    print_stats(merged, per_file_stats, dupes)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
