#!/usr/bin/env python3
"""Stage 23 — anonymize annotator names in the final combined dataset.

Reads  data/22-final-combined/mcqs.json
Writes data/23-anonymize/mcqs.json     — same records with names replaced
       data/23-anonymize/mapping.json   — { real_name → ann_N }

Replaces every annotator's real name with a stable ``ann_N`` token in:
  * the keys of ``annotator_metadata``
  * the ``annotator`` field inside each per-annotator record

Names are assigned alphabetically so the mapping is deterministic across
re-runs (Ahmed → ann_0, Ahmer → ann_1, …).

Usage:
    python src/anonymize/build.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "22-final-combined" / "mcqs.json"
DST_DIR = REPO_ROOT / "data" / "23-anonymize"
DST_MCQS = DST_DIR / "mcqs.json"
DST_MAPPING = DST_DIR / "mapping.json"


def main() -> None:
    records = json.load(open(SRC, encoding="utf-8"))

    # Collect every annotator name appearing anywhere
    names: set[str] = set()
    for rec in records:
        am = rec.get("annotator_metadata") or {}
        for name, sub in am.items():
            names.add(name)
            if isinstance(sub, dict) and sub.get("annotator"):
                names.add(sub["annotator"])

    mapping = {name: f"ann_{i}" for i, name in enumerate(sorted(names))}

    out: list[dict] = []
    for rec in records:
        new = dict(rec)
        am = rec.get("annotator_metadata")
        if am:
            new_am: dict[str, dict] = {}
            for name, sub in am.items():
                anon = mapping[name]
                new_sub = dict(sub) if isinstance(sub, dict) else sub
                if isinstance(new_sub, dict) and "annotator" in new_sub:
                    new_sub["annotator"] = mapping[new_sub["annotator"]]
                new_am[anon] = new_sub
            new["annotator_metadata"] = new_am
        out.append(new)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    with open(DST_MCQS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(DST_MAPPING, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"Wrote {DST_MCQS.relative_to(REPO_ROOT)} ({len(out)} records)")
    print(f"Wrote {DST_MAPPING.relative_to(REPO_ROOT)} ({len(mapping)} annotators)")
    print("\nMapping:")
    for name, anon in mapping.items():
        print(f"  {anon:<8} ← {name}")


if __name__ == "__main__":
    main()
