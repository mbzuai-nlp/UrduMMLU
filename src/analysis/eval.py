#!/usr/bin/env python3
"""Accuracy evaluation across all model predictions.

Walks ``output/<lang>/<model>/predictions.json`` and reports per-model
accuracy using a robust answer parser that tolerates the common output
formats models produce:

  * Intended format:  ``Answer key: X``
  * Common variants:  ``Answer: X``, ``The answer is X``, ``Final: X``
  * Urdu key letters: ``ا``/``ب``/``ج``/``د`` mapped to A/B/C/D (some Urdu LLMs
                      translate the option keys back into Urdu).
  * Option-prefix:    ``X)``, ``X.``, ``X:``  (at line start or after \\n)
  * Markdown bold:    ``**X**`` / ``__X__``
  * Last-resort:      first standalone A/B/C/D letter in the response
  * Text fallback:    ``Answer text: <value>`` matched against the option
                      dict, then the whole prediction matched against the
                      option dict as a final attempt (for models that
                      output the answer text instead of a key).

Usage:
    python src/analysis/eval.py                          # summary only
    python src/analysis/eval.py --lang ur
    python src/analysis/eval.py --model claude-haiku-4-5
    python src/analysis/eval.py --detailed               # + per-domain rows
    python src/analysis/eval.py --csv results.csv        # + CSV export
    python src/analysis/eval.py --exclude-domain Humanities --exclude-domain Other
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

# Fixed ordering for per-domain rows and CSV columns. Domains that exist
# in the data but aren't listed here are still tallied and printed after
# the canonical order.
DOMAINS = ["Humanities", "Social Sciences", "STEM", "Profession", "Other"]

# Predictions that don't start with these prefixes count as model errors,
# not parse failures (e.g. ``EMPTY_OUTPUT: finish_reason=length`` from
# reasoning models that ran out of token budget before producing text).
ERROR_PREFIXES = ("ERROR", "CONNECTION_FAILED", "EMPTY_OUTPUT")

# Urdu/Arabic answer letters used by some Urdu-tuned LLMs in place of A/B/C/D.
URDU_KEY_MAP = {
    "ا": "A", "أ": "A", "إ": "A", "آ": "A",
    "ب": "B",
    "ج": "C",
    "د": "D",
}
_URDU_KEYS = "".join(URDU_KEY_MAP.keys())
_KEY = rf"[ABCD{_URDU_KEYS}]"

# Strict patterns checked in priority order. The first match wins.
PATTERNS = [
    # Intended format (and a few common variants of "Answer key:")
    re.compile(rf"Answer\s*key\s*[:\-]\s*\(?\s*({_KEY})\s*\)?", re.IGNORECASE),
    re.compile(rf"\bFinal\s*Answer\s*[:\-]\s*\(?\s*({_KEY})\s*\)?", re.IGNORECASE),
    re.compile(rf"\bAnswer\s*[:\-]\s*\(?\s*({_KEY})\s*\)?", re.IGNORECASE),
    re.compile(rf"\bThe\s*answer\s*is\s*\(?\s*({_KEY})\s*\)?", re.IGNORECASE),
    re.compile(rf"\bcorrect\s*answer\s*is\s*\(?\s*({_KEY})\s*\)?", re.IGNORECASE),
    # Boxed (LaTeX-style chain-of-thought finals)
    re.compile(rf"\\boxed\{{\s*\(?\s*({_KEY})\s*\)?\s*\}}", re.IGNORECASE),
    # Markdown bold/italic wrapping just the letter
    re.compile(rf"(?:^|\s)\*\*\s*({_KEY})\s*\*\*", re.IGNORECASE),
    re.compile(rf"(?:^|\s)__\s*({_KEY})\s*__", re.IGNORECASE),
    # Option-prefix style at the start of a line (e.g. "D) لاہور" or "د) ...")
    re.compile(rf"(?:^|\n)\s*\(?\s*({_KEY})\s*[\)\.\:]\s*", re.IGNORECASE),
    # Last resort: any standalone A/B/C/D bounded by non-letter chars
    re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])", re.IGNORECASE),
    # Standalone Urdu key letter (e.g. a response that is just "د\n\n...").
    # Bounded by non-Arabic-letter chars so it doesn't fire inside words.
    re.compile(rf"(?:^|[\s\(\[\.,\:\;])([{_URDU_KEYS}])(?:[\s\)\.\,\:\;\-]|$)"),
]


def _is_empty_or_error(pred) -> bool:
    """Classify a prediction as a model-side error (not a parse failure)."""
    if pred is None:
        return True
    text = str(pred).strip()
    if not text:
        return True
    return text.startswith(ERROR_PREFIXES)


def parse_key(pred: str | None) -> str | None:
    if _is_empty_or_error(pred):
        return None
    text = str(pred).strip()
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            letter = m.group(1)
            return URDU_KEY_MAP.get(letter, letter.upper())
    return None


# Common Arabic ↔ Urdu character variants that render identically but
# differ in Unicode codepoint. Models trained primarily on Arabic data
# sometimes emit the Arabic codepoints when answering Urdu MCQs.
_AR_UR_TRANSLATE = str.maketrans({
    "ي": "ی",  # Arabic Yeh ي → Urdu Yeh ی
    "ى": "ی",  # Arabic Alef Maksura ى → Urdu Yeh ی
    "ك": "ک",  # Arabic Kaf ك → Urdu Kaf ک
    "ہ": "ہ",  # (Urdu Heh Goal — kept for reference)
    "ة": "ہ",  # Arabic Teh Marbuta ة → Urdu Heh ہ
    # Strip the Arabic tatweel / kashida — purely decorative joiner.
    "ـ": "",
})


def _norm(s: str) -> str:
    """Normalize text for option-text matching.

    Strips and collapses whitespace, and folds Arabic codepoints to their
    visually-identical Urdu counterparts so ``فارسى`` (Arabic Yaa) matches
    ``فارسی`` (Urdu Yeh).
    """
    s = str(s).translate(_AR_UR_TRANSLATE)
    return " ".join(s.split())


# Capture text after ``Answer text: ...`` (line-bounded). Models that
# obey the schema partially often produce this line without the matching
# ``Answer key:`` line, e.g. ``Answer text: 2.5 فیصد``.
_ANSWER_TEXT_RE = re.compile(
    r"Answer\s*text\s*[:\-]\s*(.+?)(?:\n|$)", re.IGNORECASE
)


def _extract_answer_text(pred: str) -> str | None:
    m = _ANSWER_TEXT_RE.search(pred)
    if not m:
        return None
    return m.group(1).strip()


def parse_key_from_options(pred: str | None, options: dict) -> str | None:
    """Fallback: match prediction text against option values.

    Two passes:
      1. If the prediction has an ``Answer text:`` line, match its value
         exactly (or as a 1:1 substring) against an option.
      2. Otherwise fall back to matching the whole prediction string.

    Returns the option key whose value matches, or ``None`` if there is no
    match or multiple options match ambiguously.
    """
    if not pred or not options:
        return None

    # Pass 1 — strip "Answer text:" prefix if present, match that.
    extracted = _extract_answer_text(pred)
    if extracted:
        key = _match_options(extracted, options)
        if key:
            return key

    # Pass 2 — match the whole prediction string.
    return _match_options(pred, options)


def _match_options(text: str, options: dict) -> str | None:
    text_norm = _norm(text)
    if not text_norm:
        return None
    # Exact match wins outright.
    exact = [letter for letter, val in options.items() if _norm(val) == text_norm]
    if len(exact) == 1:
        return exact[0].upper()
    # Substring fallback — only accept when there's a single unambiguous
    # match. Sort by option-text length descending so the longest option
    # wins when one option text is a prefix/substring of another (e.g.
    # ``"3"`` vs ``"35"``).
    candidates = sorted(options.items(), key=lambda kv: -len(_norm(kv[1])))
    matches = [
        letter
        for letter, val in candidates
        if text_norm in _norm(val) or _norm(val) in text_norm
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
    err = excluded = 0

    for r in records:
        if (
            r.get("domain") in exclude_domains
            or r.get("subdomain") in exclude_subdomains
        ):
            excluded += 1
            continue
        pred = r.get("prediction")
        if _is_empty_or_error(pred):
            err += 1
            continue
        pred = str(pred)
        key = parse_key(pred)
        if key is None:
            key = parse_key_from_options(pred, r.get("options") or {})
        if key is None:
            err += 1
            continue
        ok = int(key == r.get("correct_key"))
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
        "errors": err,
        "correct": total[0],
        "accuracy": total[0] / total[1] if total[1] else 0,
        "by_domain": {d: (c, t, c / t if t else 0) for d, (c, t) in dom.items()},
        "by_level": {L: (c, t, c / t if t else 0) for L, (c, t) in lvl.items()},
        "by_subdomain": {s: (c, t, c / t if t else 0) for s, (c, t) in sub.items()},
    }


# ── terminal formatting ───────────────────────────────────────────────────────

_W = 44  # model name column width


def fmt_row(name: str, stats: dict, name_width: int = _W) -> str:
    return (
        f"  {name:<{name_width}} "
        f"acc={stats['accuracy'] * 100:>6.2f}%  "
        f"({stats['correct']:>7,} / {stats['parseable']:>7,})  "
        f"err={stats['errors']:>5}"
    )


def print_domain_rows(stats: dict) -> None:
    """Per-domain rows printed beneath the model summary line."""
    seen = set()
    ordered = [d for d in DOMAINS if d in stats["by_domain"]]
    extras = sorted(d for d in stats["by_domain"] if d not in DOMAINS)
    for domain in ordered + extras:
        if domain in seen:
            continue
        seen.add(domain)
        dc, dt, da = stats["by_domain"][domain]
        print(f"    {domain:<20}  {dc:>6,}/{dt:<6,}  {da * 100:>6.2f}%")


# ── lm_eval (lm-evaluation-harness) results ───────────────────────────────────
#
# lm_eval writes results to:
#   output/lm_eval/<lang>/<model_dir>/<model_dir>/results_<ISOtimestamp>.json
# The JSON has ``results.urdummlu_<N>shot.exact_match,none`` (float 0-1) and
# ``n-samples.urdummlu_<N>shot.original`` (int). We pick the latest results
# file per model directory.

_LM_EVAL_TASK_RE = re.compile(r"urdummlu_(\d+)shot")


def discover_lm_eval(lang: str) -> list[dict]:
    """Return one stats dict per (model × n-shot) lm_eval result for ``lang``.

    Each dict is shaped like the output of ``evaluate()`` so it can be passed
    straight to ``fmt_row``. ``errors`` is always 0 here — lm_eval evaluates
    via likelihood/exact-match and has no parsing step.
    """
    lm_root = OUTPUT_DIR / "lm_eval" / lang
    if not lm_root.exists():
        return []

    rows: list[dict] = []
    # Each model has its own dir, with a nested dir, with one results file
    # per run. Take the latest by filename sort (lm_eval stamps ISO time).
    for model_dir in sorted(lm_root.iterdir()):
        if not model_dir.is_dir():
            continue
        results_files = sorted(model_dir.glob("*/results_*.json"))
        if not results_files:
            continue
        latest = results_files[-1]
        # Use the inner directory name (matches our safe_model_name format).
        model_name = latest.parent.name
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = data.get("results", {})
        n_samples = data.get("n-samples", {})
        for task, tres in results.items():
            m = _LM_EVAL_TASK_RE.match(task)
            if not m:
                continue
            shots = f"{m.group(1)}shot"
            acc = tres.get("exact_match,none")
            n = (n_samples.get(task) or {}).get("original")
            if acc is None or not n:
                continue
            correct = round(float(acc) * int(n))
            rows.append({
                "model": model_name,
                "label": f"{model_name} ({shots})",
                "shots": shots,
                "n": int(n),
                "excluded": 0,
                "parseable": int(n),
                "errors": 0,
                "correct": correct,
                "accuracy": float(acc),
                "by_domain": {},
                "by_level": {},
                "by_subdomain": {},
            })
    return rows


# ── CSV export ────────────────────────────────────────────────────────────────


def _csv_fieldnames() -> list[str]:
    base = [
        "model",
        "language",
        "total_correct",
        "total_questions",
        "total_accuracy",
        "errors",
    ]
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
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--lang", help="Restrict to a single language (e.g. ur)")
    parser.add_argument("--model", help="Restrict to a model name substring")
    parser.add_argument(
        "--exclude-domain",
        action="append",
        default=[],
        help="Domain to exclude from accuracy (repeatable).",
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
    parser.add_argument(
        "--csv",
        nargs="?",
        const=str(DEFAULT_CSV),
        default=None,
        help=(
            "Write per-model × language results to CSV. "
            f"Use bare flag for the default path ({DEFAULT_CSV}), "
            "or supply --csv <path>."
        ),
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

    csv_rows: list[dict] = []
    langs = sorted(
        p.name
        for p in OUTPUT_DIR.iterdir()
        if p.is_dir() and p.name != "lm_eval"
    )
    for lang in langs:
        if args.lang and lang != args.lang:
            continue
        paths = sorted(OUTPUT_DIR.glob(f"{lang}/*/predictions.json"))
        lm_rows = discover_lm_eval(lang)
        if not paths and not lm_rows:
            continue
        print(f"\n[{lang}]")
        for path in paths:
            model = path.parent.name
            if args.model and args.model not in model:
                continue
            records = json.loads(path.read_text(encoding="utf-8"))
            stats = evaluate(
                records,
                exclude_domains=exclude_domains,
                exclude_subdomains=exclude_subdomains,
            )
            print(fmt_row(model, stats))
            if args.detailed:
                print_domain_rows(stats)
            if args.csv is not None:
                csv_rows.append(stats_to_csv_row(model, lang, stats))

        # lm_eval rows: one per (model × n-shot). Printed under their own
        # sub-header so they don't visually mix with the 0-shot pipeline.
        filtered = [
            r for r in lm_rows
            if not args.model or args.model in r["model"]
        ]
        if filtered:
            print(f"\n[{lang} · lm_eval]")
            for row in sorted(filtered, key=lambda r: (r["model"], r["shots"])):
                print(fmt_row(row["label"], row))
                if args.csv is not None:
                    csv_rows.append(stats_to_csv_row(row["label"], lang, row))

    if args.csv is not None:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_csv_fieldnames())
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\nCSV saved → {out}  ({len(csv_rows)} rows)")


if __name__ == "__main__":
    main()
