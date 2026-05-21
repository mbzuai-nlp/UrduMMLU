#!/usr/bin/env python3
"""Per-annotator-pair agreement heatmap.

Reads data/21-final-annotated/stats.json (built by src/final_annotated/build.py)
and renders a square NxN heatmap of Cohen's-κ-style agreement per pair.

Cells:
  - off-diagonal: simplified Cohen κ vs uniform-chance baseline over 4 keys
    (computed from agree/total in the stats file).
  - diagonal: blank (self-pair).
  - empty pairs (never shared a batch): also blank.

Usage:
    python src/analysis/iaa_heatmap.py [--out path.png] [--metric kappa|agreement]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
STATS_FILE = REPO_ROOT / "data" / "21-final-annotated" / "stats.json"
DEFAULT_OUT = REPO_ROOT / "data" / "21-final-annotated" / "iaa_heatmap.png"


def cohen_kappa(agree: int, total: int, n_categories: int = 4) -> float:
    if not total:
        return float("nan")
    p_o = agree / total
    p_e = 1.0 / n_categories
    return (p_o - p_e) / (1 - p_e)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--metric", choices=("kappa", "agreement"), default="kappa",
        help="kappa = simplified Cohen κ; agreement = raw agreement rate"
    )
    args = parser.parse_args()

    stats = json.load(open(STATS_FILE, encoding="utf-8"))
    per_pair = stats["agreement"]["per_pair"]

    # Collect all annotator names
    names: set[str] = set()
    for key in per_pair:
        a, b = key.split(" + ")
        names.add(a); names.add(b)
    annotators = sorted(names)
    n = len(annotators)
    idx = {name: i for i, name in enumerate(annotators)}

    mat = np.full((n, n), np.nan)
    counts = np.zeros((n, n), dtype=int)
    for key, v in per_pair.items():
        a, b = key.split(" + ")
        i, j = idx[a], idx[b]
        val = (
            cohen_kappa(v["agree"], v["total"])
            if args.metric == "kappa"
            else v["agree"] / v["total"] if v["total"] else float("nan")
        )
        mat[i][j] = mat[j][i] = val
        counts[i][j] = counts[j][i] = v["total"]

    # Plot
    fig, ax = plt.subplots(figsize=(max(8, n * 0.55), max(7, n * 0.5)))
    cmap = plt.get_cmap("RdYlGn")
    if args.metric == "kappa":
        vmin, vmax = 0.5, 1.0
        label = "Cohen's κ (simplified, vs 25% chance)"
    else:
        vmin, vmax = 0.7, 1.0
        label = "Agreement rate"

    im = ax.imshow(mat, cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")

    # Cell annotations
    for i in range(n):
        for j in range(n):
            if np.isnan(mat[i][j]):
                continue
            txt = f"{mat[i][j]:.2f}\n({counts[i][j]})"
            ax.text(
                j, i, txt, ha="center", va="center",
                color="black", fontsize=7,
            )

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(annotators, rotation=45, ha="right")
    ax.set_yticklabels(annotators)
    ax.set_title(f"Annotator-pair agreement (final-included MCQs, n={stats['total_included']})")

    cbar = fig.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label(label)

    plt.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"Wrote {args.out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
