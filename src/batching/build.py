#!/usr/bin/env python3
"""Stage 16 — batch splitting (subdomain-pure).

Reads ``data/15-subsampling/mcqs_to_annotate.json`` and chunks it into
batches of ``BATCH_SIZE`` MCQs, **one subdomain per batch** so the
assignment stage can apply subdomain-based rules (e.g. only doctors do
chemistry/biology batches; only the arts specialist does arts batches).

Outputs:

  data/16-batching/
  ├── manifest.json          # incl. each batch's primary_subdomain
  └── batches/
      ├── batch_001.json
      └── ...
"""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "15-subsampling" / "mcqs_to_annotate.json"
DST_DIR = REPO_ROOT / "data" / "16-batching"
BATCHES_DIR = DST_DIR / "batches"
MANIFEST = DST_DIR / "manifest.json"

SEED = 42
BATCH_SIZE = 50


def build_batches(items: list, rng: random.Random) -> list[list[dict]]:
    """Group items by subdomain, then chunk each subdomain into BATCH_SIZE pieces."""
    by_sub: dict[str, list] = defaultdict(list)
    for item in items:
        by_sub[item.get("subdomain", "?")].append(item)

    batches = []
    for sub in sorted(by_sub.keys()):
        sub_items = by_sub[sub]
        rng.shuffle(sub_items)
        for i in range(0, len(sub_items), BATCH_SIZE):
            batches.append(sub_items[i:i + BATCH_SIZE])
    return batches


def main() -> None:
    print(f"Source:  {SRC}")
    print(f"Output:  {DST_DIR}\n")

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} rows from stage 15\n")

    rng = random.Random(SEED)
    batches = build_batches(data, rng)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    for old in BATCHES_DIR.glob("batch_*.json"):
        old.unlink()
    # Remove any stale IAA file from a previous run
    iaa_legacy = DST_DIR / "iaa_batch.json"
    if iaa_legacy.exists():
        iaa_legacy.unlink()

    batch_index = []
    for idx, batch in enumerate(batches, start=1):
        batch_id = f"batch_{idx:03d}"
        primary_sub = batch[0].get("subdomain", "?")
        for it in batch:
            it["batch_id"] = batch_id
            it["is_iaa"] = False
        path = BATCHES_DIR / f"{batch_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=4)
        batch_index.append({
            "id": batch_id,
            "size": len(batch),
            "primary_subdomain": primary_sub,
            "subdomains": dict(Counter(it.get("subdomain") for it in batch)),
        })

    manifest = {
        "seed": SEED,
        "batch_size": BATCH_SIZE,
        "input_rows": len(data),
        "batch_count": len(batches),
        "regular_count": sum(len(b) for b in batches),
        "subdomain_pure": True,
        "batches": batch_index,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=4)

    # Report
    sub_counts = Counter(b["primary_subdomain"] for b in batch_index)
    sizes = Counter(b["size"] for b in batch_index)
    print(f"=== Batches ===")
    print(f"  total:              {len(batches)}")
    print(f"  size distribution:  {dict(sorted(sizes.items()))}")
    print(f"  total MCQs:         {sum(len(b) for b in batches)}")
    print(f"\n=== Batches per subdomain ===")
    for sub, n in sub_counts.most_common():
        print(f"  {sub:<35} {n:>3}")
    print(f"\n  {MANIFEST}")
    print(f"  {BATCHES_DIR}/  ({len(batches)} files)")


if __name__ == "__main__":
    main()
