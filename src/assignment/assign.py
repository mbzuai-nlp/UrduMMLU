#!/usr/bin/env python3
"""Stage 17 — dual-annotation assignment.

Reads the manifest produced by stage 16 and emits
``data/17-assignments/assignments.json`` mapping each annotator handle
to a sorted list of ``batch_id``s they own.

**Dual annotation**: every batch is assigned to exactly two different
annotators. Each annotator therefore ends up with roughly
``2 × n_batches / n_annotators`` batches.

Algorithm:
  1. Shuffle the batch list once (seed=SEED) for fairness.
  2. **Pass 1** — round-robin deal: ``batch[i] → annotators[i % N]``.
  3. **Pass 2** — same deal with a shift of ``N // 2`` so the second
     annotator on each batch is different from the first.

Usage:
    python src/assignment/assign.py alice bob carol diana
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "data" / "16-batching" / "manifest.json"
DST = REPO_ROOT / "data" / "17-assignments" / "assignments.json"
SEED = 42


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs="+", help="annotator handles")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    annotators = args.annotators
    if len(annotators) < 2:
        raise SystemExit("dual annotation requires at least 2 annotators")

    if not MANIFEST.exists():
        raise SystemExit(f"missing {MANIFEST} — run src/batching/build.py first")

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)

    batch_ids = sorted(b["id"] for b in manifest["batches"])
    rng = random.Random(args.seed)
    rng.shuffle(batch_ids)

    n = len(annotators)
    shift = max(1, n // 2)

    assignments = {a: [] for a in annotators}
    coverage = Counter()
    for i, bid in enumerate(batch_ids):
        a1 = annotators[i % n]
        a2 = annotators[(i + shift) % n]
        assignments[a1].append(bid)
        assignments[a2].append(bid)
        coverage[bid] += 2

    # Sanity: every batch covered exactly twice
    if any(c != 2 for c in coverage.values()):
        raise SystemExit("internal error: not every batch ended up dual-covered")

    out = {
        "seed": args.seed,
        "n_annotators": n,
        "n_batches": len(batch_ids),
        "dual_annotation": True,
        "annotators": sorted(annotators),
        "assignments": {a: sorted(b) for a, b in assignments.items()},
    }

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)

    print(f"Wrote {DST}")
    print(f"  dual annotation: {len(batch_ids)} batches × 2 = {2 * len(batch_ids)} batch-slots")
    print(f"  shift between passes: {shift}")
    print()
    for a in annotators:
        batches = assignments[a]
        print(f"  {a:<20} {len(batches):>4} batches")


if __name__ == "__main__":
    main()
