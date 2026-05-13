#!/usr/bin/env python3
"""Stage 14 — subsampling.

Produces an annotation-ready subset of the unanswered MCQs:

  - Caps each subdomain at ``SUBDOMAIN_CAP`` rows.
  - Within a subdomain, stratifies sampling on (``source`` × ``length_tier``)
    so every source and every length bucket is represented proportionally.
  - Pre-excludes rows that trigger ``≥ 2`` quality flags
    (``catch_all`` + ``short_question``). These go to the appendix file
    rather than being annotated.

Outputs two files (every input row lands in exactly one):

  - ``data/14-subsampling/mcqs_to_annotate.json`` — the sampled subset
  - ``data/14-subsampling/mcqs_appendix.json``  — everything else

Each output row carries two new fields:

  - ``quality_flags`` — list (possibly empty) of triggered flags
  - ``length_tier``   — ``"short"`` (≤9 words) or ``"long"`` (>9 words)

Reads from ``data/13-correlation-deduplicated/mcqs_without_answers.json``.
"""

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "14-english-filtered" / "mcqs_without_answers.json"
DST_DIR = REPO_ROOT / "data" / "15-subsampling"
DST_ANNOTATE = DST_DIR / "mcqs_to_annotate.json"
DST_APPENDIX = DST_DIR / "mcqs_appendix.json"

SEED = 42
SUBDOMAIN_CAP = 1200
LENGTH_TIER_BOUNDARY = 9  # ≤ N words = short, > N = long
SHORT_QUESTION_MIN = 4    # < this many tokens triggers short_question flag

CATCH_ALL_PATTERNS = (
    "ان میں سے کوئی نہیں",
    "مذکورہ بالا میں سے کوئی نہیں",
    "مذکورہ میں سے کوئی نہیں",
    "تمام کے تمام",
    "ان میں سے کوئی بھی نہیں",
    "none of the above",
    "all of the above",
)


def quality_flags(item) -> list:
    flags = []
    q = (item.get("question") or "").replace("‏", "").strip()
    if len(q.split()) < SHORT_QUESTION_MIN:
        flags.append("short_question")

    opts = item.get("options") or {}
    if isinstance(opts, dict):
        for v in opts.values():
            if not isinstance(v, str):
                continue
            v_norm = v.replace("‏", "").strip()
            v_low = v_norm.lower()
            if any(pat in v_norm or pat in v_low for pat in CATCH_ALL_PATTERNS):
                flags.append("catch_all")
                break
    return flags


def length_tier(item) -> str:
    q = (item.get("question") or "").replace("‏", "").strip()
    return "short" if len(q.split()) <= LENGTH_TIER_BOUNDARY else "long"


def source_key(item):
    src = item.get("source")
    if isinstance(src, list):
        return tuple(sorted(src)) if src else ("unknown",)
    if isinstance(src, str) and src:
        return (src,)
    return ("unknown",)


def proportional_allocate(cell_sizes: dict, cap: int) -> dict:
    """Allocate `cap` items across cells proportional to cell size.

    Capped per cell (a cell can't be allocated more than it contains).
    Adjusts rounding so the totals sum to exactly `cap` (or the total
    available, whichever is smaller).
    """
    total = sum(cell_sizes.values())
    if total <= cap:
        return dict(cell_sizes)

    # Initial proportional allocation
    alloc = {}
    for k, n in cell_sizes.items():
        alloc[k] = min(n, max(0, round(n * cap / total)))

    # Walk the difference. If we're under, redistribute to cells with capacity
    # (largest first). If we're over, trim from cells with the highest
    # allocation first.
    def diff():
        return cap - sum(alloc.values())

    while diff() != 0:
        d = diff()
        candidates = sorted(
            cell_sizes.items(),
            key=lambda x: (alloc[x[0]] - x[1] * cap / total),  # most over-allocated first
        )
        if d > 0:
            # need more; find a cell with spare capacity (alloc < cell_size)
            for k, n in sorted(cell_sizes.items(), key=lambda x: -x[1]):
                if alloc[k] < n:
                    alloc[k] += 1
                    break
            else:
                break
        else:
            # need less; trim the most-over-allocated cell
            for k, _ in candidates[::-1]:
                if alloc[k] > 0:
                    alloc[k] -= 1
                    break
            else:
                break

    return alloc


def sample_subdomain(items, cap, rng):
    """Stratified sample of one subdomain's items into ``cap`` rows."""
    if len(items) <= cap:
        return list(items), []

    # Group by (source, length_tier)
    cells = defaultdict(list)
    for item in items:
        cell = (source_key(item), item["length_tier"])
        cells[cell].append(item)

    cell_sizes = {k: len(v) for k, v in cells.items()}
    quotas = proportional_allocate(cell_sizes, cap)

    sampled, rest = [], []
    for cell, members in cells.items():
        rng.shuffle(members)
        q = quotas[cell]
        sampled.extend(members[:q])
        rest.extend(members[q:])

    return sampled, rest


def main() -> None:
    print(f"Source:  {SRC}")
    print(f"Output:  {DST_DIR}\n")

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} rows from stage 13\n")

    # Annotate each row with quality_flags and length_tier
    for item in data:
        item["quality_flags"] = quality_flags(item)
        item["length_tier"] = length_tier(item)

    # Eligibility: keep if < 2 flags; otherwise straight to appendix
    eligible = [it for it in data if len(it["quality_flags"]) < 2]
    ineligible = [it for it in data if len(it["quality_flags"]) >= 2]

    # Per-subdomain stratified sampling
    by_subdomain = defaultdict(list)
    for it in eligible:
        by_subdomain[it.get("subdomain", "?")].append(it)

    rng = random.Random(SEED)
    annotate, appendix_overcap = [], []
    per_sub_stats = []

    for sub in sorted(by_subdomain.keys()):
        items = by_subdomain[sub]
        kept, rest = sample_subdomain(items, SUBDOMAIN_CAP, rng)
        annotate.extend(kept)
        appendix_overcap.extend(rest)
        per_sub_stats.append((sub, len(items), len(kept), len(rest)))

    appendix = appendix_overcap + ineligible

    # Reporting
    print(f"=== Quality flag distribution (input) ===")
    flag_counts = Counter()
    multi_flag = 0
    for it in data:
        for f in it["quality_flags"]:
            flag_counts[f] += 1
        if len(it["quality_flags"]) >= 2:
            multi_flag += 1
    for flag, n in flag_counts.most_common():
        print(f"  {flag:<18} {n:>5}  ({100*n/len(data):.1f}%)")
    print(f"  rows with ≥ 2 flags (→ appendix): {multi_flag}")

    print(f"\n=== Per-subdomain sampling ===")
    print(f"{'subdomain':<32} {'eligible':>8} {'sampled':>8} {'overcap':>8}")
    print("-" * 60)
    for sub, n_in, n_kept, n_rest in per_sub_stats:
        action = "" if n_in <= SUBDOMAIN_CAP else f"cap={SUBDOMAIN_CAP}"
        print(f"  {sub:<30} {n_in:>8} {n_kept:>8} {n_rest:>8}  {action}")

    print(f"\n=== Totals ===")
    print(f"  input rows:           {len(data)}")
    print(f"  eligible:             {len(eligible)}")
    print(f"  ineligible (2+ flags):{len(ineligible)}")
    print(f"  → mcqs_to_annotate:   {len(annotate)}")
    print(f"  → mcqs_appendix:      {len(appendix)}")
    print(f"     (over-cap:         {len(appendix_overcap)})")
    print(f"     (ineligible:       {len(ineligible)})")
    print(f"  sum check:            {len(annotate) + len(appendix)} (= {len(data)})")

    # Length-tier balance in the sampled set
    tier_counts = Counter(it["length_tier"] for it in annotate)
    print(f"\n=== Length-tier balance in annotation set ===")
    for tier, n in tier_counts.most_common():
        print(f"  {tier:<10} {n:>5}  ({100*n/len(annotate):.1f}%)")

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_ANNOTATE, "w", encoding="utf-8") as f:
        json.dump(annotate, f, ensure_ascii=False, indent=4)
    with open(DST_APPENDIX, "w", encoding="utf-8") as f:
        json.dump(appendix, f, ensure_ascii=False, indent=4)

    print(f"\nWrote:")
    print(f"  {DST_ANNOTATE}")
    print(f"  {DST_APPENDIX}")


if __name__ == "__main__":
    main()
