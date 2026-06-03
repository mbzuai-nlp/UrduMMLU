#!/usr/bin/env python3
"""Sunburst chart of the final dataset by domain + subdomain.

Two concentric rings: inner = the 5 domains, outer = the 26 subdomains.
Arc length is proportional to MCQ count. Palette is the warm→cool
orange-to-green gradient used in the pipeline diagram.

Usage:
    python src/analysis/domain_sunburst.py [--src path/mcqs.json] [--out path.png]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = REPO_ROOT / "data" / "25-final" / "mcqs.json"
DEFAULT_OUT = REPO_ROOT / "data" / "25-final" / "domains_sunburst.png"

# Warm → cool palette pulled from the pipeline-diagram swatches.
# Ordered largest-domain → smallest-domain (Humanities → Profession).
# Palette sampled directly from the pipeline-diagram swatches.
# Ordered so the largest domains take the green end of the gradient
# and orange becomes a small warm accent — keeps the chart green-dominant.
DOMAIN_COLORS = {
    "Humanities":      "#3C7C2A",  # dark green
    "Social Sciences": "#75A93D",  # medium green
    "STEM":            "#B5C941",  # yellow-green
    "Other":           "#D6A640",  # mustard
    "Profession":      "#DF7A45",  # orange (warm accent)
}

# Pretty-printed subdomain labels (with abbreviations for the long ones).
SUBDOMAIN_LABELS = {
    "urdu literature":                  "Urdu Literature",
    "urdu language":                    "Urdu Language",
    "urdu grammar":                     "Urdu Grammar",
    "islamic studies":                  "Islamic Studies",
    "ethics":                           "Ethics",
    "fine arts":                        "Fine Arts",
    "pakistan studies":                 "Pakistan Studies",
    "economics":                        "Economics",
    "education":                        "Education",
    "sociology":                        "Sociology",
    "health and physical education":    "Health & PE",
    "civics":                           "Civics",
    "geography":                        "Geography",
    "psychology":                       "Psychology",
    "current and international affairs":"Current & Intl. Affairs",
    "commerce":                         "Commerce",
    "psychometrics":                    "Psychometrics",
    "chemistry":                        "Chemistry",
    "biology":                          "Biology",
    "general science":                  "General Science",
    "mathematics":                      "Mathematics",
    "computer science":                 "Computer Science",
    "physics":                          "Physics",
    "general knowledge":                "General Knowledge",
    "professional development":         "Prof. Development",
    "professional studies":             "Prof. Studies",
}


def pretty_subdomain(name: str) -> str:
    clean = name.split(" / ", 1)[-1].strip().lower()
    return SUBDOMAIN_LABELS.get(clean, clean.title())


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def shade(hex_color: str, factor: float) -> tuple[float, float, float]:
    """Lighten an RGB color by mixing with white. factor 0=original, 1=white."""
    r, g, b = hex_to_rgb(hex_color)
    return (r + (1 - r) * factor, g + (1 - g) * factor, b + (1 - b) * factor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC_FILE,
                        help="Path to mcqs.json (default: stage 25)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output PNG (default: <src dir>/domains_sunburst.png)")
    args = parser.parse_args()

    out_path = args.out or args.src.parent / "domains_sunburst.png"
    records = json.load(open(args.src, encoding="utf-8"))

    # domain → subdomain → count
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        d = r.get("domain") or "Unknown"
        s = r.get("subdomain") or "—"
        counts[d][s] += 1

    # Sort domains by total size (largest first), subdomains within each by size
    domains = sorted(counts.keys(), key=lambda d: -sum(counts[d].values()))
    total = sum(sum(counts[d].values()) for d in domains)

    domain_sizes: list[int] = []
    domain_colors: list[tuple[float, float, float]] = []

    sub_sizes: list[int] = []
    sub_colors: list[tuple[float, float, float]] = []
    sub_labels: list[str] = []
    sub_counts: list[int] = []

    for d_name in domains:
        d_size = sum(counts[d_name].values())
        d_color_hex = DOMAIN_COLORS.get(d_name, "#888888")
        domain_sizes.append(d_size)
        domain_colors.append(hex_to_rgb(d_color_hex))

        subs = sorted(counts[d_name].items(), key=lambda kv: -kv[1])
        n = max(len(subs) - 1, 1)
        for idx, (sub_name, sub_count) in enumerate(subs):
            tint = 0.15 + (idx / n) * 0.55
            sub_sizes.append(sub_count)
            sub_colors.append(shade(d_color_hex, tint))
            sub_labels.append(sub_name)
            sub_counts.append(sub_count)

    # ----- plot -----
    sns.set_theme(style="white", context="paper")
    fig, ax = plt.subplots(figsize=(12, 12), subplot_kw=dict(aspect="equal"))

    ring_width = 0.32

    # Outer ring — subdomains
    outer_wedges, _ = ax.pie(
        sub_sizes,
        radius=1.0,
        colors=sub_colors,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=ring_width, edgecolor="white", linewidth=1.5),
    )

    # Inner ring — domains
    inner_wedges, _ = ax.pie(
        domain_sizes,
        radius=1.0 - ring_width,
        colors=domain_colors,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=ring_width, edgecolor="white", linewidth=1.5),
    )

    import math

    inner_r_outer_ring = 1.0 - ring_width  # inner radius of outer ring
    outer_r_outer_ring = 1.0               # outer radius of outer ring
    inner_r_inner_ring = 1.0 - 2 * ring_width

    # Domain labels — centered inside each inner-ring wedge
    for w, d_name in zip(inner_wedges, domains):
        ang = (w.theta1 + w.theta2) / 2.0
        rad = (inner_r_inner_ring + inner_r_outer_ring) / 2.0
        x = rad * math.cos(math.radians(ang))
        y = rad * math.sin(math.radians(ang))
        rot = ang - 180 if 90 < ang < 270 else ang
        ax.text(x, y, d_name,
                ha="center", va="center",
                rotation=rot,
                fontsize=11, fontweight="bold", color="white")

    # Subdomain labels — centered inside each outer-ring wedge, radial orientation
    for w, name in zip(outer_wedges, sub_labels):
        arc_deg = w.theta2 - w.theta1
        if arc_deg < 2.8:  # too thin to fit any readable text
            continue
        ang = (w.theta1 + w.theta2) / 2.0
        rad = (inner_r_outer_ring + outer_r_outer_ring) / 2.0
        x = rad * math.cos(math.radians(ang))
        y = rad * math.sin(math.radians(ang))
        rot = ang - 180 if 90 < ang < 270 else ang
        fontsize = min(10, max(6.5, arc_deg * 0.55))
        ax.text(x, y, pretty_subdomain(name),
                ha="center", va="center",
                rotation=rot,
                fontsize=fontsize, color="#1a1a1a")

    ax.set_title(f"UrduMMLU — Final Dataset by Domain & Subdomain",
                 fontsize=15, pad=20)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    try:
        rel = out_path.resolve().relative_to(REPO_ROOT)
        print(f"Wrote {rel}")
    except ValueError:
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
