#!/usr/bin/env python3
"""Sample MCQs from each unlabeled-level source for human/LLM classification.

For each source that has empty ``level`` everywhere, draws a random
20-MCQ sample (one per subdomain weighted by frequency) and writes them
to ``tmp/level_samples/<source>.json`` for review.

The intended workflow:
  1. Run this to get the samples.
  2. Either eyeball them or feed them to an LLM with the few-shot
     classification prompt embedded below.
  3. Add the per-source decision to ``SOURCE_LEVEL_MAP`` in
     ``src/final/build.py`` (or a similar override map).

Usage:
    python src/analysis/level_few_shot.py
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "25-final" / "mcqs.json"
OUT_DIR = REPO_ROOT / "tmp" / "level_samples"
SAMPLE_SIZE = 20
SEED = 42

PROMPT_HEADER = """\
Classify the Pakistani educational level of the following Urdu MCQ.
Choose exactly one of: SSC-I (grade 9), SSC-II (grade 10),
HSSC-I (grade 11), HSSC-II (grade 12).

Guidelines:
  SSC-I  / SSC-II  : matric-level. Basic chem/bio/physics, elementary
                     math, basic urdu, civics, pakistan studies basics.
  HSSC-I / HSSC-II : intermediate. Advanced sciences, economics,
                     sociology, psychology, computer science, advanced
                     urdu literature, advanced math.
Reply with the level only.
"""


def main() -> None:
    records = json.load(open(SRC, encoding="utf-8"))
    rng = random.Random(SEED)

    # Bucket records by source-name where level is empty
    by_source: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        if rec.get("level"):
            continue
        for s in rec.get("source", []):
            by_source[s["name"]].append(rec)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, recs in sorted(by_source.items(), key=lambda x: -len(x[1])):
        sample = rng.sample(recs, min(SAMPLE_SIZE, len(recs)))
        payload = {
            "source": name,
            "total_unlabeled": len(recs),
            "sample_size": len(sample),
            "prompt": PROMPT_HEADER.strip(),
            "samples": [
                {
                    "id": r["id"],
                    "domain": r["domain"],
                    "subdomain": r["subdomain"],
                    "question": r["question"],
                    "options": r["options"],
                    "correct_key": r["correct_key"],
                }
                for r in sample
            ],
        }
        out_path = OUT_DIR / f"{name.replace(' ', '_')}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_path.relative_to(REPO_ROOT)} ({len(sample)} samples, {len(recs):,} total unlabeled)")


if __name__ == "__main__":
    main()
