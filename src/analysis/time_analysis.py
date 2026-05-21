#!/usr/bin/env python3
"""Per-annotator active-time analysis.

Reports total time spent annotating, with a per-MCQ cap to filter out
"tab left open" outliers. Without the cap, totals are inflated by browser
idle time (Saad had a single MCQ logged at 13 hours, etc.).

Usage:
    python src/analysis/time_analysis.py [--cap-seconds 300]
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOT_DIR = REPO_ROOT / "data" / "19-annotated"


def load_annotations() -> list[dict]:
    rows: list[dict] = []
    for folder in sorted(ANNOT_DIR.iterdir()):
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            if f.suffix != ".json":
                continue
            with open(f, encoding="utf-8") as fh:
                rows.extend(json.load(fh).get("annotations", []))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cap-seconds",
        type=int,
        default=300,
        help="Cap per-MCQ time in seconds (default 300 = 5 min)",
    )
    args = parser.parse_args()

    by_ann: dict[str, list[dict]] = defaultdict(list)
    for a in load_annotations():
        by_ann[a["annotator"]].append(a)

    cap = args.cap_seconds
    print(
        f"{'annotator':<10} {'records':>7} {'raw_hr':>7} {'capped_hr':>9} "
        f"{'>cap':>4} {'med':>4} {'mean_c':>7}"
    )
    print("-" * 70)

    overall_raw = 0.0
    overall_cap = 0.0
    for name in sorted(by_ann.keys()):
        rows = by_ann[name]
        times = [
            (a.get("time_spent_ms", 0) or 0) / 1000
            for a in rows
            if a.get("time_spent_ms")
        ]
        raw_h = sum(times) / 3600
        capped = [min(t, cap) for t in times]
        cap_h = sum(capped) / 3600
        over = sum(1 for t in times if t > cap)
        med = statistics.median(capped) if capped else 0
        mean_c = statistics.mean(capped) if capped else 0
        overall_raw += raw_h
        overall_cap += cap_h
        print(
            f"{name:<10} {len(rows):>7} {raw_h:>6.1f}h {cap_h:>8.1f}h {over:>4} "
            f"{med:>3.0f}s {mean_c:>6.1f}s"
        )
    print("-" * 70)
    print(f"Totals — raw: {overall_raw:.1f}h    capped: {overall_cap:.1f}h")


if __name__ == "__main__":
    main()
