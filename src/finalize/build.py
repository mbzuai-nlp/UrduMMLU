#!/usr/bin/env python3
"""Build the final combined dataset.

Auto-discovers the latest numbered pipeline stage under ``data/``
(``13-correlation-deduplicated/`` at the time of writing), reads both
``mcqs_with_answers.json`` and ``mcqs_without_answers.json`` from it,
concatenates them into a single list, and writes the result to
``data/!-final/mcqs.json``.

Re-numbering: ``id`` is assigned contiguously ``0..N-1`` over the
combined list so it is unique across the file. The original per-source
ids would collide because both source files restart at 0.

Rows from ``mcqs_with_answers`` keep their ``correct_option`` /
``correct_key``; rows from ``mcqs_without_answers`` have those fields
as ``None``, which is sufficient to tell the two halves apart.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DST_DIR = DATA_DIR / "!-final"
DST_FILE = DST_DIR / "mcqs.json"

WITH_ANSWERS = "mcqs_with_answers.json"
WITHOUT_ANSWERS = "mcqs_without_answers.json"

STAGE_RE = re.compile(r"^(\d+)-")


def latest_stage() -> Path:
    candidates = []
    for p in DATA_DIR.iterdir():
        if not p.is_dir():
            continue
        m = STAGE_RE.match(p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    if not candidates:
        raise FileNotFoundError(f"no numbered stages found under {DATA_DIR}")
    # Walk highest → lowest, pick the first stage that contains either input file.
    # Stages past the pure-data section (15-subsampling onward) reshape MCQs into
    # batches/manifests and don't carry the with/without_answers pair anymore.
    candidates.sort(key=lambda x: x[0], reverse=True)
    for _, p in candidates:
        if (p / WITH_ANSWERS).exists() or (p / WITHOUT_ANSWERS).exists():
            return p
    return candidates[0][1]


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    stage = latest_stage()
    src_with = stage / WITH_ANSWERS
    src_without = stage / WITHOUT_ANSWERS

    print(f"Source stage:  {stage}")
    print(f"  + {src_with.name}")
    print(f"  + {src_without.name}")
    print(f"Destination:   {DST_FILE}\n")

    with_data = load(src_with) if src_with.exists() else []
    without_data = load(src_without) if src_without.exists() else []

    combined = []
    for i, item in enumerate(with_data + without_data):
        item["id"] = i
        combined.append(item)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=4)

    answered = sum(1 for x in combined if x.get("correct_option") is not None)
    unanswered = len(combined) - answered

    print(f"with_answers rows:    {len(with_data)}")
    print(f"without_answers rows: {len(without_data)}")
    print(f"combined total:       {len(combined)}")
    print(f"  answered:           {answered}")
    print(f"  unanswered:         {unanswered}")


if __name__ == "__main__":
    main()
