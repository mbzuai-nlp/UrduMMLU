#!/usr/bin/env python3
"""Treemap of the combined dataset by domain + subdomain.

Nested rectangles: top-level by domain (5 boxes), each subdivided by
subdomain. Area is proportional to MCQ count. Useful for paper figure
showing the dataset's domain coverage at a glance.

Usage:
    python src/analysis/domain_treemap.py [--out path.png]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import squarify

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = REPO_ROOT / "data" / "22-final-combined" / "mcqs.json"
DEFAULT_OUT = REPO_ROOT / "data" / "22-final-combined" / "domains_treemap.png"

# Distinct hue per domain; subdomains use lighter tints of the domain hue.
DOMAIN_COLORS = {
    "Humanities":      "#7B68EE",  # medium slate blue
    "Social Sciences": "#3CB371",  # medium sea green
    "STEM":            "#FF8C42",  # orange
    "Other":           "#778899",  # light slate gray
    "Profession":      "#D67BB0",  # rose
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def shade(hex_color: str, factor: float) -> tuple[float, float, float]:
    """Lighten an RGB color by mixing with white. factor in [0,1] = how light."""
    r, g, b = hex_to_rgb(hex_color)
    return (r + (1 - r) * factor, g + (1 - g) * factor, b + (1 - b) * factor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC_FILE,
                        help="Path to mcqs.json (default: stage 22)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output PNG (default: <src>/../domains_treemap.png)")
    args = parser.parse_args()

    out_path = args.out or args.src.parent / "domains_treemap.png"
    records = json.load(open(args.src, encoding="utf-8"))

    # domain → subdomain → count
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        d = r.get("domain") or "Unknown"
        s = r.get("subdomain") or "—"
        counts[d][s] += 1

    domains = sorted(counts.keys(), key=lambda d: -sum(counts[d].values()))

    # Landscape canvas for paper figures: wider than tall.
    W, H = 200, 100
    fig, ax = plt.subplots(figsize=(18, 9))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")

    total = sum(sum(counts[d].values()) for d in domains)
    domain_sizes = [sum(counts[d].values()) for d in domains]

    # Outer treemap — one rect per domain
    outer_rects = squarify.normalize_sizes(domain_sizes, W, H)
    outer_rects = squarify.squarify(outer_rects, 0, 0, W, H)

    for d_name, outer, raw_size in zip(domains, outer_rects, domain_sizes):
        x, y, w, h = outer["x"], outer["y"], outer["dx"], outer["dy"]
        domain_color = DOMAIN_COLORS.get(d_name, "#888888")

        # Inner subdomains
        subdomains = sorted(counts[d_name].items(), key=lambda kv: -kv[1])
        sub_sizes = [c for _, c in subdomains]
        sub_rects_raw = squarify.normalize_sizes(sub_sizes, w, h)
        sub_rects = squarify.squarify(sub_rects_raw, x, y, w, h)

        for (sub_name, sub_count), inner, idx in zip(subdomains, sub_rects, range(len(subdomains))):
            # Tint each subdomain a slightly different shade for visual separation
            tint = 0.15 + (idx / max(len(subdomains) - 1, 1)) * 0.55
            color = shade(domain_color, tint)
            rx, ry, rw, rh = inner["x"], inner["y"], inner["dx"], inner["dy"]
            ax.add_patch(plt.Rectangle((rx, ry), rw, rh,
                                       facecolor=color,
                                       edgecolor="white", linewidth=1.2))
            # Label if box is big enough
            if rw * rh > 12:
                fontsize = min(11, max(6, (rw * rh) ** 0.35))
                ax.text(rx + rw / 2, ry + rh / 2,
                        f"{sub_name}\n{sub_count}",
                        ha="center", va="center",
                        fontsize=fontsize, color="black")

        # Outer border around the domain group
        ax.add_patch(plt.Rectangle((x, y), w, h,
                                   fill=False, edgecolor=domain_color, linewidth=3))
        # Domain label placed inside the top of the box; falls back to outside-top if tight
        pct = raw_size / total * 100
        label = f"{d_name} — {raw_size:,} ({pct:.1f}%)"
        # Inside if there's vertical room; otherwise above
        if h > 6:
            ax.text(x + w / 2, y + h - 1.2, label,
                    ha="center", va="top",
                    fontsize=12, fontweight="bold",
                    color=domain_color,
                    bbox=dict(facecolor="white", alpha=0.8,
                              edgecolor=domain_color, boxstyle="round,pad=0.3"))

    plt.title(f"Urdu MMLU — Final Combined Dataset ({total:,} MCQs)",
              fontsize=15, pad=30)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    try:
        rel = out_path.resolve().relative_to(REPO_ROOT)
        print(f"Wrote {rel}")
    except ValueError:
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
