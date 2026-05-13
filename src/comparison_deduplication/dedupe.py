#!/usr/bin/env python3
"""Exact-match deduplication on question text.

Groups rows by exact question text, then:

  - **Singletons** are kept as-is (with `source` / `source_url` wrapped in
    a list for schema consistency with merged rows).
  - **Duplicate groups where all rows agree on `correct_option`** are
    collapsed to a single row; the first row is kept and the merged row's
    `source` / `source_url` become deduplicated lists preserving every
    upstream origin.
  - **Duplicate groups where rows disagree on `correct_option`** are
    dropped entirely — these 100-odd "disputed" groups carry irreducible
    label noise that's worse than the cost of losing the row.

`mcqs_without_answers.json` has no `correct_option`, so every duplicate
group is merged (no "disputed" branch).

A future "correlation deduplication" step is expected to catch
near-duplicates (typos, whitespace variation, option-shuffled twins)
that exact-match cannot.

Reads ``data/8-option-prefix-stripped/*.json`` and writes to
``data/9-comparison-deduplicated/*.json``.
"""

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "8-option-prefix-stripped"
DST_DIR = REPO_ROOT / "data" / "9-comparison-deduplicated"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]


def to_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def merged_sources(items):
    """Deduplicated parallel lists of source / source_url across `items`."""
    names, urls = [], []
    for it in items:
        for src in to_list(it.get("source")):
            if src and src not in names:
                names.append(src)
                # Pair the URL from the same item; fall back to '' if missing
                paired_urls = to_list(it.get("source_url"))
                urls.append(paired_urls[0] if paired_urls else "")
    return names, urls


def normalize_singleton(item):
    """Wrap source/source_url as lists to match merged-row schema."""
    out = dict(item)
    out["source"] = to_list(out.get("source"))
    out["source_url"] = to_list(out.get("source_url"))
    return out


def dedupe(data, check_answer):
    groups = defaultdict(list)
    no_question = []
    for item in data:
        q = (item.get("question") or "").strip()
        if not q:
            no_question.append(item)
            continue
        groups[q].append(item)

    out = list(no_question)
    stats = {
        "input_rows": len(data),
        "unique_questions": len(groups),
        "singletons": 0,
        "merged_groups": 0,
        "dropped_disputed_groups": 0,
        "dropped_disputed_rows": 0,
    }

    for q, items in groups.items():
        if len(items) == 1:
            stats["singletons"] += 1
            out.append(normalize_singleton(items[0]))
            continue

        if check_answer:
            answers = {it.get("correct_option") for it in items if it.get("correct_option") is not None}
            if len(answers) > 1:
                stats["dropped_disputed_groups"] += 1
                stats["dropped_disputed_rows"] += len(items)
                continue

        merged = dict(items[0])
        names, urls = merged_sources(items)
        merged["source"] = names
        merged["source_url"] = urls
        out.append(merged)
        stats["merged_groups"] += 1

    stats["output_rows"] = len(out)
    return out, stats


def process_file(src: Path, dst: Path, check_answer: bool) -> dict:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    out, stats = dedupe(data, check_answer=check_answer)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
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

        check = "without_answers" not in name
        stats = process_file(src, dst, check_answer=check)
        print(f"{name}  (check_answer={check})")
        print(f"  input rows:              {stats['input_rows']}")
        print(f"  unique questions:        {stats['unique_questions']}")
        print(f"  singletons:              {stats['singletons']}")
        print(f"  merged duplicate groups: {stats['merged_groups']}")
        print(f"  dropped disputed groups: {stats['dropped_disputed_groups']} "
              f"({stats['dropped_disputed_rows']} rows)")
        print(f"  output rows:             {stats['output_rows']}")
        print()


if __name__ == "__main__":
    main()
