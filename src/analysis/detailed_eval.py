#!/usr/bin/env python3
"""Detailed accuracy evaluation with domain breakdown and CSV export.

Walks ``output/<lang>/<model>/predictions.json``, prints a per-model summary
with domain-wise accuracy to stdout, and writes a CSV with one row per
model × language containing total and per-domain accuracy.

Answer parsing mirrors eval.py (regex patterns + option-text fallback).

Usage:
    python src/analysis/detailed_eval.py
    python src/analysis/detailed_eval.py --lang ur
    python src/analysis/detailed_eval.py --model claude-haiku-4-5
    python src/analysis/detailed_eval.py --output results/detailed.csv
    python src/analysis/detailed_eval.py --exclude-domain Humanities
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_CSV = REPO_ROOT / "output" / "detailed_accuracy.csv"

DOMAINS = ["Humanities", "Social Sciences", "STEM", "Profession", "Other"]

# ── answer-key parser ─────────────────────────────────────────────────────────

PATTERNS = [
    re.compile(r"Answer\s*key\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bFinal\s*Answer\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bAnswer\s*[:\-]\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bThe\s*answer\s*is\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\bcorrect\s*answer\s*is\s*\(?\s*([ABCD])\s*\)?", re.IGNORECASE),
    re.compile(r"\\boxed\{\s*\(?\s*([ABCD])\s*\)?\s*\}", re.IGNORECASE),
    re.compile(r"(?:^|\s)\*\*\s*([ABCD])\s*\*\*", re.IGNORECASE),
    re.compile(r"(?:^|\s)__\s*([ABCD])\s*__", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*\(?\s*([ABCD])\s*[\)\.\:]\s*", re.IGNORECASE),
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
    return " ".join(str(s).split())


def parse_key_from_options(pred: str | None, options: dict) -> str | None:
    if not pred or not options:
        return None
    pred_norm = _norm(pred)
    if not pred_norm:
        return None
    matches = [k for k, v in options.items() if _norm(v) == pred_norm]
    if len(matches) == 1:
        return matches[0].upper()
    if not matches:
        matches = [k for k, v in options.items() if pred_norm in _norm(v) or _norm(v) in pred_norm]
        if len(matches) == 1:
            return matches[0].upper()
    return None


# ── evaluation ────────────────────────────────────────────────────────────────

def evaluate(
    records: list[dict],
    exclude_domains: set[str] | None = None,
    exclude_subdomains: set[str] | None = None,
) -> dict:
    exclude_domains = exclude_domains or set()
    exclude_subdomains = exclude_subdomains or set()

    dom: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = [0, 0]
    err = parse_fail = text_match = excluded = 0

    for r in records:
        if r.get("domain") in exclude_domains or r.get("subdomain") in exclude_subdomains:
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
        ok = int(key == r.get("correct_key"))
        total[0] += ok
        total[1] += 1
        dom[r.get("domain", "?")][0] += ok
        dom[r.get("domain", "?")][1] += 1
        sub[r.get("subdomain", "?")][0] += ok
        sub[r.get("subdomain", "?")][1] += 1

    return {
        "n": len(records),
        "excluded": excluded,
        "correct": total[0],
        "parseable": total[1],
        "parse_fail": parse_fail,
        "text_match": text_match,
        "errors": err,
        "accuracy": total[0] / total[1] if total[1] else 0.0,
        "by_domain": {d: (c, t, c / t if t else 0.0) for d, (c, t) in dom.items()},
        "by_subdomain": {s: (c, t, c / t if t else 0.0) for s, (c, t) in sub.items()},
    }


# ── terminal formatting ───────────────────────────────────────────────────────

_W = 44  # model name column width


def print_model_block(lang: str, model: str, stats: dict) -> None:
    acc = stats["accuracy"] * 100
    c, t = stats["correct"], stats["parseable"]
    pf, tm, err = stats["parse_fail"], stats["text_match"], stats["errors"]

    print(f"  {model:<{_W}} acc={acc:>6.2f}%  ({c:>7,}/{t:<7,})  "
          f"parse_fail={pf:>5}  text_match={tm:>4}  err={err}")

    # domain rows, sorted by question count descending
    for domain in DOMAINS:
        if domain not in stats["by_domain"]:
            continue
        dc, dt, da = stats["by_domain"][domain]
        print(f"    {domain:<20}  {dc:>6,}/{dt:<6,}  {da*100:>6.2f}%")


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _csv_fieldnames() -> list[str]:
    base = ["model", "language", "total_correct", "total_questions", "total_accuracy",
            "parse_fail", "text_match", "errors"]
    for d in DOMAINS:
        col = d.replace(" ", "_")
        base += [f"{col}_correct", f"{col}_questions", f"{col}_accuracy"]
    return base


def stats_to_csv_row(model: str, lang: str, stats: dict) -> dict:
    row: dict = {
        "model": model,
        "language": lang,
        "total_correct": stats["correct"],
        "total_questions": stats["parseable"],
        "total_accuracy": round(stats["accuracy"] * 100, 2),
        "parse_fail": stats["parse_fail"],
        "text_match": stats["text_match"],
        "errors": stats["errors"],
    }
    for d in DOMAINS:
        col = d.replace(" ", "_")
        dc, dt, da = stats["by_domain"].get(d, (0, 0, 0.0))
        row[f"{col}_correct"] = dc
        row[f"{col}_questions"] = dt
        row[f"{col}_accuracy"] = round(da * 100, 2)
    return row


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", help="Restrict to one language folder (e.g. ur, en)")
    parser.add_argument("--model", help="Restrict to models whose name contains this substring")
    parser.add_argument("--exclude-domain", action="append", default=[],
                        help="Domain to exclude (repeatable)")
    parser.add_argument("--exclude-subdomain", action="append", default=[],
                        help="Subdomain to exclude (repeatable)")
    parser.add_argument("--output", default=str(DEFAULT_CSV),
                        help=f"CSV output path (default: {DEFAULT_CSV})")
    args = parser.parse_args()

    exclude_domains = set(args.exclude_domain)
    exclude_subdomains = set(args.exclude_subdomain)

    csv_rows: list[dict] = []

    langs = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())
    for lang in langs:
        if args.lang and lang != args.lang:
            continue
        paths = sorted(OUTPUT_DIR.glob(f"{lang}/*/predictions.json"))
        if not paths:
            continue
        print(f"\n[{lang}]")
        for path in paths:
            model = path.parent.name
            if args.model and args.model not in model:
                continue
            records = json.loads(path.read_text(encoding="utf-8"))
            stats = evaluate(records, exclude_domains=exclude_domains,
                             exclude_subdomains=exclude_subdomains)
            print_model_block(lang, model, stats)
            csv_rows.append(stats_to_csv_row(model, lang, stats))

    # write CSV
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_csv_fieldnames())
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nCSV saved → {out}  ({len(csv_rows)} rows)")


if __name__ == "__main__":
    main()
