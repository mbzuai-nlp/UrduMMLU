#!/usr/bin/env python3
"""Stage 24 — sweep Jaccard thresholds and produce a deduplicated dataset.

Reads  data/23-anonymize/mcqs.json
Writes data/24-deduplicated/mcqs.json           (deduped at ``--threshold``)
       data/24-deduplicated/stats.json          (per-threshold survivor count)
       data/24-deduplicated/jaccard_sweep.png   (plot)

Algorithm:
  * Tokenise each question on the normalised text (same logic as
    Stage 13 correlation_deduplication).
  * Build an inverted index of token → row-ids, skip stop-tokens
    (tokens appearing in too many rows).
  * For each row, look up candidates via shared tokens, then compute
    Jaccard for those candidates only.
  * Collect all candidate pairs with Jaccard ≥ MIN_THRESHOLD (0.5) once.
  * For every threshold in the sweep, run union-find on pairs ≥ T to
    get a survivor count.

Merge policy (only for the chosen output threshold):
  * Group of rows with the same canonical question + matching
    ``correct_key`` → keep the row with the smallest ``id``.
  * Group with mismatching ``correct_key`` → drop the whole group
    (defensive — same policy as Stage 13).

Usage:
    python src/deduplicate/build.py [--threshold 0.85]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "23-anonymize" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "24-deduplicated"
DST_MCQS = DST_DIR / "mcqs.json"
DST_STATS = DST_DIR / "stats.json"
DST_PLOT = DST_DIR / "jaccard_sweep.png"

MIN_THRESHOLD = 0.5
SWEEP = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
MIN_TOKENS_FOR_FUZZY = 4
STOP_FREQ = 200

DIACRITICS = re.compile(r"[ً-ٰٟؐ-ؚـ]")
PUNCT = re.compile(r"[‏‎,،.۔?؟!:;\"'“”‘’()\[\]{}<>—–\-_/\\|]")


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = DIACRITICS.sub("", text)
    text = PUNCT.sub(" ", text)
    return " ".join(text.lower().split())


def tokenise(text: str) -> set[str]:
    return set(normalize_text(text).split())


# ───────────────────────── union-find ─────────────────────────

class UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def candidate_pairs(rows: list[dict]) -> list[tuple[int, int, float]]:
    """Return list of (i, j, jaccard) for all pairs with Jaccard ≥ MIN_THRESHOLD."""
    n = len(rows)
    tokens = [tokenise(r.get("question", "")) for r in rows]

    # Inverted index
    idx: dict[str, list[int]] = defaultdict(list)
    for i, ts in enumerate(tokens):
        if len(ts) < MIN_TOKENS_FOR_FUZZY:
            continue
        for t in ts:
            idx[t].append(i)

    stop = {t for t, lst in idx.items() if len(lst) > STOP_FREQ}
    print(f"  inverted index: {len(idx):,} tokens ({len(stop):,} stop-words skipped)")

    pairs: list[tuple[int, int, float]] = []
    seen: set[tuple[int, int]] = set()
    t0 = time.time()
    for i in range(n):
        if i and i % 2000 == 0:
            print(f"  scanned {i:,}/{n:,} rows in {time.time()-t0:.1f}s, {len(pairs):,} pairs")
        ts = tokens[i]
        if len(ts) < MIN_TOKENS_FOR_FUZZY:
            continue
        cand: set[int] = set()
        for t in ts:
            if t in stop:
                continue
            for j in idx[t]:
                if j > i:
                    cand.add(j)
        for j in cand:
            tj = tokens[j]
            inter = len(ts & tj)
            if inter == 0:
                continue
            union = len(ts) + len(tj) - inter
            jac = inter / union
            if jac >= MIN_THRESHOLD:
                pairs.append((i, j, jac))
    print(f"  done in {time.time()-t0:.1f}s — {len(pairs):,} candidate pairs ≥ {MIN_THRESHOLD}")
    return pairs


def survivor_count(n: int, pairs: list[tuple[int, int, float]], threshold: float) -> tuple[int, int]:
    """Return (surviving_rows, n_groups_merged)."""
    uf = UF(n)
    for i, j, jac in pairs:
        if jac >= threshold:
            uf.union(i, j)
    roots = {uf.find(i) for i in range(n)}
    return len(roots), n - len(roots)


def apply_dedup(rows: list[dict], pairs: list[tuple[int, int, float]], threshold: float) -> list[dict]:
    """Deduplicate at the chosen threshold using the merge-agree / drop-conflict policy."""
    n = len(rows)
    uf = UF(n)
    for i, j, jac in pairs:
        if jac >= threshold:
            uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    out: list[dict] = []
    dropped_conflict = 0
    merged_groups = 0
    for members in groups.values():
        if len(members) == 1:
            out.append(rows[members[0]])
            continue
        keys = {rows[m].get("correct_key") for m in members}
        if len(keys) > 1:
            dropped_conflict += 1
            continue
        merged_groups += 1
        # Pick representative: smallest id
        rep_idx = min(members, key=lambda m: rows[m]["id"])
        out.append(rows[rep_idx])
    print(f"  merged groups: {merged_groups}")
    print(f"  dropped conflict groups: {dropped_conflict}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="Jaccard threshold for the output dataset (default 0.85)")
    args = parser.parse_args()

    rows = json.load(open(SRC, encoding="utf-8"))
    print(f"Loaded {len(rows):,} rows from {SRC.relative_to(REPO_ROOT)}")
    pairs = candidate_pairs(rows)

    # Sweep stats
    sweep_data: list[dict] = []
    for t in SWEEP:
        kept, removed = survivor_count(len(rows), pairs, t)
        sweep_data.append({"threshold": t, "kept": kept, "removed": removed})
        print(f"  T={t:.2f}: kept={kept:,}, removed={removed:,}")

    # Apply chosen threshold
    print(f"\nApplying dedup at threshold = {args.threshold}")
    deduped = apply_dedup(rows, pairs, args.threshold)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(deduped):,} records)")

    stats = {
        "input_rows": len(rows),
        "min_threshold_scanned": MIN_THRESHOLD,
        "candidate_pairs": len(pairs),
        "applied_threshold": args.threshold,
        "applied_output_rows": len(deduped),
        "sweep": sweep_data,
    }
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # Plot
    xs = [d["threshold"] for d in sweep_data]
    ys = [d["kept"] for d in sweep_data]
    removed = [d["removed"] for d in sweep_data]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(xs, ys, marker="o", linewidth=2, color="#3CB371", label="rows kept")
    ax.fill_between(xs, ys, len(rows), alpha=0.15, color="#FF8C42", label="rows removed")
    ax.axvline(args.threshold, color="#777", linestyle="--", alpha=0.6)
    ax.text(args.threshold, len(rows) * 1.005, f"chosen: T={args.threshold}",
            ha="center", fontsize=10, color="#555")

    for x, y, r in zip(xs, ys, removed):
        ax.annotate(f"{y:,}\n(-{r:,})", (x, y),
                    textcoords="offset points", xytext=(0, -22),
                    ha="center", fontsize=8, color="#333")

    ax.set_xlabel("Jaccard threshold (question text)")
    ax.set_ylabel("Rows surviving")
    ax.set_title(f"Stage 24 — Dedup sweep ({len(rows):,} input rows)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#eaeaea", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False)
    plt.tight_layout()
    plt.savefig(DST_PLOT, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Wrote {DST_PLOT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
