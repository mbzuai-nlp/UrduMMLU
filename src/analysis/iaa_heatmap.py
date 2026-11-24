#!/usr/bin/env python3
"""Per-annotator-pair agreement heatmap (Figure 13).

Reads data/21-final-annotated/stats.json (built by src/final_annotated/build.py)
and renders a square NxN heatmap of pairwise agreement.

POPULATION. Cells cover the ANSWER-ELIGIBLE items: the 17,565 annotated items
less those that were flagged, marked unsure, or left incomplete. Only these
carry two comparable answer selections, so only these can agree or disagree.
That is 16,070 items, and the per-pair counts sum to exactly that. An earlier
version of this figure was titled with ``total_included`` (14,459), which is the
*consensus-retained* subset -- by construction every item in it agrees, so it
cannot be the population a disagreement statistic is measured on.

STATISTIC. Each cell is (p_o - 0.25) / 0.75, a fixed-chance correction that
assumes a uniform 25% baseline over four options. This is NOT Cohen's kappa,
which would estimate the chance term from the two annotators' observed marginal
label frequencies. Reported and labelled as a fixed-chance coefficient.

Cells:
  - off-diagonal: the coefficient, with the number of shared items beneath.
  - dashed outline: fewer than MIN_RELIABLE shared items, so the estimate is
    noisy and should not be read as evidence about that pair.
  - diagonal and never-paired annotators: blank.

Usage:
    python src/analysis/iaa_heatmap.py                    # -> report/figures/
    python src/analysis/iaa_heatmap.py --metric agreement
    python src/analysis/iaa_heatmap.py --out somewhere.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
# Embed TrueType rather than Type 3 -- ACLPUB requires embedded fonts.
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
STATS_FILE = REPO_ROOT / "data" / "21-final-annotated" / "stats.json"
ANON_MAP = REPO_ROOT / "data" / "23-anonymize" / "mapping.json"
DEFAULT_OUT = REPO_ROOT / "report" / "figures" / "iaa_heatmap.pdf"

CHANCE = 0.25          # uniform baseline over four answer options
MIN_RELIABLE = 50      # below this many shared items, flag the cell as noisy


def fixed_chance(agree: int, total: int, chance: float = CHANCE) -> float:
    """(p_o - p_e) / (1 - p_e) with p_e held fixed at the uniform baseline."""
    if not total:
        return float("nan")
    return (agree / total - chance) / (1 - chance)


def anon_labels() -> dict[str, str]:
    """Real annotator name -> ANN<N>, reusing the released stage-23 mapping.

    Annotators are private individuals and the cells report a per-person
    quality measure, so the figure must never carry real names. The mapping in
    data/23-anonymize/mapping.json is alphabetical and stable (ann_0, ann_1,
    ...); we render it 1-indexed and uppercase for display. NOTE that
    data/21-final-annotated/stats.json, which this figure reads, still holds
    the real names -- the anonymisation happens here at render time.
    """
    raw = json.loads(ANON_MAP.read_text(encoding="utf-8"))
    return {name: f"ANN{int(tok.rsplit('_', 1)[1]) + 1}" for name, tok in raw.items()}


def eligible_population(stats: dict) -> int:
    """Items carrying two comparable answer selections."""
    d = stats["drop_breakdown"]
    return (stats["total_input"] - d["flagged"] - d["unsure"]
            - d["single_annotated"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--metric", choices=("kappa", "agreement"), default="kappa",
                    help="kappa = fixed-chance coefficient; agreement = raw rate")
    args = ap.parse_args()

    stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    per_pair = stats["agreement"]["per_pair"]

    pair_total = sum(v["total"] for v in per_pair.values())
    eligible = eligible_population(stats)
    if pair_total != eligible:
        raise SystemExit(
            f"pairwise cells sum to {pair_total:,} but the answer-eligible "
            f"population is {eligible:,} -- the figure would mislabel its own "
            f"population, refusing to render."
        )

    anon = anon_labels()
    real_names = {n for key in per_pair for n in key.split(" + ")}
    unmapped = sorted(real_names - set(anon))
    if unmapped:
        raise SystemExit(
            f"{len(unmapped)} annotator(s) missing from {ANON_MAP.name}, which "
            f"would leak a real name into the figure. Re-run "
            f"src/anonymize/build.py first."
        )
    # Order by the numeric suffix so labels read ANN1, ANN2, ... ANN17.
    annotators = sorted(real_names, key=lambda x: int(anon[x][3:]))
    labels = [anon[x] for x in annotators]
    n = len(annotators)
    idx = {name: i for i, name in enumerate(annotators)}

    mat = np.full((n, n), np.nan)
    counts = np.zeros((n, n), dtype=int)
    for key, v in per_pair.items():
        a, b = key.split(" + ")
        i, j = idx[a], idx[b]
        val = (fixed_chance(v["agree"], v["total"]) if args.metric == "kappa"
               else (v["agree"] / v["total"] if v["total"] else float("nan")))
        mat[i][j] = mat[j][i] = val
        counts[i][j] = counts[j][i] = v["total"]

    fig, ax = plt.subplots(figsize=(max(9, n * 0.62), max(7.5, n * 0.55)))
    if args.metric == "kappa":
        vmin, vmax = 0.5, 1.0
        label = "Fixed-chance agreement  $(p_o - 0.25)\\,/\\,0.75$"
    else:
        vmin, vmax = 0.7, 1.0
        label = "Observed agreement rate  $p_o$"

    im = ax.imshow(mat, cmap=plt.get_cmap("RdYlGn"), vmin=vmin, vmax=vmax,
                   aspect="equal")

    noisy = 0
    for i in range(n):
        for j in range(n):
            if np.isnan(mat[i][j]):
                continue
            ax.text(j, i, f"{mat[i][j]:.2f}\n({counts[i][j]:,})",
                    ha="center", va="center", color="black", fontsize=6.5,
                    linespacing=1.15)
            if counts[i][j] < MIN_RELIABLE:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                       edgecolor="black", linewidth=0.9,
                                       linestyle=(0, (2, 1.5))))
                noisy += 1

    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.6)
    ax.tick_params(which="minor", length=0)
    ax.set_title(
        f"Annotator-pair agreement over the {eligible:,} answer-eligible items\n"
        f"(dashed outline: fewer than {MIN_RELIABLE} shared items)",
        fontsize=10, pad=10,
    )

    cbar = fig.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label(label, fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    plt.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.out, bbox_inches="tight", dpi=200)
    try:
        shown = args.out.resolve().relative_to(REPO_ROOT)
    except ValueError:            # --out pointing outside the repo
        shown = args.out
    print(f"Wrote {shown}")
    print(f"  population   {eligible:,} answer-eligible items "
          f"(cells sum to {pair_total:,})")
    print(f"  pairs        {len(per_pair)}  ({noisy // 2} below "
          f"{MIN_RELIABLE} shared items)")
    print(f"  labels       {labels[0]}..{labels[-1]} (anonymised; no real names rendered)")
    print(f"  overall      p_o = {sum(v['agree'] for v in per_pair.values()) / pair_total:.4f}, "
          f"coefficient = {fixed_chance(sum(v['agree'] for v in per_pair.values()), pair_total):.4f}")


if __name__ == "__main__":
    main()
