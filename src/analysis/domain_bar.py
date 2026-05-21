#!/usr/bin/env python3
"""Sorted horizontal bar of subdomain counts, colored by domain.

Cleaner than a treemap for paper figures — every subdomain has a clearly
visible count, the domain grouping is preserved via color, and the eye
can compare absolute sizes precisely.

Usage:
    python src/analysis/domain_bar.py [--out path.png]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = REPO_ROOT / "data" / "22-final-combined" / "mcqs.json"
DEFAULT_OUT = REPO_ROOT / "data" / "22-final-combined" / "domains_bar.png"

DOMAIN_COLORS = {
    "Humanities":      "#7B68EE",
    "Social Sciences": "#3CB371",
    "STEM":            "#FF8C42",
    "Other":           "#778899",
    "Profession":      "#D67BB0",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC_FILE,
                        help="Path to mcqs.json (default: stage 22)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output PNG (default: <src>/../domains_bar.png)")
    args = parser.parse_args()

    out_path = args.out or args.src.parent / "domains_bar.png"
    records = json.load(open(args.src, encoding="utf-8"))

    pairs: list[tuple[str, str, int]] = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in records:
        d = r.get("domain") or "Unknown"
        s = r.get("subdomain") or "—"
        counts[(d, s)] += 1
    pairs = [(d, s, c) for (d, s), c in counts.items()]
    pairs.sort(key=lambda x: -x[2])  # descending so largest is leftmost

    domain_totals: dict[str, int] = defaultdict(int)
    for d, _, c in pairs:
        domain_totals[d] += c
    total = sum(domain_totals.values())

    labels = [s for _, s, _ in pairs]
    values = [c for _, _, c in pairs]
    colors = [DOMAIN_COLORS.get(d, "#888") for d, _, _ in pairs]

    fig, ax = plt.subplots(figsize=(max(12, len(pairs) * 0.42), 7))
    ax.bar(range(len(pairs)), values, color=colors, edgecolor="white")
    ax.set_xticks(range(len(pairs)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=10)
    ax.set_ylabel("# of MCQs", fontsize=11)
    ax.set_title(
        f"Urdu MMLU — Subdomain Counts ({total:,} MCQs, {len(pairs)} subdomains)",
        fontsize=14, pad=12,
    )

    # Annotate counts above each bar
    ymax = max(values)
    for i, v in enumerate(values):
        ax.text(i, v + ymax * 0.01, f"{v:,}",
                ha="center", va="bottom", fontsize=8, rotation=0)

    # Style
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, ymax * 1.1)
    ax.grid(axis="y", color="#eaeaea", linestyle="-", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # Legend with domain totals + percentages
    legend = [
        Patch(facecolor=DOMAIN_COLORS.get(d, "#888"),
              label=f"{d} — {n:,} ({n/total*100:.1f}%)")
        for d, n in sorted(domain_totals.items(), key=lambda x: -x[1])
    ]
    ax.legend(handles=legend, loc="upper right", frameon=False,
              title="Domain", title_fontsize=11, fontsize=10)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    try:
        rel = out_path.resolve().relative_to(REPO_ROOT)
        print(f"Wrote {rel}")
    except ValueError:
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
