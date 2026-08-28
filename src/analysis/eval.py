#!/usr/bin/env python3
"""Accuracy evaluation across all model predictions.

Metric
------
The primary metric is ALL-ITEM exact match: the denominator is every released
item and an invalid output counts as WRONG. Accuracy among parseable outputs
is still computed and exported, but as ``accuracy_valid`` — it is conditional
on the model having produced a readable answer and must always be shown next
to the invalid rate. The two diverge sharply for models that break format
(BLOOMZ-3B / Urdu prompt: 28.62% among-valid vs 7.39% all-item at a 74.2%
invalid rate).

Scores are restricted to the ids in ``data/26-eval/mcqs.json`` (26,389). The
frozen prediction files still carry the 42 items whose gold answer landed
outside A-D, which Stage 26-eval now drops; they are skipped and counted as
``unreleased``.

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
DEFAULT_SUBDOMAIN_CSV = REPO_ROOT / "output" / "subdomain_accuracy.csv"
DEFAULT_LENGTH_TIER_CSV = REPO_ROOT / "output" / "length_tier_accuracy.csv"

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


def released_ids() -> set[int]:
    """Ids in the released benchmark (data/26-eval/mcqs.json).

    The frozen prediction files still carry the 42 items whose gold answer
    landed outside A-D and that Stage 26-eval now drops, so every score is
    restricted to this set. Cached on first use.
    """
    if not hasattr(released_ids, "_cache"):
        path = REPO_ROOT / "data" / "26-eval" / "mcqs.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        released_ids._cache = {r["id"] for r in rows}
    return released_ids._cache


def evaluate(
    records: list[dict],
    exclude_domains: set[str] | None = None,
    exclude_subdomains: set[str] | None = None,
    restrict_ids: set[int] | None = None,
) -> dict:
    """Score one run.

    Two accuracies are returned, and they are not interchangeable:

      ``accuracy``        all-item exact match — invalid outputs count as
                          WRONG. This is the primary reported metric.
      ``accuracy_valid``  accuracy among parseable outputs only. Conditional
                          on the model having produced a readable answer, so
                          it flatters models that fail to follow the format
                          (BLOOMZ-3B under the Urdu prompt: 28.62% here vs
                          7.39% all-item, on a 74.2% invalid rate). Report it
                          only alongside coverage, and never as "accuracy".

    Each bucket carries ``(correct, scored, parseable)`` so both metrics can be
    recovered per domain / level / subdomain / length tier.
    """
    exclude_domains = exclude_domains or set()
    exclude_subdomains = exclude_subdomains or set()
    if restrict_ids is None:
        restrict_ids = released_ids()

    dom: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    lvl: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    tier: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    sub_dom: dict[str, str] = {}
    total = [0, 0, 0]  # correct, scored, parseable
    err = excluded = unreleased = 0

    for r in records:
        if restrict_ids is not None and r.get("id") not in restrict_ids:
            unreleased += 1
            continue
        if (
            r.get("domain") in exclude_domains
            or r.get("subdomain") in exclude_subdomains
        ):
            excluded += 1
            continue

        domain = r.get("domain", "?")
        subdomain = r.get("subdomain", "?")
        level = r.get("level", "?")
        lt = r.get("length_tier")
        buckets = [total, dom[domain], lvl[level], sub[subdomain]]
        if lt:
            buckets.append(tier[lt])
        sub_dom.setdefault(subdomain, domain)

        # Every released item is scored, whether or not it parses.
        for b in buckets:
            b[1] += 1

        pred = r.get("prediction")
        key = None
        if not _is_empty_or_error(pred):
            pred = str(pred)
            key = parse_key(pred) or parse_key_from_options(pred, r.get("options") or {})
        if key is None:
            err += 1
            continue

        for b in buckets:
            b[2] += 1
        ok = int(key == r.get("correct_key"))
        for b in buckets:
            b[0] += ok

    def rollup(counts: dict[str, list[int]]) -> dict:
        return {k: (c, s, c / s if s else 0, p) for k, (c, s, p) in counts.items()}

    correct, scored, parseable = total
    return {
        "n": len(records),
        "excluded": excluded,
        "unreleased": unreleased,
        "scored": scored,
        "parseable": parseable,
        "errors": err,
        "correct": correct,
        "accuracy": correct / scored if scored else 0,
        "accuracy_valid": correct / parseable if parseable else 0,
        "invalid_rate": err / scored if scored else 0,
        "by_domain": rollup(dom),
        "by_level": rollup(lvl),
        "by_subdomain": rollup(sub),
        "subdomain_to_domain": sub_dom,
        "by_length_tier": rollup(tier),
    }


# ── terminal formatting ───────────────────────────────────────────────────────

_W = 44  # model name column width


def fmt_row(name: str, stats: dict, name_width: int = _W) -> str:
    return (
        f"  {name:<{name_width}} "
        f"acc={stats['accuracy'] * 100:>6.2f}%  "
        f"({stats['correct']:>7,} / {stats['scored']:>7,})  "
        f"valid={stats['accuracy_valid'] * 100:>6.2f}%  "
        f"inv={stats['invalid_rate'] * 100:>5.2f}%"
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
        dc, dt, da, _dp = stats["by_domain"][domain]
        print(f"    {domain:<20}  {dc:>6,}/{dt:<6,}  {da * 100:>6.2f}%")


# ── lm_eval (lm-evaluation-harness) results ───────────────────────────────────
#
# lm_eval writes results to:
#   output/lm_eval/<lang>/[<model_dir>/]<model_dir>/results_<ISOtimestamp>.json
# alongside one samples_<task>_<ISOtimestamp>.jsonl per task.
#
# We recompute from the SAMPLES files rather than reading the aggregate in
# results_*.json, for two reasons:
#   * the aggregate is over all 26,431 items, including the 42 that Stage
#     26-eval now drops; and
#   * the aggregate includes the 130 few-shot demonstration items, which are
#     also present in the scoring split, so demonstrations were being scored
#     as test questions.
# Both are excluded here, giving a 26,259-item population that is matched
# across the 0-/1-/3-/5-shot comparison.
#
# Scoring rule: lm_eval's ``exact_match`` on this task is reproduced exactly by
# comparing the first non-space character of the target and the response (the
# answer key letter). Verified against all 24 reported run aggregates to 1e-12,
# and against first-line equality with 0 disagreements over 211,448 decisions.

_LM_EVAL_TASK_RE = re.compile(r"urdummlu_(\d+)shot")


def fewshot_pool_ids() -> set[int]:
    """Ids of the held-out few-shot demonstration pool (mcqs_dev.json)."""
    if not hasattr(fewshot_pool_ids, "_cache"):
        path = REPO_ROOT / "data" / "26-eval" / "mcqs_dev.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        fewshot_pool_ids._cache = {r["id"] for r in rows}
    return fewshot_pool_ids._cache


def _lm_eval_correct(target: str, response: str) -> bool:
    return target.strip()[:1] == response.strip()[:1]


def discover_lm_eval(lang: str, restrict_ids: set[int] | None = None,
                     exclude_ids: set[int] | None = None) -> list[dict]:
    """Return one stats dict per (model × n-shot) lm_eval run for ``lang``.

    Each dict is shaped like the output of ``evaluate()`` so it can be passed
    straight to ``fmt_row``. ``errors`` is always 0 here: lm_eval scores the
    generated continuation directly and has no parsing step, so all-item and
    among-valid accuracy coincide.
    """
    lm_root = OUTPUT_DIR / "lm_eval" / lang
    if not lm_root.exists():
        return []
    if restrict_ids is None:
        restrict_ids = released_ids()
    if exclude_ids is None:
        exclude_ids = fewshot_pool_ids()

    rows: list[dict] = []
    # Model dirs are sometimes nested one level deeper; take the latest
    # results file per directory (lm_eval stamps ISO time into the name).
    seen: dict[str, Path] = {}
    for results_file in sorted(lm_root.rglob("results_*.json")):
        seen[results_file.parent.name] = results_file

    for model_name, latest in sorted(seen.items()):
        stamp = latest.name[len("results_"):-len(".json")]
        for samples in sorted(latest.parent.glob(f"samples_*_{stamp}.jsonl")):
            m = _LM_EVAL_TASK_RE.search(samples.name)
            if not m:
                continue
            shots = f"{m.group(1)}shot"
            correct = scored = skipped = 0
            with open(samples, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    doc_id = (rec.get("doc") or {}).get("id")
                    if doc_id not in restrict_ids or doc_id in exclude_ids:
                        skipped += 1
                        continue
                    scored += 1
                    correct += _lm_eval_correct(rec["target"], rec["filtered_resps"][0])
            if not scored:
                continue
            acc = correct / scored
            rows.append({
                "model": model_name,
                "label": f"{model_name} ({shots})",
                "shots": shots,
                "n": scored + skipped,
                "excluded": 0,
                "unreleased": skipped,
                "scored": scored,
                "parseable": scored,
                "errors": 0,
                "correct": correct,
                "accuracy": acc,
                "accuracy_valid": acc,
                "invalid_rate": 0.0,
                "by_domain": {},
                "by_level": {},
                "by_subdomain": {},
                "subdomain_to_domain": {},
                "by_length_tier": {},
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
        "total_accuracy_valid",
        "parseable",
        "errors",
        "invalid_rate",
    ]
    for d in DOMAINS:
        col = d.replace(" ", "_")
        base += [f"{col}_correct", f"{col}_questions", f"{col}_accuracy"]
    return base


def stats_to_csv_row(model: str, lang: str, stats: dict) -> dict:
    # ``*_questions`` and ``*_accuracy`` are all-item: the denominator is every
    # released item, and invalid outputs count as wrong.
    row: dict = {
        "model": model,
        "language": lang,
        "total_correct": stats["correct"],
        "total_questions": stats["scored"],
        "total_accuracy": round(stats["accuracy"] * 100, 2),
        "total_accuracy_valid": round(stats["accuracy_valid"] * 100, 2),
        "parseable": stats["parseable"],
        "errors": stats["errors"],
        "invalid_rate": round(stats["invalid_rate"] * 100, 4),
    }
    for d in DOMAINS:
        col = d.replace(" ", "_")
        dc, dt, da, _dp = stats["by_domain"].get(d, (0, 0, 0.0, 0))
        row[f"{col}_correct"] = dc
        row[f"{col}_questions"] = dt
        row[f"{col}_accuracy"] = round(da * 100, 2)
    return row


def _length_tier_csv_fieldnames() -> list[str]:
    return ["model", "language", "length_tier", "correct", "questions",
            "accuracy", "parseable", "accuracy_valid"]


def stats_to_length_tier_csv_rows(model: str, lang: str, stats: dict) -> list[dict]:
    # NOTE: length_tier is only populated for the exam-derived half of the
    # benchmark; the 13,630 web-derived items carry null and are absent here.
    rows = []
    for lt, (correct, total, acc, parseable) in sorted(stats["by_length_tier"].items()):
        rows.append({
            "model": model,
            "language": lang,
            "length_tier": lt,
            "correct": correct,
            "questions": total,
            "accuracy": round(acc * 100, 2),
            "parseable": parseable,
            "accuracy_valid": round(100 * correct / parseable, 2) if parseable else 0,
        })
    return rows


def _subdomain_csv_fieldnames() -> list[str]:
    return ["model", "language", "domain", "subdomain", "correct", "questions",
            "accuracy", "parseable", "accuracy_valid"]


def stats_to_subdomain_csv_rows(model: str, lang: str, stats: dict) -> list[dict]:
    sub_dom = stats.get("subdomain_to_domain", {})
    rows = []
    for subdomain, (correct, total, acc, parseable) in sorted(stats["by_subdomain"].items()):
        rows.append({
            "model": model,
            "language": lang,
            "domain": sub_dom.get(subdomain, "?"),
            "subdomain": subdomain,
            "correct": correct,
            "questions": total,
            "accuracy": round(acc * 100, 2),
            "parseable": parseable,
            "accuracy_valid": round(100 * correct / parseable, 2) if parseable else 0,
        })
    return rows


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
    parser.add_argument(
        "--subdomain-csv",
        nargs="?",
        const=str(DEFAULT_SUBDOMAIN_CSV),
        default=None,
        help=(
            "Write per-model × subdomain accuracy to CSV (long format). "
            f"Use bare flag for the default path ({DEFAULT_SUBDOMAIN_CSV}), "
            "or supply --subdomain-csv <path>."
        ),
    )
    parser.add_argument(
        "--length-tier-csv",
        nargs="?",
        const=str(DEFAULT_LENGTH_TIER_CSV),
        default=None,
        help=(
            "Write per-model × language × length_tier accuracy to CSV. "
            f"Use bare flag for the default path ({DEFAULT_LENGTH_TIER_CSV}), "
            "or supply --length-tier-csv <path>."
        ),
    )
    args = parser.parse_args()

    if args.detailed and args.csv is None:
        args.csv = str(DEFAULT_CSV)
    if args.detailed and args.subdomain_csv is None:
        args.subdomain_csv = str(DEFAULT_SUBDOMAIN_CSV)
    if args.detailed and args.length_tier_csv is None:
        args.length_tier_csv = str(DEFAULT_LENGTH_TIER_CSV)

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
    subdomain_csv_rows: list[dict] = []
    length_tier_csv_rows: list[dict] = []
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
            if args.subdomain_csv is not None:
                subdomain_csv_rows.extend(stats_to_subdomain_csv_rows(model, lang, stats))
            if args.length_tier_csv is not None:
                length_tier_csv_rows.extend(stats_to_length_tier_csv_rows(model, lang, stats))

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
                if args.subdomain_csv is not None:
                    subdomain_csv_rows.extend(stats_to_subdomain_csv_rows(row["label"], lang, row))
                if args.length_tier_csv is not None:
                    length_tier_csv_rows.extend(stats_to_length_tier_csv_rows(row["label"], lang, row))

    if args.csv is not None:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_csv_fieldnames())
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\nCSV saved → {out}  ({len(csv_rows)} rows)")

    if args.subdomain_csv is not None:
        out = Path(args.subdomain_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_subdomain_csv_fieldnames())
            writer.writeheader()
            writer.writerows(subdomain_csv_rows)
        print(f"\nSubdomain CSV saved → {out}  ({len(subdomain_csv_rows)} rows)")

    if args.length_tier_csv is not None:
        out = Path(args.length_tier_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_length_tier_csv_fieldnames())
            writer.writeheader()
            writer.writerows(length_tier_csv_rows)
        print(f"\nLength-tier CSV saved → {out}  ({len(length_tier_csv_rows)} rows)")


if __name__ == "__main__":
    main()
