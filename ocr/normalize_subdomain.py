#!/usr/bin/env python3
"""
Normalize subdomain field in a questions JSON
==============================================

For each question:
  1. Extract the level token from the subdomain value  (e.g. "SSC-I", "SSC-II")
  2. Write the normalized level into the `level` field
  3. Strip the level token (and any trailing parentheticals) from `subdomain`

Level normalization table
--------------------------
  Raw token            → level value
  SSC-I / SSC I        → SSC-I
  SSC-II / SSC II      → SSC-II
  SSC Part-I           → SSC-I
  SSC Part-II          → SSC-II
  SSA-II               → SSA-II
  HSSC-I               → HSSC-I
  Paper-I              → SSC-I
  Paper-II             → SSC-II
  ایس ایس سی I         → SSC-I
  ایس ایس سی II        → SSC-II
  ایس ایس سی (bare)    → SSC
  (nothing found)      → existing level value unchanged

Usage
-----
  python ocr/normalize_subdomain.py
  python ocr/normalize_subdomain.py --input data/ahmer_STEM.json
  python ocr/normalize_subdomain.py --input data/ahmer_STEM.json --output data/ahmer_STEM_clean.json
"""

import argparse
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT  = BASE_DIR / "data" / "ahmer_STEM.json"


# ── Regex: captures the level token anywhere in the string ───────────────────

_LEVEL_RE = re.compile(
    r'\s*'
    r'('
    r'SSC\s+Part[-\s]?(?:III|II|I)'   # SSC Part-II / SSC Part-I
    r'|SSC[-\s]?(?:III|II|I)'          # SSC-I / SSC-II / SSC II
    r'|SSA[-\s]?(?:III|II|I)'          # SSA-II
    r'|HSSC[-\s]?(?:III|II|I)'         # HSSC-I
    r'|Paper[-\s]?(?:III|II|I)'        # Paper-II  (BISE variant)
    r'|ایس ایس سی\s*(?:III|II|I)?'    # Urdu-script SSC with optional numeral
    r')'
    r'\s*(?:\([^)]*\))?',              # swallow trailing (10th Class) / (صنعت...) etc.
    re.IGNORECASE,
)

# Maps the captured raw token to a canonical level string
def _canonical_level(raw: str) -> str:
    t = raw.strip().upper()
    if re.match(r'SSC\s*[-]?\s*(PART[-\s]?)?(III|3)', t):  return "SSC-III"
    if re.match(r'SSC\s*[-]?\s*(PART[-\s]?)?II', t):       return "SSC-II"
    if re.match(r'SSC\s*[-]?\s*(PART[-\s]?)?I', t):        return "SSC-I"
    if re.match(r'SSA\s*[-]?\s*II', t):                    return "SSA-II"
    if re.match(r'SSA\s*[-]?\s*I', t):                     return "SSA-I"
    if re.match(r'HSSC\s*[-]?\s*II', t):                   return "HSSC-II"
    if re.match(r'HSSC\s*[-]?\s*I', t):                    return "HSSC-I"
    if re.match(r'PAPER\s*[-]?\s*II', t):                  return "SSC-II"
    if re.match(r'PAPER\s*[-]?\s*I', t):                   return "SSC-I"
    # Urdu script variants
    if 'ایس ایس سی' in raw:
        if re.search(r'II', raw):   return "SSC-II"
        if re.search(r'I', raw):    return "SSC-I"
        return "SSC"
    return raw.strip()


def normalize(q: dict) -> dict:
    sub = q.get("subdomain", "")
    m = _LEVEL_RE.search(sub)
    if m:
        level = _canonical_level(m.group(1))
        sub_clean = (_LEVEL_RE.sub("", sub)).strip()
        q["subdomain"] = sub_clean
        q["level"] = level
    return q


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input",  default=str(DEFAULT_INPUT),
                   help=f"Input JSON file (default: {DEFAULT_INPUT})")
    p.add_argument("--output", default=None,
                   help="Output path (default: overwrite input file)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    src  = Path(args.input)
    dest = Path(args.output) if args.output else src

    data = json.loads(src.read_text(encoding="utf-8"))

    from collections import Counter
    level_counts: Counter = Counter()
    for q in data:
        normalize(q)
        level_counts[q.get("level", "")] += 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Processed {len(data):,} questions → {dest}")
    print("\nLevel distribution:")
    for lvl, cnt in sorted(level_counts.items(), key=lambda x: -x[1]):
        label = lvl if lvl else "(empty)"
        print(f"  {cnt:>5,}  {label}")


if __name__ == "__main__":
    main()
