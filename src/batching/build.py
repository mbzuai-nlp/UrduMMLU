#!/usr/bin/env python3
"""Stage 16 — batch splitting (no IAA pool).

Reads ``data/15-subsampling/mcqs_to_annotate.json`` (~17,579 MCQs) and
splits the whole pool into regular batches of ``BATCH_SIZE`` MCQs,
stratified across subdomains so every batch has a balanced mix.

The team has chosen to dual-annotate every MCQ (assignment side handles
the duplication), so no separate IAA pool is selected here.

Each output row carries two extra fields for the annotation tool:

  - ``batch_id`` — ``"batch_NNN"``
  - ``is_iaa``  — always ``false`` (kept for schema continuity)

Outputs:

  data/16-batching/
  ├── manifest.json          # config + per-batch subdomain mix
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


def build_batches(items: list, rng: random.Random) -> list:
    """Round-robin items into batches so each batch has a balanced subdomain mix."""
    n_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

    by_sub = defaultdict(list)
    for item in items:
        by_sub[item.get("subdomain", "?")].append(item)

    for it_list in by_sub.values():
        rng.shuffle(it_list)

    batches = [[] for _ in range(n_batches)]
    cursor = 0
    for sub in sorted(by_sub.keys()):
        for item in by_sub[sub]:
            batches[cursor % n_batches].append(item)
            cursor += 1
    return batches


def main() -> None:
    print(f"Source:  {SRC}")
    print(f"Output:  {DST_DIR}\n")

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} rows from stage 15\n")

    rng = random.Random(SEED)
    batches = build_batches(data, rng)
    for idx, batch in enumerate(batches, start=1):
        batch_id = f"batch_{idx:03d}"
        for it in batch:
            it["batch_id"] = batch_id
            it["is_iaa"] = False

    # Write files
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
        path = BATCHES_DIR / f"{batch_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=4)
        sub_counts = Counter(it.get("subdomain") for it in batch)
        batch_index.append({
            "id": batch_id,
            "size": len(batch),
            "subdomains": dict(sub_counts),
        })

    manifest = {
        "seed": SEED,
        "batch_size": BATCH_SIZE,
        "input_rows": len(data),
        "batch_count": len(batches),
        "regular_count": sum(len(b) for b in batches),
        "iaa": False,
        "batches": batch_index,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=4)

    sizes = Counter(len(b) for b in batches)
    print(f"=== Batches ===")
    print(f"  total batches:    {len(batches)}")
    print(f"  size distribution: {dict(sorted(sizes.items()))}")
    print(f"  total MCQs:       {sum(len(b) for b in batches)}")
    print(f"\n  {MANIFEST}")
    print(f"  {BATCHES_DIR}/  ({len(batches)} files)")


if __name__ == "__main__":
    main()
