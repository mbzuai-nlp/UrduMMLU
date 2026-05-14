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

Pairing rule across all batches: an **author** can only be paired with
someone from **group-1** (never with another author and never with a
non-group-1 non-author). The doctors and the arts specialist are
otherwise free to pick up batches when their load is below the running
average.

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
MANIFEST_PATH = REPO_ROOT / "data" / "16-batching" / "manifest.json"
DST_PATH = REPO_ROOT / "data" / "17-assignments" / "assignments.json"
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
    cfg["all"] = (
        cfg["authors"] + cfg["group_1"] + cfg["doctors"]
        + cfg["arts_specialist"] + cfg["general"]
    )
    return cfg


def is_valid_pair(a: str, b: str, groups: dict) -> bool:
    """Authors can only pair with group-1; no two authors on the same batch."""
    if a == b:
        return False
    authors = set(groups["authors"])
    group_1 = set(groups["group_1"])
    a_author = a in authors
    b_author = b in authors
    if a_author and b_author:
        return False
    if a_author and b not in group_1:
        return False
    if b_author and a not in group_1:
        return False
    return True


def by_load(slots: dict[str, list], candidates) -> list[str]:
    return sorted(candidates, key=lambda x: (len(slots[x]), x))


def pick_two(slots, candidates, groups):
    ordered = by_load(slots, candidates)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if is_valid_pair(a, b, groups):
                return a, b
    raise SystemExit(f"no valid pair found among {candidates}")


def pick_partner(slots, anchor, candidates, groups):
    for b in by_load(slots, candidates):
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
    all_set = set(groups["all"])

    if len(doctors) < 2:
        raise SystemExit("at least 2 doctors required")
    d1, d2 = doctors[0], doctors[1]

    # Bucket batches by primary subdomain
    batches = manifest["batches"]
    chembio_b = [b for b in batches if b["primary_subdomain"] in chembio]
    arts_b    = [b for b in batches if b["primary_subdomain"] in arts_subs]
    other_b   = [b for b in batches if b not in chembio_b and b not in arts_b]

    rng = random.Random(SEED)
    rng.shuffle(chembio_b)
    rng.shuffle(arts_b)
    rng.shuffle(other_b)

    slots: dict[str, list[str]] = {a: [] for a in groups["all"]}

    # Phase 1 — doctors handle every chem/bio batch, paired with each other
    for b in chembio_b:
        slots[d1].append(b["id"])
        slots[d2].append(b["id"])

    # Phase 2 — arts specialist on every arts batch, partner from anyone else
    # (no doctor allowed unless they have spare capacity — handled by load balance)
    for b in arts_b:
        if not arts_specialists:
            a, c = pick_two(slots, all_set, groups)
            slots[a].append(b["id"])
            slots[c].append(b["id"])
            continue
        anchor = arts_specialists[0]
        slots[anchor].append(b["id"])
        partner = pick_partner(slots, anchor, all_set, groups)
        slots[partner].append(b["id"])

    # Phase 3 — everything else: 2 lowest-loaded valid annotators
    for b in other_b:
        a, c = pick_two(slots, all_set, groups)
        slots[a].append(b["id"])
        slots[c].append(b["id"])

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
        "chembio_subdomains": sorted(groups["chembio_subdomains"]),
        "arts_subdomains":    sorted(groups["arts_subdomains"]),
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
