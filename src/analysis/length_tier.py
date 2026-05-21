#!/usr/bin/env python3
"""Question-length distribution for the final dataset.

Computes a `short`/`long` tier (≤9 vs >9 words, matching the Stage-16
subsampling rule) for every record — including scraped ones whose
``length_tier`` field is null — then plots two views:

  * Stacked bar of short vs long per domain.
  * Histogram of question word counts overall.

Usage:
    python src/analysis/length_tier.py [--src data/25-final/mcqs.json]
                                       [--out-bar path] [--out-hist path]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "data" / "25-final" / "mcqs.json"
LENGTH_BOUNDARY = 9  # ≤ N words = short (matches src/subsampling/sample.py)

DOMAIN_COLORS = {
    "Humanities":      "#7B68EE",
    "Social Sciences": "#3CB371",
    "STEM":            "#FF8C42",
    "Other":           "#778899",
    "Profession":      "#D67BB0",
}


def word_count(text: str) -> int:
    return len((text or "").replace("‏", "").strip().split())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out-bar", type=Path, default=None)
    parser.add_argument("--out-hist", type=Path, default=None)
    args = parser.parse_args()

    out_bar = args.out_bar or args.src.parent / "length_tier_bar.png"
    out_hist = args.out_hist or args.src.parent / "length_tier_hist.png"

    rows = json.load(open(args.src, encoding="utf-8"))
    counts_by_domain: dict[str, dict[str, int]] = defaultdict(lambda: {"short": 0, "long": 0})
    all_word_counts: list[int] = []
    for r in rows:
        wc = word_count(r.get("question", ""))
        tier = "short" if wc <= LENGTH_BOUNDARY else "long"
        counts_by_domain[r.get("domain", "?")][tier] += 1
        all_word_counts.append(wc)

    domains = sorted(counts_by_domain.keys(),
                     key=lambda d: -(counts_by_domain[d]["short"] + counts_by_domain[d]["long"]))
    shorts = [counts_by_domain[d]["short"] for d in domains]
    longs = [counts_by_domain[d]["long"] for d in domains]
    totals = [s + l for s, l in zip(shorts, longs)]

    # ───── stacked bar ─────
    fig, ax = plt.subplots(figsize=(11, 6))
    x = range(len(domains))
    short_colors = [DOMAIN_COLORS.get(d, "#888") for d in domains]
    long_colors = [DOMAIN_COLORS.get(d, "#888") for d in domains]
    # Short = lighter shade
    def lighten(hex_c: str, f: float = 0.55) -> tuple[float, ...]:
        h = hex_c.lstrip("#")
        r, g, b = (int(h[i:i+2], 16)/255 for i in (0, 2, 4))
        return (r + (1-r)*f, g + (1-g)*f, b + (1-b)*f)

    ax.bar(x, shorts, color=[lighten(c) for c in short_colors], edgecolor="white", label="short (≤9 words)")
    ax.bar(x, longs, bottom=shorts, color=long_colors, edgecolor="white", label="long (>9 words)")

    for i, (s, l, t) in enumerate(zip(shorts, longs, totals)):
        ax.text(i, s / 2, f"{s:,}", ha="center", va="center", fontsize=9, color="#444")
        ax.text(i, s + l / 2, f"{l:,}", ha="center", va="center", fontsize=9, color="white")
        ax.text(i, t, f"{t:,}\n({s/t*100:.0f}% / {l/t*100:.0f}%)",
                ha="center", va="bottom", fontsize=9, color="#222")

    ax.set_xticks(list(x))
    ax.set_xticklabels(domains, rotation=20, ha="right", fontsize=10)
    ax.set_ylabel("# of MCQs")
    ax.set_title(f"Question length tier by domain — short / long split ({sum(totals):,} MCQs)",
                 fontsize=14, pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, max(totals) * 1.12)
    ax.grid(axis="y", color="#eaeaea", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", frameon=False)
    plt.tight_layout()
    plt.savefig(out_bar, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_bar}")

    # ───── histogram ─────
    fig, ax = plt.subplots(figsize=(11, 5))
    max_wc = min(max(all_word_counts), 50)
    bins = list(range(0, max_wc + 2))
    ax.hist(all_word_counts, bins=bins, color="#3CB371", edgecolor="white")
    ax.axvline(LENGTH_BOUNDARY + 0.5, color="#c0392b", linestyle="--", linewidth=1.5,
               label=f"tier boundary (≤{LENGTH_BOUNDARY} = short)")
    ax.set_xlabel("words in question")
    ax.set_ylabel("# of MCQs")
    ax.set_title(f"Question length distribution ({sum(totals):,} MCQs)",
                 fontsize=14, pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#eaeaea", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", frameon=False)
    plt.tight_layout()
    plt.savefig(out_hist, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_hist}")

    # Summary
    total = sum(totals)
    total_short = sum(shorts)
    total_long = sum(longs)
    print(f"\nOverall: {total_short:,} short ({total_short/total*100:.1f}%) / "
          f"{total_long:,} long ({total_long/total*100:.1f}%)")


if __name__ == "__main__":
    main()
