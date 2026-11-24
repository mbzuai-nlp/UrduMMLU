#!/usr/bin/env python3
"""Camera-ready audit: recompute every number the paper reports.

Cross-checks the claims in the EMNLP 2026 camera-ready audit memo against
the actual pipeline outputs in ``data/`` and ``output/``.

Usage:
    python src/analysis/camera_ready_audit.py                 # all sections
    python src/analysis/camera_ready_audit.py --section eval
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from eval import evaluate, parse_key, parse_key_from_options, _is_empty_or_error

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
OUT = REPO / "output"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.4f}%" if b else "n/a"


def hdr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


# ── 1. candidate pool (paper "Raw" column, Tables 7 & 8) ──────────────────────

def candidate_pool():
    hdr("1. CLEANED CANDIDATE POOL (paper 'Raw' = 40,427)")
    stage = DATA / "15-english-filtered"
    with_ans = load(stage / "mcqs_with_answers.json")
    no_ans = load(stage / "mcqs_without_answers.json")
    ups = load(stage / "mcqs_upsampled.json")
    pool = with_ans + no_ans
    print(f"with_answers            = {len(with_ans):,}")
    print(f"without_answers         = {len(no_ans):,}")
    print(f"upsampled (separate)    = {len(ups):,}")
    print(f"POOL (with + without)   = {len(pool):,}   <- paper says 40,427")
    print(f"POOL + upsampled        = {len(pool) + len(ups):,}")

    dom = Counter(r.get("domain") or "<none>" for r in pool)
    print("\nDomain distribution of pool:")
    for d, n in dom.most_common():
        print(f"  {d:<18} {n:>7,}")
    print(f"  {'TOTAL':<18} {sum(dom.values()):>7,}")

    # source: one row per (item, source) vs primary-source attribution
    multi = Counter(len(r.get("source") or []) for r in pool)
    print(f"\nsources-per-item histogram: {dict(sorted(multi.items()))}")
    flat = Counter()
    primary = Counter()
    for r in pool:
        srcs = r.get("source") or ["<none>"]
        for s in srcs:
            flat[s] += 1
        primary[srcs[0]] += 1
    print("\nSource distribution (flat = row per (item,source); primary = first source):")
    print(f"  {'source':<22}{'flat':>9}{'primary':>10}")
    for s, n in flat.most_common():
        print(f"  {s:<22}{n:>9,}{primary[s]:>10,}")
    print(f"  {'TOTAL':<22}{sum(flat.values()):>9,}{sum(primary.values()):>10,}")
    return pool


# ── 2. final benchmark (paper "Final" column) ────────────────────────────────

def final_benchmark():
    hdr("2. FINAL BENCHMARK (26,431)")
    final = load(DATA / "26-eval" / "mcqs.json")
    print(f"items = {len(final):,}")

    dom = Counter(r["domain"] for r in final)
    tot = len(final)
    print("\nDomain distribution + share (paper Table 8 'Final'):")
    for d, n in dom.most_common():
        print(f"  {d:<18} {n:>7,}   {100*n/tot:>7.4f}%  -> rounds to {100*n/tot:.1f}%")
    print(f"  {'TOTAL':<18} {tot:>7,}")

    multi = Counter(len(r.get("source") or []) for r in final)
    print(f"\nsources-per-item histogram: {dict(sorted(multi.items()))}")
    flat, primary = Counter(), Counter()
    for r in final:
        srcs = [s["name"] if isinstance(s, dict) else s for s in (r.get("source") or ["<none>"])]
        for s in srcs:
            flat[s] += 1
        primary[srcs[0]] += 1
    print("\nSource distribution (paper Table 7 'Final'):")
    print(f"  {'source':<22}{'flat':>9}{'primary':>10}")
    for s, n in flat.most_common():
        print(f"  {s:<22}{n:>9,}{primary[s]:>10,}")
    print(f"  {'TOTAL':<22}{sum(flat.values()):>9,}{sum(primary.values()):>10,}")

    print("\nLevel x domain (paper: 'STEM and SS become more prominent at HSSC'):")
    lvl = defaultdict(Counter)
    for r in final:
        lvl[r["domain"]][r.get("level") or "<none>"] += 1
    levels = ["SSC-I", "SSC-II", "HSSC-I", "HSSC-II", "<none>"]
    print(f"  {'domain':<18}" + "".join(f"{L:>10}" for L in levels))
    for d in sorted(lvl):
        print(f"  {d:<18}" + "".join(f"{lvl[d][L]:>10,}" for L in levels))
    print("  within-level domain share (%):")
    for L in levels:
        col = {d: lvl[d][L] for d in lvl}
        s = sum(col.values())
        if not s:
            continue
        parts = "  ".join(f"{d}={100*n/s:.1f}" for d, n in sorted(col.items(), key=lambda kv: -kv[1]))
        print(f"    {L:<9} n={s:<7,} {parts}")
    return final


# ── 3. provenance / consensus flow ───────────────────────────────────────────

def flow():
    hdr("3. ANNOTATION + PROVENANCE FLOW")
    s21 = load(DATA / "21-final-annotated" / "stats.json")
    s22 = load(DATA / "22-final-combined" / "stats.json")
    s24 = load(DATA / "24-deduplicated" / "stats.json")
    s25 = load(DATA / "25-final" / "stats.json")

    d = s21["drop_breakdown"]
    tot_in, tot_ok = s21["total_input"], s21["total_included"]
    print(f"annotated in            = {tot_in:,}")
    print(f"  flagged               = {d['flagged']:,}")
    print(f"  unsure                = {d['unsure']:,}")
    print(f"  incomplete (single)   = {d['single_annotated']:,}")
    print(f"  disagree              = {d['disagree']:,}")
    print(f"  sum dropped           = {sum(d.values()):,}")
    print(f"consensus retained      = {tot_ok:,}  (check {tot_in} - {sum(d.values())} = {tot_in - sum(d.values())})")

    eligible = tot_in - d["flagged"] - d["unsure"] - d["single_annotated"]
    print(f"\nAGREEMENT POPULATION (audit claim: 16,070, not 14,459)")
    print(f"  answer-eligible       = {eligible:,}")
    print(f"  agreed                = {tot_ok:,}")
    print(f"  disagreed             = {d['disagree']:,}")
    print(f"  observed agreement    = {tot_ok}/{eligible} = {pct(tot_ok, eligible)}")
    print(f"  paper reports         = 89.98%")
    ka = (tot_ok / eligible - 0.25) / 0.75
    print(f"  (obs - .25)/.75       = {ka:.4f}   paper reports kappa = 0.8663")

    per_pair = s21["agreement"]["per_pair"]
    print(f"\nFigure 13 pairwise cells: {len(per_pair)} pairs")
    print(f"  sum of pair totals    = {sum(v['total'] for v in per_pair.values()):,}")
    print(f"  sum of pair agrees    = {sum(v['agree'] for v in per_pair.values()):,}")
    print(f"  pairs with n < 50     = {sum(1 for v in per_pair.values() if v['total'] < 50)}")
    print(f"  min pair n            = {min(v['total'] for v in per_pair.values())}")

    print(f"\n22-final-combined total = {s22['total']:,}")
    print(f"  inputs: {s22['inputs']}")
    print(f"  sum of inputs (annotated + scraped_valid + upsampled) = "
          f"{s22['inputs']['annotated'] + s22['inputs']['scraped_with_valid_key'] + s22['inputs']['upsampled_with_valid_key']:,}")
    print(f"  provenance: {s22['provenance']}  (sum = {sum(s22['provenance'].values()):,})")
    print(f"\n24-dedup: input {s24['input_rows']:,} -> output {s24['applied_output_rows']:,} "
          f"(threshold {s24['applied_threshold']})")
    sweep = {e['threshold']: e for e in s24['sweep']}
    t = s24['applied_threshold']
    print(f"  sweep[{t}] says kept {sweep[t]['kept']:,} / removed {sweep[t]['removed']:,} "
          f"-> MISMATCH vs applied_output_rows {s24['applied_output_rows']:,} "
          f"(delta {sweep[t]['kept'] - s24['applied_output_rows']:,})")
    print(f"\n25-final provenance: {s25['provenance']}  (sum = {sum(s25['provenance'].values()):,})")
    print(f"  exam-derived 14,459 -> 12,759 : loss = {14459 - s25['provenance']['annotated']:,}")
    print(f"  web 13,877+498=14,375 -> 13,672 : loss = {14375 - s25['provenance']['scraped']:,}")
    print(f"  answer-key dist: {s25['correct_key_distribution']}  "
          f"(note E={s25['correct_key_distribution'].get('E', 0)} -> not 4-option!)")


# ── 4. MMLU-ProX overlap subjects ────────────────────────────────────────────

NINE = ["biology", "chemistry", "computer science", "economics", "geography",
        "mathematics", "physics", "psychology", "sociology"]


def prox_overlap(final):
    hdr("4. MMLU-ProX 9-SUBJECT OVERLAP (paper: 6,852 UrduMMLU questions)")
    c = Counter(r["subdomain"] for r in final)
    tot = 0
    for s in NINE:
        print(f"  {s:<20}{c[s]:>7,}")
        tot += c[s]
    print(f"  {'TOTAL':<20}{tot:>7,}   <- paper's table uses 6,852")
    print(f"  delta = {tot - 6852:,}")
    tex = REPO / "report" / "tables" / "native_vs_prox.tex"
    if tex.exists():
        import re
        body = tex.read_text(encoding="utf-8")
        nums = re.findall(r"\\multirow\{2\}\{\*\}\{([\d,]+)\}", body)
        print(f"  per-subject n in native_vs_prox.tex: {nums}")


# ── 5. evaluation: denominator ───────────────────────────────────────────────

def evaluation():
    hdr("5. ACCURACY DENOMINATOR (audit P0-01 -- now fixed in eval.py)")
    print("all    = correct / released items   (invalid scored wrong)  <- REPORTED")
    print("valid  = correct / parseable        (conditional; flatters format failures)")
    print(f"\n{'lang':<5}{'model':<42}{'n':>7}{'inval':>7}{'inv%':>7}{'all%':>8}{'valid%':>8}{'delta':>8}")
    rows = []
    for lang in ("en", "ur"):
        for p in sorted((OUT / lang).glob("*/predictions.json")):
            st = evaluate(load(p))
            rows.append((lang, p.parent.name, st["scored"], st["errors"],
                         100 * st["invalid_rate"], 100 * st["accuracy"],
                         100 * st["accuracy_valid"]))
    for lang, m, n, e, ip, allm, valid in rows:
        print(f"{lang:<5}{m:<42}{n:>7,}{e:>7,}{ip:>7.2f}{allm:>8.2f}{valid:>8.2f}{allm-valid:>8.2f}")

    ns = {r[2] for r in rows}
    print(f"\nAll runs scored on the same population: {ns == {26389}} {sorted(ns)}")

    print("\nRuns where the two metrics differ by > 0.5 points "
          "(i.e. where the old denominator mattered):")
    for lang, m, n, e, ip, allm, valid in sorted(rows, key=lambda r: r[6] - r[5], reverse=True):
        if valid - allm > 0.5:
            print(f"  {lang} {m:<42} valid {valid:>6.2f} -> all-item {allm:>6.2f}  ({allm-valid:+.2f})")

    print("\nRanking difference between the two metrics (per prompt language):")
    for lang in ("en", "ur"):
        sub = [r for r in rows if r[0] == lang]
        a = [m for _, m, *_ in sorted(sub, key=lambda r: -r[6])]   # by valid-only
        b = [m for _, m, *_ in sorted(sub, key=lambda r: -r[5])]   # by all-item
        moved = [(m, a.index(m) + 1, b.index(m) + 1) for m in a if a.index(m) != b.index(m)]
        print(f"  [{lang}] {len(moved)} models rank differently under the reported metric")
        for m, i, j in moved:
            print(f"    {m:<42} valid #{i} -> all-item #{j}")

    print("\nBLOOMZ-3B / ur sanity check (audit's concrete contradiction):")
    st = evaluate(load(OUT / "ur" / "bigscience__bloomz-3b" / "predictions.json"))
    print(f"  scored={st['scored']:,} parseable={st['parseable']:,} "
          f"invalid={st['errors']:,} ({100*st['invalid_rate']:.1f}%) correct={st['correct']:,}")
    print(f"  acc among valid = {100*st['accuracy_valid']:.2f}%   "
          f"all-item acc = {100*st['accuracy']:.2f}%   <- REPORTED")
    print(f"  ceiling on all-item acc given the invalid rate = "
          f"{100*st['parseable']/st['scored']:.2f}%")

    print("\nError-type split of 'invalid' (model error vs unparseable text):")
    for lang in ("en", "ur"):
        for p in sorted((OUT / lang).glob("*/predictions.json")):
            recs = load(p)
            hard = soft = 0
            for r in recs:
                pred = r.get("prediction")
                if _is_empty_or_error(pred):
                    hard += 1
                    continue
                if parse_key(str(pred)) is None and parse_key_from_options(str(pred), r.get("options") or {}) is None:
                    soft += 1
            if hard or soft:
                print(f"  {lang} {p.parent.name:<42} empty/error={hard:<6,} unparseable={soft:<6,}")


# ── 6. paper claims that need arithmetic ─────────────────────────────────────

def claims():
    hdr("6. SPOT-CHECKS ON REPORTED DELTAS")
    print("Annotator demographics (n=17):")
    for k, v in [("bachelor's 47.1%", 8), ("master's 41.2%", 7), ("native 94.1%", 16)]:
        print(f"  {k:<20} nearest integer count: {v}/17 = {100*v/17:.4f}%")
    print(f"  'at least a bachelor's' 8+7 = 15/17 = {100*15/17:.4f}%  (paper: 88.3%)")

    print("\nGemini-3.5-Flash vs DeepSeek-V4-Flash (paper: 7.79 / 8.92):")
    print(f"  en: 90.20 - 82.41 = {90.20-82.41:.2f}")
    print(f"  ur: 90.34 - 81.42 = {90.34-81.42:.2f}")
    print("\nSTEM-Humanities gaps under Urdu prompt (paper: 12.50 for Gemini):")
    print(f"  Gemini-3.5-Flash: 97.81 - 85.31 = {97.81-85.31:.2f}")
    print(f"  DeepSeek-V4-Flash: 97.57 - 67.32 = {97.57-67.32:.2f}")
    print("\nDomain shares, final benchmark:")
    for d, n in [("Humanities", 11010), ("Social Sciences", 7968), ("STEM", 5113),
                 ("Other", 1365), ("Profession", 975)]:
        print(f"  {d:<18} {n:>7,} / 26,431 = {100*n/26431:.4f}%")
    print("\nSource retention (paper: 'BISE Multan shows the largest reduction'):")
    for s, raw, fin in [("Ustad 360", 23788, 11068), ("MCQTimes", 6099, 5918),
                        ("TestPointPK", 3619, 3502), ("ETest", 3102, 2783),
                        ("FBISE", 2406, 1459), ("ExamAunty", 643, 540),
                        ("GoTest", 566, 515), ("PakMCQs", 434, 414),
                        ("BISE Multan 2025", 440, 232)]:
        print(f"  {s:<20} {raw:>7,} -> {fin:>7,}   retained {100*fin/raw:>6.2f}%   "
              f"reduction {100-100*fin/raw:>6.2f}%")


SECTIONS = {
    "pool": lambda: candidate_pool(),
    "final": lambda: final_benchmark(),
    "flow": flow,
    "prox": lambda: prox_overlap(load(DATA / "26-eval" / "mcqs.json")),
    "eval": evaluation,
    "claims": claims,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", action="append", choices=sorted(SECTIONS), default=None)
    a = ap.parse_args()
    for name in (a.section or list(SECTIONS)):
        SECTIONS[name]()


if __name__ == "__main__":
    main()
