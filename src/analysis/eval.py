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
  * Text fallback:    prediction text matched against option values (for
                      models that output the answer text instead of a key)

Usage:
    python src/analysis/eval.py                  # scan all langs / models
    python src/analysis/eval.py --lang ur
    python src/analysis/eval.py --model claude-haiku-4-5
    python src/analysis/eval.py --exclude-domain Humanities --exclude-domain Other
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


def _norm(s: str) -> str:
    """Normalize text for option-text matching: strip and collapse whitespace."""
    return " ".join(str(s).split())


def parse_key_from_options(pred: str | None, options: dict) -> str | None:
    """Fallback: match prediction text against option values.

    Returns the option key whose value matches the prediction, or None if
    there is no match or the match is ambiguous (multiple options match).
    """
    if not pred or not options:
        return None
    pred_norm = _norm(pred)
    if not pred_norm:
        return None
    matches = [
        letter for letter, text in options.items()
        if _norm(text) == pred_norm
    ]
    if len(matches) == 1:
        return matches[0].upper()
    # Looser fallback: prediction is a substring of an option or vice versa
    if not matches:
        matches = [
            letter for letter, text in options.items()
            if pred_norm in _norm(text) or _norm(text) in pred_norm
        ]
        if len(matches) == 1:
            return matches[0].upper()
    return None


def evaluate(
    records: list[dict],
    exclude_domains: set[str] | None = None,
    exclude_subdomains: set[str] | None = None,
) -> dict:
    exclude_domains = exclude_domains or set()
    exclude_subdomains = exclude_subdomains or set()

    dom: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    lvl: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = [0, 0]
    err = 0
    parse_fail = 0
    text_match = 0
    excluded = 0

    for r in records:
        if (
            r.get("domain") in exclude_domains
            or r.get("subdomain") in exclude_subdomains
        ):
            excluded += 1
            continue
        pred = r.get("prediction") or ""
        if str(pred).startswith(("ERROR", "CONNECTION_FAILED")):
            err += 1
            continue
        key = parse_key(pred)
        if key is None:
            key = parse_key_from_options(pred, r.get("options") or {})
            if key is None:
                parse_fail += 1
                continue
            text_match += 1
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
        "excluded": excluded,
        "parseable": total[1],
        "parse_fail": parse_fail,
        "text_match": text_match,
        "errors": err,
        "correct": total[0],
        "accuracy": total[0] / total[1] if total[1] else 0,
        "by_domain": {d: (c, t, c / t if t else 0) for d, (c, t) in dom.items()},
        "by_level": {L: (c, t, c / t if t else 0) for L, (c, t) in lvl.items()},
        "by_subdomain": {s: (c, t, c / t if t else 0) for s, (c, t) in sub.items()},
    }


def fmt_row(name: str, stats: dict, name_width: int = 42) -> str:
    return (
        f"  {name:<{name_width}} "
        f"acc={stats['accuracy'] * 100:>6.2f}%  "
        f"({stats['correct']:>7,} / {stats['parseable']:>7,})  "
        f"parse_fail={stats['parse_fail']:>5}  text_match={stats['text_match']:>5}  err={stats['errors']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", help="Restrict to a single language (e.g. ur)")
    parser.add_argument("--model", help="Restrict to a model name substring")
    parser.add_argument(
        "--exclude-domain",
        action="append",
        default=[],
        help="Domain to exclude from accuracy (repeatable). e.g. --exclude-domain Humanities",
    )
    parser.add_argument(
        "--exclude-subdomain",
        action="append",
        default=[],
        help="Subdomain to exclude from accuracy (repeatable).",
    )
    parser.add_argument(
        "-d",
        "--detailed",
        action="store_true",
        help="Show per-domain breakdown beneath each model row.",
    )
    args = parser.parse_args()
    exclude_domains = set(args.exclude_domain)
    exclude_subdomains = set(args.exclude_subdomain)
    if exclude_domains or exclude_subdomains:
        bits = []
        if exclude_domains:
            bits.append(f"domains={sorted(exclude_domains)}")
        if exclude_subdomains:
            bits.append(f"subdomains={sorted(exclude_subdomains)}")
        print(f"Excluding: {', '.join(bits)}")

    langs = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())
    for lang in langs:
        if args.lang and lang != args.lang:
            continue
        models = sorted(OUTPUT_DIR.glob(f"{lang}/*/predictions.json"))
        if not models:
            continue  # Skip non-language dirs (e.g. ``lm_eval/``).
        print(f"\n[{lang}]")
        for path in models:
            model = path.parent.name
            if args.model and args.model not in model:
                continue
            records = json.load(open(path, encoding="utf-8"))
            stats = evaluate(
                records,
                exclude_domains=exclude_domains,
                exclude_subdomains=exclude_subdomains,
            )
            print(fmt_row(model, stats))
            if args.detailed:
                for dn, (c, t, a) in sorted(
                    stats["by_domain"].items(), key=lambda x: -x[1][1]
                ):
                    print(f"      {dn:<22} {c:>5}/{t:<6} {a * 100:>5.1f}%")


if __name__ == "__main__":
    main()
