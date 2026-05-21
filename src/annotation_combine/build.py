#!/usr/bin/env python3
"""Stage 20 — combine raw annotator submissions into one MCQ-keyed file.

Reads:
  - data/16-subsampling/mcqs_to_annotate.json
  - data/18-assignments/assignments.json     (used to filter out "extras"
                                              from the prior, reshuffled
                                              assignment)
  - data/19-annotated/<name>/<name>__batch_NNN.json   (per-batch submissions)

Writes:
  - data/20-annotated-combined/mcqs.json

Each output record preserves every Stage-16 field intact and adds:

    "annotator_metadata": {
        "<annotator_name>": { ... full submitted annotation record ... },
        "<annotator_name>": { ... },
    }

No filtering / consensus logic is applied here. Stage 21 owns the rules
for turning these combined records into the final benchmark.

Usage:
    python src/annotation_combine/build.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_MCQS = REPO_ROOT / "data" / "16-subsampling" / "mcqs_to_annotate.json"
SRC_ASSIGN = REPO_ROOT / "data" / "18-assignments" / "assignments.json"
SRC_ANNOT_DIR = REPO_ROOT / "data" / "19-annotated"
DST_DIR = REPO_ROOT / "data" / "20-annotated-combined"
DST_FILE = DST_DIR / "mcqs.json"


def load_mcqs() -> dict:
    with open(SRC_MCQS, encoding="utf-8") as f:
        return {m["id"]: m for m in json.load(f)}


def load_assigned_pairs() -> set[tuple[str, str]]:
    with open(SRC_ASSIGN, encoding="utf-8") as f:
        cfg = json.load(f)
    return {
        (annotator, batch_id)
        for annotator, batches in cfg["assignments"].items()
        for batch_id in batches
    }


def load_annotations() -> list[dict]:
    rows: list[dict] = []
    for folder in sorted(SRC_ANNOT_DIR.iterdir()):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.suffix != ".json":
                continue
            with open(f, encoding="utf-8") as fh:
                sub = json.load(fh)
            rows.extend(sub.get("annotations", []))
    return rows


def main() -> None:
    mcqs = load_mcqs()
    assigned_pairs = load_assigned_pairs()
    annotations = load_annotations()

    kept = [a for a in annotations if (a["annotator"], a["batch_id"]) in assigned_pairs]
    dropped_extras = len(annotations) - len(kept)

    by_mcq: dict[int, dict[str, dict]] = defaultdict(dict)
    for a in kept:
        by_mcq[a["mcq_id"]][a["annotator"]] = a

    combined: list[dict] = []
    for mcq_id, am in by_mcq.items():
        src = mcqs.get(mcq_id)
        if src is None:
            continue
        rec = dict(src)
        rec["annotator_metadata"] = am
        combined.append(rec)

    combined.sort(key=lambda x: x["id"])

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    dual = sum(1 for r in combined if len(r["annotator_metadata"]) == 2)
    single = sum(1 for r in combined if len(r["annotator_metadata"]) == 1)
    print(f"Wrote {DST_FILE.relative_to(REPO_ROOT)} ({len(combined)} MCQs)")
    print(f"  dual-annotated:   {dual}")
    print(f"  single-annotated: {single}")
    print(f"  extras dropped:   {dropped_extras}")


if __name__ == "__main__":
    main()
