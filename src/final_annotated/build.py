#!/usr/bin/env python3
"""Stage 21 — final-annotated benchmark dataset.

Reads:
  - data/20-annotated-combined/mcqs.json    (Stage-20 combined records)

Writes:
  - data/21-final-annotated/mcqs.json       (filtered + edited MCQs)
  - data/21-final-annotated/stats.json      (drop breakdown, distributions, IAA)

Inclusion rules (mirrored in data/21-final-annotated/rules.md):

  * Dual annotation required.
  * Neither annotator flagged.
  * Neither annotator picked the "unsure" UI button.
  * Both picked a real A/B/C/D option.
  * Both picked the SAME option (consensus).

For included MCQs:
  * The agreed key becomes ``correct_key``.
  * Edits to question / options / subdomain are applied:
      - field edited by only one annotator → use that edit
      - field edited by both, same value → use the agreed edit
      - field edited by both, different values → use the LONGER edit
  * The ``domain`` follows the (possibly edited) ``subdomain``: we build a
    canonical ``subdomain → domain`` map from the input data (majority vote
    across all combined records) and look up the post-edit subdomain. This
    means annotators only need to edit ``subdomain`` to relocate an MCQ —
    the domain auto-corrects.
  * Bidi marks (U+200E/F, U+202A-E, U+2066-9) stripped from question and options.
  * Stage-16 IDs preserved (no renumbering).

Usage:
    python src/final_annotated/build.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = REPO_ROOT / "data" / "20-annotated-combined" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "21-final-annotated"
DST_MCQS = DST_DIR / "mcqs.json"
DST_STATS = DST_DIR / "stats.json"

BIDI_CHARS = "‎‏‪‫‬‭‮⁦⁧⁨⁩"
STRIP_BIDI = str.maketrans("", "", BIDI_CHARS)


def clean(s):
    return s.translate(STRIP_BIDI) if isinstance(s, str) else s


def merge_field_edits(values: list[str], original: str) -> str:
    """Apply the edit rule for a single field: longer of multiple edits, else
    the single edit, else original."""
    if not values:
        return original
    if len(set(values)) == 1:
        return values[0]
    return max(values, key=len)


def apply_edits(src: dict, annotator_metadata: dict) -> tuple[str, dict, str]:
    """Resolve question / options / subdomain across annotators' edits."""
    edits_per_annotator = [
        am.get("edits", {}) or {} for am in annotator_metadata.values()
    ]

    q_edits = [e["question"] for e in edits_per_annotator if e.get("question")]
    question = merge_field_edits(q_edits, src["question"])

    options = dict(src["options"])
    for key in list(options.keys()):
        opt_edits = [
            e.get("options", {}).get(key)
            for e in edits_per_annotator
            if e.get("options", {}).get(key)
        ]
        options[key] = merge_field_edits(opt_edits, options[key])

    sub_edits = [e["subdomain"] for e in edits_per_annotator if e.get("subdomain")]
    subdomain = merge_field_edits(sub_edits, src.get("subdomain"))

    return question, options, subdomain


def classify(record: dict) -> str | None:
    """Return the inclusion verdict for one combined record.
    None = include, otherwise drop reason string."""
    am = record.get("annotator_metadata") or {}
    if len(am) < 2:
        return "single_annotated"
    if any(a.get("flagged") for a in am.values()):
        return "flagged"
    keys = [a.get("selected_key") for a in am.values()]
    if any(k == "unsure" for k in keys):
        return "unsure"
    if not all(k in ("A", "B", "C", "D") for k in keys):
        return "invalid"
    if len(set(keys)) > 1:
        return "disagree"
    return None  # include


def build_canonical_domain_map(records: list[dict]) -> dict[str, str]:
    """Majority-vote map: subdomain → most-common domain across the inputs.

    Uses the original (pre-edit) subdomain/domain pairings in each record,
    which reflect the scraped/curated tagging. Subdomain edits made by
    annotators are then resolved against this map at write time.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    for rec in records:
        sub = rec.get("subdomain")
        dom = rec.get("domain")
        if sub and dom:
            counts[sub][dom] += 1
    return {sub: c.most_common(1)[0][0] for sub, c in counts.items()}


def cohen_kappa(agree: int, total: int, n_categories: int = 4) -> float:
    """Simplified κ vs a uniform-chance baseline over the 4 option keys."""
    if not total:
        return 0.0
    p_o = agree / total
    p_e = 1.0 / n_categories
    return (p_o - p_e) / (1 - p_e)


def main() -> None:
    with open(SRC_FILE, encoding="utf-8") as f:
        combined = json.load(f)

    canonical_domain = build_canonical_domain_map(combined)

    drops: Counter = Counter()
    pair_agree: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    final: list[dict] = []
    domain_corrections = 0

    for rec in combined:
        verdict = classify(rec)
        am = rec.get("annotator_metadata") or {}
        if verdict == "disagree":
            a, b = sorted(am.keys())
            pair_agree[(a, b)][1] += 1
            drops["disagree"] += 1
            continue
        if verdict is not None:
            drops[verdict] += 1
            continue

        # Track agreement for stats
        a, b = sorted(am.keys())
        pair_agree[(a, b)][0] += 1
        pair_agree[(a, b)][1] += 1

        consensus = next(iter(am.values()))["selected_key"]
        question, options, subdomain = apply_edits(rec, am)

        # Domain follows subdomain via the canonical map; fall back to the
        # record's own domain if the subdomain isn't recognised.
        original_domain = rec.get("domain")
        domain = canonical_domain.get(subdomain, original_domain)
        if domain != original_domain:
            domain_corrections += 1

        # Strip dead `is_iaa` field from per-annotator records.
        am_clean = {
            name: {k: v for k, v in rec_a.items() if k != "is_iaa"}
            for name, rec_a in am.items()
        }

        final.append({
            "id": rec["id"],
            "question": clean(question),
            "options": {k: clean(v) for k, v in options.items()},
            "correct_key": consensus,
            "domain": domain,
            "subdomain": subdomain,
            "level": rec.get("level"),
            "source": rec.get("source"),
            "source_url": rec.get("source_url"),
            "quality_flags": rec.get("quality_flags", []),
            "length_tier": rec.get("length_tier"),
            "annotator_metadata": am_clean,
        })

    final.sort(key=lambda x: x["id"])

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    dom = Counter(r["domain"] for r in final)
    sub = Counter((r["domain"], r["subdomain"]) for r in final)
    total_agree = sum(p[0] for p in pair_agree.values())
    total_pairs = sum(p[1] for p in pair_agree.values())

    stats = {
        "total_input": len(combined),
        "total_included": len(final),
        "domain_corrections": domain_corrections,
        "drop_breakdown": dict(drops),
        "domain_distribution": dict(dom),
        "subdomain_distribution": {
            f"{d} / {s}": c for (d, s), c in sub.most_common()
        },
        "agreement": {
            "overall_observed": round(total_agree / total_pairs, 4) if total_pairs else 0,
            "overall_cohen_kappa_simplified": round(
                cohen_kappa(total_agree, total_pairs), 4
            ),
            "per_pair": {
                f"{a} + {b}": {
                    "agree": p[0],
                    "total": p[1],
                    "rate": round(p[0] / p[1], 3) if p[1] else 0,
                }
                for (a, b), p in sorted(pair_agree.items())
            },
        },
    }
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(final)} MCQs)")
    print(f"Wrote {DST_STATS.relative_to(REPO_ROOT)}")
    print(f"\nDomain corrected via canonical map: {domain_corrections}")
    print(f"\nDrop breakdown:")
    for k, v in drops.most_common():
        print(f"  {k:<20} {v}")
    print(f"\nDomain distribution:")
    for k, v in dom.most_common():
        print(f"  {k:<20} {v}")
    print(f"\nOverall agreement: {stats['agreement']['overall_observed']*100:.1f}%")
    print(f"Cohen kappa:       {stats['agreement']['overall_cohen_kappa_simplified']:.3f}")


if __name__ == "__main__":
    main()
