#!/usr/bin/env python3
"""Accuracy evaluation across all model predictions.

Walks ``output/<lang>/<model>/predictions.json`` and reports per-model
accuracy using a robust answer parser that tolerates the common output
formats models produce:

  * Intended format:  ``Answer key: X``
  * Common variants:  ``Answer: X``, ``The answer is X``, ``Final: X``
  * Option-prefix:    ``X)``, ``X.``, ``X:``  (at line start or after \\n)
  * Markdown bold:    ``**X**`` / ``__X__``
  * Last-resort:      first standalone A/B/C/D letter in the response

Usage:
    python src/analysis/eval.py                  # scan all langs / models
    python src/analysis/eval.py --lang ur
    python src/analysis/eval.py --model claude-haiku-4-5
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "output"

# Strict patterns checked in priority order. The first match wins.
PATTERNS = [
    # Intended format (and a few common variants of "Answer key:")
    re.compile(r"Answer\s*key\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bFinal\s*Answer\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bAnswer\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bThe\s*answer\s*is\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bcorrect\s*answer\s*is\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    # Boxed (LaTeX-style chain-of-thought finals)
    re.compile(r"\\boxed\{\s*\(?\s*([ABCD])\s*\)?\s*\}", re.IGNORECASE),
    # Markdown bold/italic wrapping just the letter
    re.compile(r"(?:^|\s)\*\*\s*([ABCD])\s*\*\*", re.IGNORECASE),
    re.compile(r"(?:^|\s)__\s*([ABCD])\s*__", re.IGNORECASE),
    # Option-prefix style at the start of a line (e.g. "D) لاہور")
    re.compile(r"(?:^|\n)\s*\(?\s*([ABCD])\s*[\)\.\:]\s*", re.IGNORECASE),
    # Last resort: any standalone A/B/C/D bounded by non-letter chars
    re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])", re.IGNORECASE),
]


def parse_key(pred: str | None) -> str | None:
    if not pred:
        return None
    text = str(pred).strip()
    if not text or text.startswith(("ERROR", "CONNECTION_FAILED")):
        return None
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).upper()
    return None


def evaluate(records: list[dict]) -> dict:
    dom: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    lvl: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = [0, 0]
    err = 0
    parse_fail = 0

    for r in records:
        pred = r.get("prediction") or ""
        if str(pred).startswith(("ERROR", "CONNECTION_FAILED")):
            err += 1
            continue
        key = parse_key(pred)
        if key is None:
            parse_fail += 1
            continue
        ok = key == r.get("correct_key")
        total[0] += ok
        total[1] += 1
        dom[r.get("domain", "?")][0] += ok
        dom[r.get("domain", "?")][1] += 1
        lvl[r.get("level", "?")][0] += ok
        lvl[r.get("level", "?")][1] += 1
        sub[r.get("subdomain", "?")][0] += ok
        sub[r.get("subdomain", "?")][1] += 1

    return {
        "n": len(records),
        "parseable": total[1],
        "parse_fail": parse_fail,
        "errors": err,
        "correct": total[0],
        "accuracy": total[0] / total[1] if total[1] else 0,
        "by_domain": {d: (c, t, c / t if t else 0) for d, (c, t) in dom.items()},
        "by_level": {L: (c, t, c / t if t else 0) for L, (c, t) in lvl.items()},
        "by_subdomain": {s: (c, t, c / t if t else 0) for s, (c, t) in sub.items()},
    }


def fmt_row(name: str, stats: dict) -> str:
    return (
        f"  {name:<32} "
        f"acc={stats['accuracy']*100:>5.2f}%  "
        f"({stats['correct']:>6,}/{stats['parseable']:<6,})  "
        f"parse_fail={stats['parse_fail']:>5}  err={stats['errors']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", help="Restrict to a single language (e.g. ur)")
    parser.add_argument("--model", help="Restrict to a model name substring")
    args = parser.parse_args()

    langs = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())
    for lang in langs:
        if args.lang and lang != args.lang:
            continue
        print(f"\n[{lang}]")
        models = sorted(OUTPUT_DIR.glob(f"{lang}/*/predictions.json"))
        for path in models:
            model = path.parent.name
            if args.model and args.model not in model:
                continue
            records = json.load(open(path, encoding="utf-8"))
            stats = evaluate(records)
            print(fmt_row(model, stats))
            for dn, (c, t, a) in sorted(stats["by_domain"].items(), key=lambda x: -x[1][1]):
                print(f"      {dn:<22} {c:>5}/{t:<6} {a*100:>5.1f}%")


if __name__ == "__main__":
    main()
