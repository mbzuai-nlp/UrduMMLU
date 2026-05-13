#!/usr/bin/env python3
"""Normalize character forms across all string fields.

Two passes:

1. **NFKC normalization** — folds Arabic presentation forms (ligatures like
   ``ﷲ`` → ``الله``), fullwidth variants, and other compatibility characters
   into canonical base sequences. Needed for downstream tokenization and
   exact-match retrieval.

2. **Arabic → Urdu letter substitution** — visually-identical Arabic
   codepoints get re-mapped to their Urdu counterparts:

   ======  ===========================  ======  =========================
   From    Name                         To      Name
   ======  ===========================  ======  =========================
   U+064A  Arabic Yeh ``ي``             U+06CC  Farsi Yeh ``ی``
   U+0649  Arabic Alef Maksura ``ى``    U+06CC  Farsi Yeh ``ی``
   U+0643  Arabic Kaf ``ك``             U+06A9  Keheh ``ک``
   U+0647  Arabic Heh ``ه``             U+06C1  Heh Goal ``ہ``
   ======  ===========================  ======  =========================

A final NFC pass re-composes diacritics.

Reads ``data/6-schema-canonicalized/*.json`` and writes to
``data/7-character-normalized/*.json``.
"""

import json
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "6-schema-canonicalized"
DST_DIR = REPO_ROOT / "data" / "7-character-normalized"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

ARABIC_TO_URDU = str.maketrans({
    "ي": "ی",  # ي → ی
    "ى": "ی",  # ى → ی
    "ك": "ک",  # ك → ک
    "ه": "ہ",  # ه → ہ
})


def normalize(text: str, stats: dict) -> str:
    if not isinstance(text, str) or not text:
        return text

    original = text
    after_nfkc = unicodedata.normalize("NFKC", text)
    if after_nfkc != text:
        stats["nfkc"] += 1

    mapped = after_nfkc.translate(ARABIC_TO_URDU)
    if mapped != after_nfkc:
        stats["arabic_to_urdu"] += 1

    final = unicodedata.normalize("NFC", mapped)

    if final != original:
        stats["any_change"] += 1
    return final


def fix_item(item: dict, stats: dict) -> dict:
    q = item.get("question", "")
    item["question"] = normalize(q, stats["question"])

    options = item.get("options")
    if isinstance(options, dict):
        for key, value in options.items():
            if isinstance(value, str):
                options[key] = normalize(value, stats["option"])
    elif isinstance(options, list):
        for i, value in enumerate(options):
            if isinstance(value, str):
                options[i] = normalize(value, stats["option"])

    co = item.get("correct_option")
    if isinstance(co, str):
        item["correct_option"] = normalize(co, stats["correct_option"])

    return item


def empty_stats() -> dict:
    return {
        "question": {"any_change": 0, "nfkc": 0, "arabic_to_urdu": 0},
        "option": {"any_change": 0, "nfkc": 0, "arabic_to_urdu": 0},
        "correct_option": {"any_change": 0, "nfkc": 0, "arabic_to_urdu": 0},
    }


def process_file(src: Path, dst: Path) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = empty_stats()
    stats["total"] = len(data)
    for item in data:
        fix_item(item, stats)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return stats


def main() -> None:
    print(f"Source:      {SRC_DIR}")
    print(f"Destination: {DST_DIR}\n")

    for name in FILES:
        src = SRC_DIR / name
        dst = DST_DIR / name
        if not src.exists():
            print(f"Skip (not found): {src}")
            continue

        stats = process_file(src, dst)
        print(f"{name}  (total {stats['total']})")
        for field in ("question", "option", "correct_option"):
            s = stats[field]
            print(
                f"  {field:<16} any={s['any_change']:>5}  "
                f"nfkc={s['nfkc']:>5}  arabic→urdu={s['arabic_to_urdu']:>5}"
            )
        print()


if __name__ == "__main__":
    main()
