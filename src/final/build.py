#!/usr/bin/env python3
"""Stage 25 — final benchmark dataset.

Reads  data/24-deduplicated/mcqs.json   (already deduped at Jaccard ≥ 0.85)
Writes data/25-final/mcqs.json          (contiguous IDs starting at 0)
       data/25-final/stats.json         (domain/subdomain/provenance counts)

This stage is a thin sealing step over Stage 24:

  * Renumbers ``id`` to be a contiguous 0..N range (gaps left by dedup
    are removed).
  * Preserves the previous ``id`` as ``legacy_id``. Any pre-existing
    ``legacy_id`` from Stage 22 is preserved as ``stage22_id`` for
    full traceability.

Usage:
    python src/final/build.py
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "24-deduplicated" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "25-final"
DST_MCQS = DST_DIR / "mcqs.json"
DST_STATS = DST_DIR / "stats.json"

SEED = 42

# Trusted level labels come from book-based sources (Pakistani textbooks
# with explicit grade tags). We use the empirical (subdomain → level)
# distribution from those records to assign levels to MCQs from
# web-scraped sources, sampling proportionally so each subdomain's grade
# mix is preserved.
BOOK_SOURCES = {"Ustad 360", "FBISE", "BISE Multan 2025"}


# Display-name map for the canonical source identifier. Keyed by URL host
# (for web scrapes) or by the legacy display name (for book sources).
# Book hosts are listed too so the URL-based lookup also resolves to the
# right display name after the homepage URL is attached.
SOURCE_DISPLAY_NAMES = {
    # Web sources — key = bare hostname
    "mcqtimes.com":     "MCQ Times",
    "testpointpk.com":  "TestPoint PK",
    "etest.com.pk":     "eTest",
    "examaunty.com":    "ExamAunty",
    "gotest.com.pk":    "GoTest",
    "pakmcqs.com":      "PakMCQs",
    # Book homepages
    "ustad360.com":     "Ustad 360",
    "fbise.edu.pk":     "FBISE",
    "bisemultan.edu.pk": "BISE Multan 2025",
    # Legacy display names as a fallback when no URL is attached
    "Ustad 360":        "Ustad 360",
    "FBISE":            "FBISE",
    "BISE Multan 2025": "BISE Multan 2025",
}

# Homepage URLs for sources that come from books/PDFs (no per-record URL).
# Used as a fallback when ``source_url`` is missing.
SOURCE_HOMEPAGE_URLS = {
    "Ustad 360":        "https://www.ustad360.com",
    "FBISE":            "https://www.fbise.edu.pk",
    "BISE Multan 2025": "https://www.bisemultan.edu.pk",
}


def standardize_source_name(name: str, url: str | None) -> str:
    """Return the canonical display name for a source."""
    if url:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host in SOURCE_DISPLAY_NAMES:
            return SOURCE_DISPLAY_NAMES[host]
        # Fallback: title-cased hostname (without TLD)
        return host.split(".")[0].title()
    return SOURCE_DISPLAY_NAMES.get(name, name)


def main() -> None:
    rows = json.load(open(SRC, encoding="utf-8"))
    print(f"Loaded {len(rows):,} rows from {SRC.relative_to(REPO_ROOT)}")

    # ── Build the empirical (subdomain → level distribution) map from the
    # book-source records — these have trusted grade tags. ────────────────
    sub_level_counts: dict[str, Counter] = defaultdict(Counter)
    global_level_counts: Counter = Counter()
    for rec in rows:
        # Stage 24 input still stores ``source`` as a flat list of names
        names = set(rec.get("source") or [])
        if not (names & BOOK_SOURCES):
            continue
        lvl = rec.get("level")
        if not lvl:
            continue
        sub_level_counts[rec.get("subdomain", "")][lvl] += 1
        global_level_counts[lvl] += 1

    def sample_level(subdomain: str, rng: random.Random) -> str | None:
        dist = sub_level_counts.get(subdomain) or global_level_counts
        if not dist:
            return None
        levels, weights = zip(*dist.items())
        return rng.choices(levels, weights=weights, k=1)[0]

    rng = random.Random(SEED)
    DROP_FIELDS = {"id", "legacy_id", "quality_flags", "source", "source_url"}
    out: list[dict] = []
    level_fills: Counter = Counter()
    for new_id, rec in enumerate(rows):
        new = {"id": new_id, "legacy_id": rec["id"]}
        if "legacy_id" in rec:
            new["stage22_id"] = rec["legacy_id"]
        for k, v in rec.items():
            if k in DROP_FIELDS:
                continue
            new[k] = v

        # Fill missing level by sampling from the empirical subdomain
        # distribution learned above.
        if not new.get("level"):
            lvl = sample_level(rec.get("subdomain", ""), rng)
            if lvl:
                new["level"] = lvl
                level_fills[lvl] += 1

        # Merge `source` (list of names) + `source_url` (list of urls) into a
        # single `source` list of `{name, url}` dicts. Missing/empty URLs
        # become null (e.g. book-based sources like Ustad 360, FBISE).
        # The name is standardized from the URL host when available.
        names = rec.get("source") or []
        urls = rec.get("source_url") or []
        merged_sources = []
        for i, name in enumerate(names):
            url = urls[i] if i < len(urls) else ""
            url = url or SOURCE_HOMEPAGE_URLS.get(name)
            merged_sources.append({
                "name": standardize_source_name(name, url),
                "url": url,
            })
        new["source"] = merged_sources

        # Stratify correct_key: shuffle option positions so A/B/C/D are
        # roughly equiprobable. Avoids the matric-paper bias where D is
        # under-used. Stable: same seed → same permutation per record.
        if isinstance(new.get("options"), dict) and new.get("correct_key") in new["options"]:
            correct_text = new["options"][new["correct_key"]]
            keys = list(new["options"].keys())
            values = list(new["options"].values())
            rng.shuffle(values)
            new["options"] = dict(zip(keys, values))
            new["correct_key"] = next(k for k, v in new["options"].items() if v == correct_text)

        out.append(new)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    prov = Counter(r["provenance"] for r in out)
    dom = Counter(r["domain"] for r in out)
    sub = Counter((r["domain"], r["subdomain"]) for r in out)
    keys = Counter(r["correct_key"] for r in out)

    stats = {
        "total": len(out),
        "provenance": dict(prov),
        "correct_key_distribution": dict(keys),
        "domain_distribution": dict(dom.most_common()),
        "subdomain_distribution": {
            f"{d} / {s}": c for (d, s), c in sub.most_common()
        },
    }
    with open(DST_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(out):,} records)")
    print(f"Wrote {DST_STATS.relative_to(REPO_ROOT)}")
    print(f"\nLevel filled by empirical sampling: {sum(level_fills.values()):,}")
    for lvl, n in sorted(level_fills.items()):
        print(f"  {lvl:<10} {n:,}")
    print(f"\nProvenance: {dict(prov)}")
    print(f"\nDomain distribution:")
    for d, c in dom.most_common():
        print(f"  {d:<20} {c:,}")


if __name__ == "__main__":
    main()
