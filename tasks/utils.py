"""Helpers for the UrduMMLU lm-evaluation-harness task.

Referenced from urdu_mmlu.yaml via lm-eval's ``!function`` tag.

The scoring rule is deliberately narrow. The prompt demands a two-line
"Answer key: X / Answer text: ..." response, and both gold and prediction are
reduced to a single answer-key letter before comparison. Anything that does not
yield a letter compares unequal and is therefore counted wrong, which matches
the all-item convention used for the zero-shot results (see the metric note in
src/analysis/eval.py).
"""

from __future__ import annotations

import re

VALID_KEYS = ("A", "B", "C", "D")

# "Answer key: D", "answer key - D", or a bare leading letter.
_KEY_RE = re.compile(r"answer\s*key\s*[:\-]?\s*\(?\s*([ABCD])\b", re.IGNORECASE)
_LEAD_RE = re.compile(r"^\W*([ABCD])\b")


def _parse_answer_key(text: str) -> str | None:
    """Reduce a gold target or a model continuation to one of A-D, or None."""
    if not text:
        return None
    text = str(text).strip()
    m = _KEY_RE.search(text) or _LEAD_RE.match(text)
    return m.group(1).upper() if m else None


def doc_to_text(doc: dict) -> str:
    options = doc["options"]
    return (
        f"Subject: {doc['domain']} – {doc['subdomain']} | Level: {doc['level']}\n\n"
        f"Question: {doc['question']}\n\n"
        f"A) {options['A']}\n"
        f"B) {options['B']}\n"
        f"C) {options['C']}\n"
        f"D) {options['D']}\n\n"
        "Answer key:"
    )


def doc_to_target(doc: dict) -> str:
    key = doc["correct_key"]
    answer_text = doc["options"][key]
    return f"{key}\nAnswer text: {answer_text}"


def exact_match(items):
    """Pass (gold, pred) pairs through to the aggregation step."""
    return items


def agg_exact_match(items) -> float:
    if not items:
        return 0.0
    correct = 0
    for gold, pred in items:
        gold_key = _parse_answer_key(gold)
        pred_key = _parse_answer_key(pred)
        if gold_key is not None and gold_key == pred_key:
            correct += 1
    return correct / len(items)
