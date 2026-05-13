#!/usr/bin/env python3
"""Correlation / fuzzy deduplication.

Two stages, both deterministic, no ML dependencies:

  **Stage A — canonical-key exact match.**
    For every row build a fingerprint:
      ``normalize(question) + '‖' + '|'.join(sorted(normalize(o)) for o in options)``
    Rows sharing a key are merged (whitespace, punctuation, diacritic and
    option-order variations all collapse here).

  **Stage B — word-Jaccard fuzzy match.**
    For each row tokenize the normalized question on whitespace and look
    up candidate near-duplicates via an inverted index that skips
    stop-tokens (tokens appearing in more than ``STOP_FREQ`` rows). For
    each candidate pair compute Jaccard = |A ∩ B| / |A ∪ B| and keep
    pairs with Jaccard ≥ ``JACCARD_THRESHOLD``. Confirmed pairs form
    connected components which are merged as a group.

Merge / drop policy (matches step 9 ``comparison_deduplication``):

  - Singletons pass through with ``source`` / ``source_url`` wrapped in
    1-element lists (already the case after step 9).
  - Groups whose ``correct_option`` agrees (after normalization) are
    collapsed; the row with the smallest ``id`` wins and merged
    ``source`` / ``source_url`` lists deduplicate parallel entries.
  - Groups where ``correct_option`` disagrees are **dropped entirely**.

Reads ``data/12-blanks-normalized/*.json`` and writes to
``data/13-correlation-deduplicated/*.json``.
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "12-blanks-normalized"
DST_DIR = REPO_ROOT / "data" / "13-correlation-deduplicated"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json"]

JACCARD_THRESHOLD = 0.90
OPTION_JACCARD_THRESHOLD = 0.50
MIN_TOKENS_FOR_FUZZY = 4
STOP_FREQ = 200  # tokens occurring in > this many rows are treated as stop-words

# Arabic / Urdu combining diacritics + Arabic tatweel + RLM + most punctuation
DIACRITICS = re.compile(r"[ً-ٰٟؐ-ؚـ]")
PUNCT = re.compile(
    r"[‏‎,،.۔?؟!:;\"'“”‘’()\[\]{}<>—–\-_/\\|]"
)


def normalize_text(text: str) -> str:
    """Aggressive normalization for fingerprinting / fuzzy matching."""
    if not isinstance(text, str):
        return ""
    text = DIACRITICS.sub("", text)
    text = PUNCT.sub(" ", text)
    text = text.lower()
    text = " ".join(text.split())
    return text


def canonical_key(item):
    q = normalize_text(item.get("question", ""))
    opts = item.get("options") or {}
    if isinstance(opts, dict):
        opt_norms = sorted(normalize_text(v) for v in opts.values() if isinstance(v, str))
    else:
        opt_norms = []
    return q + "‖" + "|".join(opt_norms)


def normalized_correct_option(item):
    co = item.get("correct_option")
    if co is None:
        return None
    return normalize_text(co)


def to_list(v):
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def merge_sources(items):
    names, urls = [], []
    for it in items:
        item_names = to_list(it.get("source"))
        item_urls = to_list(it.get("source_url"))
        for i, src in enumerate(item_names):
            if not src or src in names:
                continue
            names.append(src)
            urls.append(item_urls[i] if i < len(item_urls) else "")
    return names, urls


def merge_group(items, check_answer):
    """Return merged row, or None to signal 'drop this disputed group'."""
    if check_answer:
        answers = {normalized_correct_option(it) for it in items if it.get("correct_option")}
        if len(answers) > 1:
            return None  # disputed
    items_sorted = sorted(items, key=lambda x: x.get("id", 0))
    merged = dict(items_sorted[0])
    names, urls = merge_sources(items_sorted)
    merged["source"] = names
    merged["source_url"] = urls
    return merged


# ---------------- Stage A ----------------

def stage_a(data, check_answer):
    groups = defaultdict(list)
    for item in data:
        groups[canonical_key(item)].append(item)

    out, dropped_disputed_rows, merged_groups, dropped_groups = [], 0, 0, 0
    for items in groups.values():
        if len(items) == 1:
            out.append(items[0])
            continue
        merged = merge_group(items, check_answer)
        if merged is None:
            dropped_groups += 1
            dropped_disputed_rows += len(items)
        else:
            out.append(merged)
            merged_groups += 1

    return out, {
        "stage_a_merged_groups": merged_groups,
        "stage_a_dropped_groups": dropped_groups,
        "stage_a_dropped_rows": dropped_disputed_rows,
    }


# ---------------- Stage B ----------------

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[rx] = ry


def option_signatures(item):
    """Compute a set with one signature per option value.

    Each signature is the normalized option string with all whitespace
    removed, so trivial differences like ``300°C`` vs ``300 °C`` collapse
    to a single shared signature. Comparing two questions' option-sigs by
    Jaccard gives a robust "do these two MCQs have the same answer
    choices?" measure.
    """
    out = set()
    opts = item.get("options") or {}
    if isinstance(opts, dict):
        for v in opts.values():
            if isinstance(v, str):
                sig = normalize_text(v).replace(" ", "")
                if sig:
                    out.add(sig)
    return out


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def stage_b(data, check_answer, threshold=JACCARD_THRESHOLD,
            option_threshold=OPTION_JACCARD_THRESHOLD):
    tokens = []
    opt_sigs = []
    for item in data:
        tokens.append(set(normalize_text(item.get("question", "")).split()))
        opt_sigs.append(option_signatures(item))

    # Inverted index, skip stop-tokens
    inverted = defaultdict(list)
    for rid, toks in enumerate(tokens):
        for t in toks:
            inverted[t].append(rid)

    stop = {t for t, rows in inverted.items() if len(rows) > STOP_FREQ}

    # Candidate pair generation via shared rare tokens
    candidates = set()
    for rid, toks in enumerate(tokens):
        if len(toks) < MIN_TOKENS_FOR_FUZZY:
            continue
        rare = toks - stop
        seen = set()
        for t in rare:
            for other in inverted[t]:
                if other == rid or other in seen:
                    continue
                seen.add(other)
                if len(tokens[other]) < MIN_TOKENS_FOR_FUZZY:
                    continue
                pair = (rid, other) if rid < other else (other, rid)
                candidates.add(pair)

    # Confirm candidates: require BOTH question-Jaccard ≥ threshold AND
    # option-set-Jaccard ≥ option_threshold (the latter catches the
    # "same question wording, totally different option values" false positive).
    uf = UnionFind(len(data))
    confirmed_pairs = 0
    rejected_by_options = 0
    for a, b in candidates:
        if jaccard(tokens[a], tokens[b]) < threshold:
            continue
        if jaccard(opt_sigs[a], opt_sigs[b]) < option_threshold:
            rejected_by_options += 1
            continue
        uf.union(a, b)
        confirmed_pairs += 1

    # Build groups from connected components
    groups = defaultdict(list)
    for i in range(len(data)):
        groups[uf.find(i)].append(i)

    out, dropped_rows, merged_groups, dropped_groups = [], 0, 0, 0
    for ids in groups.values():
        items = [data[i] for i in ids]
        if len(items) == 1:
            out.append(items[0])
            continue
        merged = merge_group(items, check_answer)
        if merged is None:
            dropped_groups += 1
            dropped_rows += len(items)
        else:
            out.append(merged)
            merged_groups += 1

    return out, {
        "stage_b_confirmed_pairs": confirmed_pairs,
        "stage_b_rejected_by_options": rejected_by_options,
        "stage_b_merged_groups": merged_groups,
        "stage_b_dropped_groups": dropped_groups,
        "stage_b_dropped_rows": dropped_rows,
        "stage_b_stop_tokens": len(stop),
    }


def process_file(src: Path, dst: Path, check_answer: bool) -> dict:
    t0 = time.time()
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = {"input_rows": len(data)}

    after_a, stats_a = stage_a(data, check_answer=check_answer)
    stats["after_stage_a"] = len(after_a)
    stats.update(stats_a)

    after_b, stats_b = stage_b(after_a, check_answer=check_answer)
    stats["output_rows"] = len(after_b)
    stats.update(stats_b)
    stats["seconds"] = round(time.time() - t0, 1)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(after_b, f, ensure_ascii=False, indent=4)

    return stats


def main() -> None:
    print(f"Source:      {SRC_DIR}")
    print(f"Destination: {DST_DIR}")
    print(f"Jaccard threshold: {JACCARD_THRESHOLD}")
    print()

    for name in FILES:
        src = SRC_DIR / name
        dst = DST_DIR / name
        if not src.exists():
            print(f"Skip (not found): {src}")
            continue

        check = "without_answers" not in name
        stats = process_file(src, dst, check_answer=check)
        print(f"{name}  (check_answer={check}, {stats['seconds']}s)")
        print(f"  input rows:                  {stats['input_rows']}")
        print(f"  ── stage A (canonical key) ──")
        print(f"  merged groups:               {stats['stage_a_merged_groups']}")
        print(f"  dropped disputed groups:     {stats['stage_a_dropped_groups']} "
              f"({stats['stage_a_dropped_rows']} rows)")
        print(f"  rows after stage A:          {stats['after_stage_a']}")
        print(f"  ── stage B (Q-Jaccard ≥ {JACCARD_THRESHOLD}, opt-Jaccard ≥ {OPTION_JACCARD_THRESHOLD}) ──")
        print(f"  stop tokens skipped:         {stats['stage_b_stop_tokens']}")
        print(f"  confirmed pairs:             {stats['stage_b_confirmed_pairs']}")
        print(f"  rejected by option mismatch: {stats['stage_b_rejected_by_options']}")
        print(f"  merged groups:               {stats['stage_b_merged_groups']}")
        print(f"  dropped disputed groups:     {stats['stage_b_dropped_groups']} "
              f"({stats['stage_b_dropped_rows']} rows)")
        print(f"  output rows:                 {stats['output_rows']}")
        print()


if __name__ == "__main__":
    main()
