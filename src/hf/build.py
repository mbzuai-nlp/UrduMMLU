#!/usr/bin/env python3
"""Stage 27-hf — Hugging Face release snapshot (sorted + renumbered).

Reads  data/26-eval/mcqs.json          (frozen eval snapshot, original ids)
Writes data/27-hf/urdummlu.json        (sorted by domain/subdomain, ids 0..N)
       data/27-hf/stats.json
       data/26-eval/id_map.json         (new_id -> original_id crosswalk)

This is the ONLY published artifact (uploaded to huggingface.co by
.github/workflows/hf-push.yml). Records are reordered for clean browsing:

  * domain order: STEM, Social Sciences, Humanities, Profession, Other
  * within each domain: subdomain by frequency (most common first)
  * ids are renumbered 0..N in the new order

Because ids are renumbered, the public ids deliberately differ from the eval
ids in data/26-eval/. The emitted id_map.json (kept in 26-eval, unpublished)
bridges the two spaces so a published record can always be traced back to its
evaluation id.

Usage:
    python src/hf/build.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "26-eval" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "27-hf"
DST_MCQS = DST_DIR / "urdummlu.json"
DST_STATS = DST_DIR / "stats.json"
ID_MAP = REPO_ROOT / "data" / "26-eval" / "id_map.json"

# Release ordering: records are grouped by domain in this order, then by
# subdomain (most frequent first within each domain).
DOMAIN_ORDER = ("STEM", "Social Sciences", "Humanities", "Profession", "Other")


def compute_stats(out: list[dict]) -> dict:
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

    return {
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


def main() -> None:
    rows = json.load(open(SRC, encoding="utf-8"))

    # ── Sort: domain order, then subdomain by frequency (stable on orig id) ──
    domain_rank = {d: i for i, d in enumerate(DOMAIN_ORDER)}
    sub_counts = Counter((r["domain"], r["subdomain"]) for r in rows)
    rows.sort(
        key=lambda r: (
            domain_rank.get(r["domain"], len(DOMAIN_ORDER)),
            -sub_counts[(r["domain"], r["subdomain"])],
            r["subdomain"] or "",
            r["id"],
        )
    )

    # ── Renumber ids 0..N in the new order; record the crosswalk ──────────
    id_map: dict[str, int] = {}
    out: list[dict] = []
    for new_id, rec in enumerate(rows):
        id_map[str(new_id)] = rec["id"]
        out.append({**rec, "id": new_id})

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(compute_stats(out), f, ensure_ascii=False, indent=2)
    with open(ID_MAP, "w", encoding="utf-8") as f:
        json.dump(id_map, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(out):,} records, ids renumbered 0..{len(out) - 1})")
    print(f"Wrote {DST_STATS.relative_to(REPO_ROOT)}")
    print(f"Wrote {ID_MAP.relative_to(REPO_ROOT)} ({len(id_map):,} new->original pairs)")
    print(f"First record: id=0 domain={out[0]['domain']} subdomain={out[0]['subdomain']}")


if __name__ == "__main__":
    main()
