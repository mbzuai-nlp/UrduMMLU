#!/usr/bin/env python3
"""Stage 17 — group-aware dual-annotation assignment.

Every batch is assigned to exactly **two** different annotators, but the
pair is chosen by *role* and subdomain, not pure round-robin:

  - **Chemistry / Biology** batches go to the **two doctors only**;
    they pair with each other.
  - **Arts** batches (art-and-drawing, urdu-literature, urdu-language,
    urdu-grammar) have the **arts specialist** as one annotator; the
    partner is chosen by load balance from anyone else (no author-
    pairing rule violation).
  - **All other batches** are dealt to the least-loaded valid pair.

Pairing rule across all batches: an **author** is never paired with
another author. Their partner can be anyone non-author (group-1,
doctors, arts specialist, or general). Load is balanced on **MCQ
count**, not batch count, so annotators end up with roughly equal
review volume even though batches differ in size.

Group definitions are read from ``src/assignment/groups.json``. Edit
that file to change team membership without touching this script.

Usage:
    python src/assignment/assign.py [--groups path/to/groups.json]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "data" / "17-batching" / "manifest.json"
DST_PATH = REPO_ROOT / "data" / "18-assignments" / "assignments.json"
DEFAULT_GROUPS = Path(__file__).resolve().parent / "groups.json"
SEED = 42


def load_groups(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["authors"] = list(cfg.get("authors", []))
    cfg["group_1"] = list(cfg.get("group_1", []))
    cfg["doctors"] = list(cfg.get("doctors", []))
    cfg["arts_specialist"] = list(cfg.get("arts_specialist", []))
    cfg["general"] = list(cfg.get("general", []))
    cfg["chembio_subdomains"] = set(cfg.get("chembio_subdomains", []))
    cfg["arts_subdomains"] = set(cfg.get("arts_subdomains", []))
    cfg["subdomain_specialists"] = {
        sub: list(names)
        for sub, names in cfg.get("subdomain_specialists", {}).items()
    }
    cfg["all"] = (
        cfg["authors"] + cfg["group_1"] + cfg["doctors"]
        + cfg["arts_specialist"] + cfg["general"]
    )
    return cfg


def is_valid_pair(a: str, b: str, groups: dict) -> bool:
    """No two authors on the same batch; everything else is allowed."""
    if a == b:
        return False
    authors = set(groups["authors"])
    if a in authors and b in authors:
        return False
    return True


def by_load(loads: dict[str, int], candidates) -> list[str]:
    return sorted(candidates, key=lambda x: (loads[x], x))


def pick_two(loads, candidates, groups, cap=None):
    """Pick 2 least-loaded valid annotators. If `cap` is given, skip anyone
    at or above the cap; relax it only if no valid pair fits."""
    ordered = by_load(loads, candidates)
    if cap is not None:
        for i, a in enumerate(ordered):
            if loads[a] >= cap:
                continue
            for b in ordered[i + 1:]:
                if loads[b] >= cap:
                    continue
                if is_valid_pair(a, b, groups):
                    return a, b
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if is_valid_pair(a, b, groups):
                return a, b
    raise SystemExit(f"no valid pair found among {candidates}")


def pick_partner(loads, anchor, candidates, groups, cap=None):
    """Pick least-loaded valid partner for `anchor`. Cap acts like `pick_two`."""
    if cap is not None:
        for b in by_load(loads, candidates):
            if b == anchor or loads[b] >= cap:
                continue
            if is_valid_pair(anchor, b, groups):
                return b
    for b in by_load(loads, candidates):
        if b == anchor:
            continue
        if is_valid_pair(anchor, b, groups):
            return b
    raise SystemExit(f"no valid partner for {anchor}")


def assign(manifest: dict, groups: dict) -> dict:
    chembio = groups["chembio_subdomains"]
    arts_subs = groups["arts_subdomains"]
    doctors = groups["doctors"]
    arts_specialists = groups["arts_specialist"]
    specialists = groups["subdomain_specialists"]
    all_set = set(groups["all"])

    if not doctors:
        raise SystemExit("at least 1 doctor required")

    # Bucket batches by primary subdomain. Order of priority:
    # chem/bio > arts > subdomain specialist > general.
    batches = manifest["batches"]
    chembio_b, arts_b, specialist_b, other_b = [], [], [], []
    for b in batches:
        sub = b["primary_subdomain"]
        if sub in chembio:
            chembio_b.append(b)
        elif sub in arts_subs:
            arts_b.append(b)
        elif sub in specialists:
            specialist_b.append(b)
        else:
            other_b.append(b)

    # Sort each phase by batch size DESC so the largest batches are placed
    # first while load-balancing has the most room to absorb the variance —
    # standard longest-processing-time heuristic.
    rng = random.Random(SEED)
    for bucket in (chembio_b, arts_b, specialist_b, other_b):
        rng.shuffle(bucket)
        bucket.sort(key=lambda x: -x["size"])

    slots: dict[str, list[str]] = {a: [] for a in groups["all"]}
    loads: dict[str, int] = {a: 0 for a in groups["all"]}

    # Target MCQ load per annotator. Total MCQ-slots / N annotators. The
    # picker uses this as a soft cap: it skips anyone already at-or-above
    # the cap, but relaxes when no valid pair fits (e.g. author-must-pair-
    # with-group-1 may force one side over the cap).
    total_mcq_slots = sum(b["size"] for b in batches) * 2
    cap = (total_mcq_slots + len(groups["all"]) - 1) // len(groups["all"])

    def place(name: str, batch: dict) -> None:
        slots[name].append(batch["id"])
        loads[name] += batch["size"]

    # Phase 1 — chem/bio: ONE doctor on every batch (primary). The partner
    # is load-balanced across everyone else, so doctors don't pair with
    # each other every time and chem/bio review load spreads across the team.
    for b in chembio_b:
        anchor = by_load(loads, doctors)[0]
        place(anchor, b)
        partner = pick_partner(loads, anchor, all_set, groups, cap=cap)
        place(partner, b)

    # Phase 2 — arts specialist on every arts batch, partner from anyone else
    for b in arts_b:
        if not arts_specialists:
            a, c = pick_two(loads, all_set, groups, cap=cap)
            place(a, b)
            place(c, b)
            continue
        anchor = arts_specialists[0]
        place(anchor, b)
        partner = pick_partner(loads, anchor, all_set, groups, cap=cap)
        place(partner, b)

    # Phase 3 — subdomain specialists (e.g. mathematics → Hasan/Sarfraz/Ahmer).
    # One annotator must be from the specialist pool; the partner is chosen
    # by load balance among everyone else (subject to the author-pairing rule).
    for b in specialist_b:
        pool = specialists[b["primary_subdomain"]]
        anchor = by_load(loads, pool)[0]
        place(anchor, b)
        partner = pick_partner(loads, anchor, all_set, groups, cap=cap)
        place(partner, b)

    # Phase 4 — everything else: 2 lowest-loaded valid annotators
    for b in other_b:
        a, c = pick_two(loads, all_set, groups, cap=cap)
        place(a, b)
        place(c, b)

    return slots


def report(slots: dict, manifest: dict, groups: dict) -> None:
    print(f"{'annotator':<14} {'group':<10} {'batches':>8} {'sample subs':<40}")
    print("-" * 80)
    group_lookup = {}
    for g in ("authors", "group_1", "doctors", "arts_specialist", "general"):
        for n in groups[g]:
            group_lookup[n] = g.replace("_", "-")

    primary = {b["id"]: b["primary_subdomain"] for b in manifest["batches"]}

    for name in groups["all"]:
        bids = slots[name]
        sub_counts = Counter(primary[b] for b in bids).most_common(4)
        sub_str = ", ".join(f"{s}({n})" for s, n in sub_counts) or "—"
        print(f"  {name:<12} {group_lookup[name]:<10} {len(bids):>8}  {sub_str}")

    print()
    # Sanity: every batch covered twice
    cover = Counter()
    for bids in slots.values():
        for b in bids:
            cover[b] += 1
    bad = [b for b, c in cover.items() if c != 2]
    if bad:
        print(f"WARNING: {len(bad)} batches not exactly dual-covered: {bad[:5]} ...")
    else:
        print(f"✓ all {len(cover)} batches covered exactly twice")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, default=DEFAULT_GROUPS,
                        help=f"path to groups config (default: {DEFAULT_GROUPS})")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        raise SystemExit(f"missing {MANIFEST_PATH} — run src/batching/build.py first")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    groups = load_groups(args.groups)
    slots = assign(manifest, groups)

    report(slots, manifest, groups)

    out = {
        "seed": SEED,
        "groups": {k: groups[k] for k in (
            "authors", "group_1", "doctors", "arts_specialist", "general",
        )},
        "chembio_subdomains":     sorted(groups["chembio_subdomains"]),
        "arts_subdomains":        sorted(groups["arts_subdomains"]),
        "subdomain_specialists":  groups["subdomain_specialists"],
        "n_annotators": len(groups["all"]),
        "n_batches":    manifest["batch_count"],
        "dual_annotation": True,
        "annotators":  sorted(groups["all"]),
        "assignments": {a: sorted(bids) for a, bids in slots.items()},
    }
    DST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DST_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
    print(f"\nWrote {DST_PATH}")


if __name__ == "__main__":
    main()
