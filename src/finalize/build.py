#!/usr/bin/env python3
"""Build the final combined dataset.

Auto-discovers the latest numbered pipeline stage that still holds the
``mcqs_with_answers.json`` / ``mcqs_without_answers.json`` pair (the
bidi-isolated stage 14 at the time of writing), concatenates them into
a single list, re-numbers ``id`` contiguously, and writes:

  data/!-final/
  ├── mcqs.json         — full text incl. bidi-isolation marks (matches
  │                       what the web app uses; render-correct in any
  │                       bidi-aware viewer)
  └── mcqs_clean.json   — same content with all Unicode bidi formatting
                          chars stripped. Easier to grep / tokenize /
                          read in plain editors.

The bidi chars removed for the clean copy:
  U+200E LRM, U+200F RLM,
  U+202A–U+202E (embeddings & overrides),
  U+2066–U+2069 (isolates).
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DST_DIR = DATA_DIR / "!-final"
DST_FILE = DST_DIR / "mcqs.json"          # canonical, clean (no bidi marks)
DST_BIDI_FILE = DST_DIR / "mcqs_bidi.json"  # display-ready, with bidi marks

WITH_ANSWERS = "mcqs_with_answers.json"
WITHOUT_ANSWERS = "mcqs_without_answers.json"

STAGE_RE = re.compile(r"^(\d+)-")

# All Unicode bidi formatting characters — fully stripped from ``mcqs.json``
# so downstream consumers (LLM prompts, tokenizers, training pipelines)
# see the raw text without any invisible direction marks. Display tools
# that need correct visual ordering should load ``mcqs_bidi.json``.
#
# Stripped:
#   U+200E LRM, U+200F RLM       directional marks
#   U+202A..U+202E               directional embeddings & overrides
#   U+2066..U+2069               directional isolates (LRI/RLI/FSI/PDI)
_BIDI_CHARS = "‎‏‪‫‬‭‮⁦⁧⁨⁩"
_STRIP_BIDI = str.maketrans("", "", _BIDI_CHARS)


def strip_bidi(value):
    """Recursively strip bidi-formatting chars from strings inside dicts/lists."""
    if isinstance(value, str):
        return value.translate(_STRIP_BIDI)
    if isinstance(value, dict):
        return {k: strip_bidi(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_bidi(v) for v in value]
    return value


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

    # 1. mcqs.json — canonical, CLEAN (no bidi marks). Easier to read in
    #    Jupyter / editors, easier to grep / tokenize / use downstream.
    clean = [strip_bidi(item) for item in combined]
    with open(DST_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=4)

    # 2. mcqs_bidi.json — display-ready, with bidi-isolation marks
    #    (LRI/PDI). Used by the web preview / annotator. Renders correctly
    #    in any bidi-aware viewer even when the host context is LTR.
    with open(DST_BIDI_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=4)

    answered = sum(1 for x in combined if x.get("correct_option") is not None)
    unanswered = len(combined) - answered

    # How many bidi chars stripped?
    def char_count(items):
        total = 0
        for it in items:
            strings = [it.get("question") or "", it.get("correct_option") or ""]
            opts = it.get("options")
            if isinstance(opts, dict):
                strings.extend(v for v in opts.values() if isinstance(v, str))
            for s in strings:
                if isinstance(s, str):
                    for c in _BIDI_CHARS:
                        total += s.count(c)
        return total
    stripped = char_count(combined)

    print(f"with_answers rows:    {len(with_data)}")
    print(f"without_answers rows: {len(without_data)}")
    print(f"combined total:       {len(combined)}")
    print(f"  answered:           {answered}")
    print(f"  unanswered:         {unanswered}")
    print()
    print(f"Wrote:")
    print(f"  {DST_FILE}        (clean — bidi-formatting chars removed)")
    print(f"  {DST_BIDI_FILE}   (with bidi marks — {stripped} formatting chars)")


if __name__ == "__main__":
    main()
