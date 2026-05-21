#!/usr/bin/env python3
"""Stage 22 — combine human-annotated and source-keyed MCQs into one benchmark.

Reads:
  - data/21-final-annotated/mcqs.json          (human-consensus labels)
  - data/15-english-filtered/mcqs_with_answers.json  (scraped source labels)

Writes:
  - data/22-final-combined/mcqs.json
  - data/22-final-combined/stats.json

Combines the two label sources into a single dataset. The two stages use
the same integer ID space for different MCQs (a known quirk of the
pipeline), so this stage:

  * assigns new contiguous IDs starting at 0
  * preserves each MCQ's original ID in ``legacy_id``
  * tags every record with ``provenance`` (``"annotated"`` or ``"scraped"``)

Conflicts resolution:

  * If the same question text appears in both inputs, the **annotated**
    record wins (human-verified beats scraped). The scraped duplicate is
    dropped.

Bidi marks (U+200E/F, U+202A-E, U+2066-9) are stripped from question and
options to match the Stage-21 convention — the combined dataset is
LLM-evaluation ready out of the box.

Usage:
    python src/final_combined/build.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ANNOTATED = REPO_ROOT / "data" / "21-final-annotated" / "mcqs.json"
SRC_SCRAPED = REPO_ROOT / "data" / "15-english-filtered" / "mcqs_with_answers.json"
SRC_UPSAMPLED = REPO_ROOT / "data" / "15-english-filtered" / "mcqs_upsampled.json"
DST_DIR = REPO_ROOT / "data" / "22-final-combined"
DST_MCQS = DST_DIR / "mcqs.json"
DST_STATS = DST_DIR / "stats.json"

BIDI_CHARS = "‎‏‪‫‬‭‮⁦⁧⁨⁩"
STRIP_BIDI = str.maketrans("", "", BIDI_CHARS)

# Per-subdomain domain overrides. Scraped data sometimes tags
# professional-skills content under "Other" — pull those into "Profession".
SUBDOMAIN_DOMAIN_OVERRIDES = {
    "professional development": "Profession",
    "federal investigation law": "Profession",
    "fine arts": "Humanities",
}

# Per-subdomain renames. The long tail of tiny vocational subdomains
# (home economics, hajj management, plumbing, …) collapses into a single
# "professional studies" bucket. ``professional development`` is large
# enough to stand on its own and is deliberately NOT in this list.
SUBDOMAIN_RENAMES = {
    "home economics": "professional studies",
    "hajj management": "professional studies",
    "tourism management": "professional studies",
    "media production": "professional studies",
    "clerical services": "professional studies",
    "plumbing": "professional studies",
    "federal investigation law": "professional studies",
    "tarjamatul quran": "islamic studies",
    "art and drawing": "fine arts",
}


def clean(s):
    return s.translate(STRIP_BIDI) if isinstance(s, str) else s


def clean_dict(d):
    return {k: clean(v) for k, v in d.items()} if isinstance(d, dict) else d


def normalize_annotated(rec: dict) -> dict:
    """Annotated records are already bidi-clean; just add provenance + legacy id."""
    return {
        "legacy_id": rec["id"],
        "provenance": "annotated",
        "question": rec["question"],
        "options": rec["options"],
        "correct_key": rec["correct_key"],
        "domain": rec.get("domain"),
        "subdomain": rec.get("subdomain"),
        "level": rec.get("level"),
        "source": rec.get("source"),
        "source_url": rec.get("source_url"),
        "quality_flags": rec.get("quality_flags", []),
        "length_tier": rec.get("length_tier"),
        "annotator_metadata": rec.get("annotator_metadata"),
    }


def normalize_scraped(rec: dict) -> dict:
    """Scraped records still have bidi marks — strip them here."""
    return {
        "legacy_id": rec["id"],
        "provenance": "scraped",
        "question": clean(rec["question"]),
        "options": clean_dict(rec["options"]),
        "correct_key": rec["correct_key"],
        "domain": rec.get("domain"),
        "subdomain": rec.get("subdomain"),
        "level": rec.get("level"),
        "source": rec.get("source"),
        "source_url": rec.get("source_url"),
        "quality_flags": [],
        "length_tier": None,
        "annotator_metadata": None,
    }


def main() -> None:
    annotated = json.load(open(SRC_ANNOTATED, encoding="utf-8"))
    scraped_all = json.load(open(SRC_SCRAPED, encoding="utf-8"))
    scraped = [m for m in scraped_all if m.get("correct_key") in ("A", "B", "C", "D")]
    upsampled_all = json.load(open(SRC_UPSAMPLED, encoding="utf-8"))
    upsampled = [m for m in upsampled_all if m.get("correct_key") in ("A", "B", "C", "D")]

    out: list[dict] = []
    seen_questions: set[str] = set()
    dropped_no_key = (len(scraped_all) - len(scraped)) + (len(upsampled_all) - len(upsampled))
    dropped_dup_question = 0

    # Annotated wins on conflict: ingest them first
    for rec in annotated:
        normalized = normalize_annotated(rec)
        key = normalized["question"].strip()
        if key in seen_questions:
            continue
        seen_questions.add(key)
        out.append(normalized)

    # Then the scraped source-keyed set
    for rec in scraped:
        normalized = normalize_scraped(rec)
        key = normalized["question"].strip()
        if key in seen_questions:
            dropped_dup_question += 1
            continue
        seen_questions.add(key)
        out.append(normalized)

    # Then the upsample (also source-keyed). Same normalisation as scraped.
    for rec in upsampled:
        normalized = normalize_scraped(rec)
        key = normalized["question"].strip()
        if key in seen_questions:
            dropped_dup_question += 1
            continue
        seen_questions.add(key)
        out.append(normalized)

    # Step 1: per-subdomain domain overrides (e.g. "professional development" → Profession)
    overrides_applied = 0
    for rec in out:
        new_domain = SUBDOMAIN_DOMAIN_OVERRIDES.get(rec.get("subdomain"))
        if new_domain and rec.get("domain") != new_domain:
            rec["domain"] = new_domain
            overrides_applied += 1

    # Step 2: per-subdomain renames (the long tail of vocational subdomains)
    renames_applied = 0
    for rec in out:
        new_sub = SUBDOMAIN_RENAMES.get(rec.get("subdomain"))
        if new_sub:
            rec["subdomain"] = new_sub
            renames_applied += 1

    # Assign new contiguous IDs starting at 0
    for new_id, rec in enumerate(out):
        rec["id"] = new_id
    # Reorder so id is first
    out = [
        {"id": r.pop("id"), **r} for r in out
    ]

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Stats
    prov = Counter(r["provenance"] for r in out)
    dom = Counter(r["domain"] for r in out)
    sub = Counter((r["domain"], r["subdomain"]) for r in out)
    correct_dist = Counter(r["correct_key"] for r in out)

    stats = {
        "total": len(out),
        "inputs": {
            "annotated": len(annotated),
            "scraped_with_valid_key": len(scraped),
            "upsampled_with_valid_key": len(upsampled),
            "scraped_dropped_no_key": dropped_no_key,
            "scraped_dropped_dup_question": dropped_dup_question,
        },
        "subdomain_domain_overrides": {
            "applied": overrides_applied,
            "mapping": SUBDOMAIN_DOMAIN_OVERRIDES,
        },
        "subdomain_renames": {
            "applied": renames_applied,
            "mapping": SUBDOMAIN_RENAMES,
        },
        "provenance": dict(prov),
        "correct_key_distribution": dict(correct_dist),
        "domain_distribution": dict(dom.most_common()),
        "subdomain_distribution": {
            f"{d} / {s}": c for (d, s), c in sub.most_common()
        },
    }
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(out)} MCQs)")
    print(f"Wrote {DST_STATS.relative_to(REPO_ROOT)}")
    print(f"\nProvenance: {dict(prov)}")
    print(f"\nDomain distribution:")
    for d, c in dom.most_common():
        print(f"  {d:<20} {c}")
    print(f"\nDropped: {dropped_dup_question} duplicate-question scraped MCQs")


if __name__ == "__main__":
    main()
