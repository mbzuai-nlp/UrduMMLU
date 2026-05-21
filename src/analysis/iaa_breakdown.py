#!/usr/bin/env python3
"""Inter-annotator agreement breakdown.

Operates on data/20-annotated-combined/mcqs.json. Reports:

  * Overall agreement (both picked A-D, same key).
  * Per-annotator disagreement rate vs partners.
  * Per-pair agreement counts.
  * Distribution of dropped vs included MCQs under Stage-21 rules.

Usage:
    python src/analysis/iaa_breakdown.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = REPO_ROOT / "data" / "20-annotated-combined" / "mcqs.json"


def main() -> None:
    combined = json.load(open(SRC_FILE, encoding="utf-8"))

    pair_stats: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    per_ann: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    drops = Counter()
    valid_dual = 0
    total_agree = 0

    for rec in combined:
        am = rec.get("annotator_metadata") or {}
        if len(am) < 2:
            drops["single_annotated"] += 1
            continue
        if any(a.get("flagged") for a in am.values()):
            drops["flagged"] += 1
            continue
        keys = [a.get("selected_key") for a in am.values()]
        if any(k == "unsure" for k in keys):
            drops["unsure"] += 1
            continue
        if not all(k in ("A", "B", "C", "D") for k in keys):
            drops["invalid"] += 1
            continue

        valid_dual += 1
        names = sorted(am.keys())
        pair_key = (names[0], names[1])
        pair_stats[pair_key][1] += 1
        per_ann[names[0]][1] += 1
        per_ann[names[1]][1] += 1
        if keys[0] == keys[1]:
            total_agree += 1
            pair_stats[pair_key][0] += 1
            per_ann[names[0]][0] += 1
            per_ann[names[1]][0] += 1
        else:
            drops["disagree"] += 1

    print(f"Combined records: {len(combined)}")
    print(f"Valid dual (both A/B/C/D, not flagged, not unsure): {valid_dual}")
    print(f"  agreed: {total_agree} ({total_agree/valid_dual*100:.1f}%)")
    print(f"  disagreed: {valid_dual - total_agree}")

    print(f"\nDrop breakdown (would-be excluded by Stage 21):")
    for k, v in drops.most_common():
        print(f"  {k:<20} {v}")

    print(f"\nPer-annotator disagreement rate with partners:")
    items = sorted(
        per_ann.items(),
        key=lambda x: -(1 - x[1][0] / x[1][1] if x[1][1] else 0),
    )
    for name, (a, t) in items:
        disagree_rate = (t - a) / t * 100 if t else 0
        print(f"  {name:<10} {disagree_rate:>5.1f}% disagree  ({t - a}/{t})")

    print(f"\nPer-pair agreement (showing pairs with ≥10 shared MCQs):")
    for (a, b), (ag, tot) in sorted(pair_stats.items(), key=lambda x: -x[1][1]):
        if tot < 10:
            continue
        print(f"  {a:<10} + {b:<10}  {ag/tot*100:>5.1f}%  ({ag}/{tot})")


if __name__ == "__main__":
    main()
