#!/usr/bin/env python3
"""Standardize data/1-raw/upsample_mcqs.json → data/2-processed/upsample_mcqs.json.

The raw upsample file (testpointpk.com scrape) ships with extra fields
(english translations, snake_case ``std_subdomain``, source as
``"testpointpk.com"``). This stage aligns it with the shared Stage-2
schema used by the other processed files (e.g. ``mcqtimes.json``):

  id, question, options, domain, subdomain, correct_option, correct_index,
  level, source_url, source

Notes
-----
* ``correct_option`` is stored as a letter (``A``..``E``), matching the
  testpointpk/etest/examaunty/gotest convention noted in
  ``src/schema_canonicalization/canonicalize.py``. Stage 6 turns it into
  the full text + key.
* The ``E`` slot is preserved when present (52 records have a real E
  option, 471 have "None of these").
* English translations and ``language`` are dropped — they aren't part
  of the Stage-2 schema.
* ``std_domain`` "Psychology & Education" is folded into "Social Sciences"
  (matches the convention in the existing files; education and psychology
  already live under Social Sciences there).
* ``std_subdomain`` snake_case is converted to space-separated form.

Usage:
    python src/upsample/standardize.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "1-raw" / "upsample_mcqs.json"
DST = REPO_ROOT / "data" / "2-processed" / "upsample_mcqs.json"

DOMAIN_MAP = {
    "Social Sciences": "Social Sciences",
    "STEM": "STEM",
    "Psychology & Education": "Social Sciences",
}

# Align upsample's snake_case subdomain values with the canonical names
# used elsewhere in the pipeline.
SUBDOMAIN_RENAMES = {
    "current affairs": "current and international affairs",
    "international affairs": "current and international affairs",
}


def normalize_subdomain(s: str) -> str:
    name = (s or "").replace("_", " ").strip()
    return SUBDOMAIN_RENAMES.get(name, name)


OPTION_KEYS = ("A", "B", "C", "D", "E")


def standardize(rec: dict, idx: int) -> dict:
    domain = DOMAIN_MAP.get(rec.get("std_domain"), rec.get("std_domain"))
    subdomain = normalize_subdomain(rec.get("std_subdomain", ""))
    urdu_opts = rec.get("options_urdu") or []
    options = {OPTION_KEYS[i]: text for i, text in enumerate(urdu_opts)}
    return {
        "id": idx,
        "question": rec["question"],
        "options": options,
        "domain": domain,
        "subdomain": subdomain,
        "correct_option": rec.get("correct_answer"),
        "correct_index": rec.get("correct_index"),
        "level": rec.get("level", ""),
        "source_url": rec.get("url"),
        "source": "testpointpk",
    }


def main() -> None:
    with open(SRC, encoding="utf-8") as f:
        raw = json.load(f)

    # Filter to align with the mcqtimes/pakmcqs/native_mcqs A-D convention:
    #   * keep 4-option records as-is
    #   * trim the 5th option from records where correct ∈ A-D (it's almost
    #     always "None of these")
    #   * drop records where correct = E (those need the 5th slot)
    #   * drop malformed records with <4 options
    filtered: list[dict] = []
    dropped_corr_e = 0
    trimmed_e = 0
    dropped_too_few = 0
    for r in raw:
        urdu = r.get("options_urdu") or []
        n = len(urdu)
        if n < 4:
            dropped_too_few += 1
            continue
        if n >= 5:
            if r.get("correct_answer") == "E":
                dropped_corr_e += 1
                continue
            r = {**r, "options_urdu": urdu[:4]}
            trimmed_e += 1
        filtered.append(r)

    out = [standardize(r, i) for i, r in enumerate(filtered)]

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    from collections import Counter
    dom = Counter(r["domain"] for r in out)
    sub = Counter(r["subdomain"] for r in out)
    print(f"Wrote {DST.relative_to(REPO_ROOT)} ({len(out)} records)")
    print(f"  trimmed E option:        {trimmed_e}")
    print(f"  dropped (correct = E):   {dropped_corr_e}")
    print(f"  dropped (<4 options):    {dropped_too_few}")
    print(f"\nDomain:")
    for d, n in dom.most_common(): print(f"  {d:<22} {n}")
    print(f"\nSubdomain:")
    for s, n in sub.most_common(): print(f"  {s:<25} {n}")


if __name__ == "__main__":
    main()
