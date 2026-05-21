#!/usr/bin/env python3
"""Stage 14 — Bidi isolation + math-exponent normalization.

Two transforms, both targeting how math/Latin fragments render in
mixed-bidi Urdu text:

1. **Exponent normalization** (math/physics subdomains only) —
   ``a2``, ``b3``, ``(x+1)2`` → ``a²``, ``b³``, ``(x+1)²``.
   Pattern: a digit ``2-9`` immediately following a letter or closing
   paren, with a non-alphanumeric (or end) after it. Restricted to
   ``mathematics`` and ``physics`` subdomains so chemistry formulas
   like ``H2O``, ``CO2`` aren't mangled into ``H²O``, ``CO²``.

2. **Bidi isolation** — wraps Latin / digit / math fragments in
   Unicode LRI (U+2066) … PDI (U+2069) markers so they render
   correctly inside an RTL Urdu paragraph in any bidi-aware viewer.

Applied **only** to the user-visible content fields:

  - ``question``
  - ``options.*`` (each value)
  - ``correct_option``

Other fields (``source``, ``source_url``, ``subdomain``, ``level``,
``id``, etc.) are not touched.

Reads ``data/13-correlation-deduplicated/*.json`` and writes to
``data/14-bidi-isolated/*.json``.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "data" / "13-correlation-deduplicated"
DST_DIR = REPO_ROOT / "data" / "14-bidi-isolated"
FILES = ["mcqs_with_answers.json", "mcqs_without_answers.json", "mcqs_upsampled.json"]

LRI = "⁦"
PDI = "⁩"

# A "LTR fragment" = at least one Latin/digit/math char, may contain
# internal whitespace and math punctuation; must end with an
# alphanumeric or closing-bracket-class char (so we don't isolate
# trailing operators).
LTR_FRAGMENT_RE = re.compile(
    r"""
    (
        (?: [A-Za-z0-9]              # start: a strong-LTR char ...
          | [()+\-*/=^.,%]            #  ... or math punctuation
          | [²³]                       #  ... or sup digits
        )
        (?: [A-Za-z0-9\s()+\-*/=^.,%²³] )*   # middle: same plus spaces
        [A-Za-z0-9)²³%]              # end: alphanumeric / closer
    )
    """,
    re.VERBOSE,
)

URDU_RE = re.compile(r"[؀-ۿݐ-ݿ]")

# Math notation normalization (math / physics subdomains only)
SUPERSCRIPT = {"2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}
SUBSCRIPT   = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉"}

# log_n, ln_n, lg_n, exp_n — base/index is a subscript, not a superscript
FN_SUBSCRIPT_RE = re.compile(r"\b(log|ln|lg|exp)([2-9])(?=[^A-Za-z0-9]|$)")

# Letter (Latin or Greek) or closing paren, followed by a digit, at end of variable
EXPONENT_END_RE = re.compile(
    r"(?<=[A-Za-zΑ-Ωα-ω)])([2-9])(?=[^A-Za-z0-9]|$)"
)
# Same letter-digit pattern but with a letter on the *right* too (digit
# sandwiched between letters). Math subdomain only — would over-fire on
# chemistry-style ``H2O`` if applied broadly.
EXPONENT_MID_RE = re.compile(
    r"(?<=[A-Za-zΑ-Ωα-ω])([2-9])(?=[A-Za-zΑ-Ωα-ω])"
)

# Physics deliberately excluded: m1/m2, v1/v2, r1/r2 etc. are subscript
# indices, not exponents — converting them would mangle the content.
MATH_SUBDOMAINS = {"mathematics"}


def convert_exponents(text):
    """In a math context normalize visual math:

      - ``log5 8`` → ``log₅ 8``   (function name + numeric base → subscript)
      - ``a2 + b2`` → ``a² + b²`` (letter or close-paren + digit → superscript)

    Returns ``(text, count)``.
    """
    if not isinstance(text, str) or not text:
        return text, 0
    count = 0

    def to_sub(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}{SUBSCRIPT[m.group(2)]}"
    text = FN_SUBSCRIPT_RE.sub(to_sub, text)

    def to_sup(m):
        nonlocal count
        count += 1
        return SUPERSCRIPT[m.group(1)]
    text = EXPONENT_END_RE.sub(to_sup, text)
    text = EXPONENT_MID_RE.sub(to_sup, text)

    return text, count


LATIN_DIGIT_RE = re.compile(r"[A-Za-z0-9]")


def isolate_ltr(text):
    """Wrap each maximal non-Urdu region that contains LTR-strong content
    in LRI…PDI. Edge whitespace is kept outside the wrap so spaces
    between Urdu words don't get pulled into the isolate.

    Returns ``(new_text, region_count)``. Idempotent: skips strings that
    already contain LRI/PDI markers.
    """
    if not isinstance(text, str) or not text:
        return text, 0
    if LRI in text or PDI in text:
        return text, 0

    has_urdu = bool(URDU_RE.search(text))
    has_ltr = bool(LATIN_DIGIT_RE.search(text))
    if not has_ltr:
        return text, 0

    # Pure-LTR string inside an RTL container would still get its
    # neutrals (parens, math symbols, superscripts) reordered by bidi.
    # Wrap the whole thing so it renders as an isolated LTR unit.
    if not has_urdu:
        return f"{LRI}{text}{PDI}", 1

    # Mixed: iterate, accumulating non-Urdu chars into a buffer; flush
    # the buffer (wrapped in LRI/PDI when it has LTR content) whenever an
    # Urdu char is reached.
    out = []
    buf = []
    count = 0

    def flush():
        nonlocal count
        if not buf:
            return
        s = "".join(buf)
        buf.clear()
        if LATIN_DIGIT_RE.search(s):
            stripped = s.strip()
            leading = s[: len(s) - len(s.lstrip())]
            trailing = s[len(s.rstrip()):]
            out.append(leading)
            out.append(LRI)
            out.append(stripped)
            out.append(PDI)
            out.append(trailing)
            count += 1
        else:
            out.append(s)

    for ch in text:
        if URDU_RE.match(ch):
            flush()
            out.append(ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out), count


def fix_item(item, stats):
    is_math = item.get("subdomain") in MATH_SUBDOMAINS

    def maybe_exponents(text):
        if not is_math:
            return text, 0
        return convert_exponents(text)

    q = item.get("question", "")
    q, ne = maybe_exponents(q)
    stats["exponents"] += ne
    q, n = isolate_ltr(q)
    if n:
        stats["q_fragments"] += n
        stats["q_changed"] += 1
    item["question"] = q

    opts = item.get("options")
    if isinstance(opts, dict):
        for k, v in opts.items():
            if isinstance(v, str):
                v, ne = maybe_exponents(v)
                stats["exponents"] += ne
                v, n = isolate_ltr(v)
                if n:
                    stats["o_fragments"] += n
                    stats["o_changed"] += 1
                opts[k] = v

    co = item.get("correct_option")
    if isinstance(co, str):
        co, ne = maybe_exponents(co)
        stats["exponents"] += ne
        co, n = isolate_ltr(co)
        if n:
            stats["c_fragments"] += n
            stats["c_changed"] += 1
        item["correct_option"] = co
    return item


def process_file(src, dst):
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    stats = {
        "total": len(data),
        "q_changed": 0, "q_fragments": 0,
        "o_changed": 0, "o_fragments": 0,
        "c_changed": 0, "c_fragments": 0,
        "exponents": 0,
    }
    for item in data:
        fix_item(item, stats)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return stats


def main():
    print(f"Source:      {SRC_DIR}")
    print(f"Destination: {DST_DIR}\n")
    DST_DIR.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        src = SRC_DIR / name
        dst = DST_DIR / name
        if not src.exists():
            print(f"Skip (not found): {src}")
            continue
        s = process_file(src, dst)
        print(f"{name}  (total {s['total']})")
        print(f"  exponents normalized:     {s['exponents']}  (math/physics only)")
        print(f"  questions wrapped:        {s['q_changed']}  (fragments: {s['q_fragments']})")
        print(f"  option values wrapped:    {s['o_changed']}  (fragments: {s['o_fragments']})")
        print(f"  correct_option wrapped:   {s['c_changed']}  (fragments: {s['c_fragments']})")
        print()


if __name__ == "__main__":
    main()
