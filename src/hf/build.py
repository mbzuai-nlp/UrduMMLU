#!/usr/bin/env python3
"""Stage 26 — Hugging Face release snapshot.

Reads  data/25-final/mcqs.json
Writes data/26-hf/mcqs.json
       data/26-hf/stats.json

The release file is a slim view of the final dataset, dropping internal
provenance/traceability fields and per-annotator records that aren't
needed by downstream evaluators.

Released schema (every record exactly these keys, in this order):
  id, question, options, correct_key, domain, subdomain, level,
  length_tier, source

Usage:
    python src/hf/build.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "25-final" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "26-hf"
DST_MCQS = DST_DIR / "mcqs.json"
DST_STATS = DST_DIR / "stats.json"

KEEP_KEYS = (
    "id",
    "question",
    "options",
    "correct_key",
    "domain",
    "subdomain",
    "level",
    "length_tier",
    "source",
)


def main() -> None:
    rows = json.load(open(SRC, encoding="utf-8"))
    out = [{k: rec.get(k) for k in KEEP_KEYS} for rec in rows]

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # ── Stats ─────────────────────────────────────────────────────────
    domain = Counter(r["domain"] for r in out)
    subdomain = Counter((r["domain"], r["subdomain"]) for r in out)
    level = Counter(r["level"] for r in out)
    length_tier = Counter(r["length_tier"] for r in out)
    correct_key = Counter(r["correct_key"] for r in out)

    source_name = Counter()
    for r in out:
        for s in r["source"] or []:
            source_name[s["name"]] += 1

    level_by_domain: dict[str, Counter] = defaultdict(Counter)
    for r in out:
        level_by_domain[r["domain"]][r["level"]] += 1

    stats = {
        "total": len(out),
        "domain_distribution": dict(domain.most_common()),
        "subdomain_distribution": {f"{d} / {s}": c for (d, s), c in subdomain.most_common()},
        "level_distribution": {k: level[k] for k in ("SSC-I", "SSC-II", "HSSC-I", "HSSC-II") if k in level},
        "level_by_domain": {
            d: {k: level_by_domain[d][k] for k in ("SSC-I", "SSC-II", "HSSC-I", "HSSC-II") if k in level_by_domain[d]}
            for d in domain
        },
        "length_tier_distribution": dict(length_tier.most_common()),
        "correct_key_distribution": dict(sorted(correct_key.items())),
        "source_distribution": dict(source_name.most_common()),
    }
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(out):,} records)")
    print(f"Wrote {DST_STATS.relative_to(REPO_ROOT)}")
    print(f"Keys per record: {list(out[0].keys())}")


if __name__ == "__main__":
    main()
