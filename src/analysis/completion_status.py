#!/usr/bin/env python3
"""Completion status per annotator.

Reports, for every annotator in the current assignment:
  - how many of their assigned batches they've submitted
  - which batches are still missing
  - any extras (submitted batches NOT in their current assignment)

Usage:
    python src/analysis/completion_status.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSIGN = REPO_ROOT / "data" / "18-assignments" / "assignments.json"
ANNOT_DIR = REPO_ROOT / "data" / "19-annotated"
MANIFEST = REPO_ROOT / "data" / "17-batching" / "manifest.json"

BATCH_FILE_RE = re.compile(r"^([A-Za-z]+)__batch_(\d{3})\.json$")


def submitted_batches(folder: Path) -> tuple[str, set[str]]:
    """Return (detected annotator name, set of batch_ids) for a folder."""
    files = [f for f in folder.iterdir() if f.suffix == ".json"]
    detected: str | None = None
    bids: set[str] = set()
    for f in files:
        m = BATCH_FILE_RE.match(f.name)
        if not m:
            continue
        if detected is None:
            detected = m.group(1)
        bids.add(f"batch_{m.group(2)}")
    return detected or folder.name, bids


def main() -> None:
    assignments = json.load(open(ASSIGN, encoding="utf-8"))["assignments"]
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    primary_sub = {b["id"]: b["primary_subdomain"] for b in manifest["batches"]}

    # Map: detected_name -> folder
    name_to_folder: dict[str, Path] = {}
    for folder in sorted(ANNOT_DIR.iterdir()):
        if not folder.is_dir():
            continue
        name, _ = submitted_batches(folder)
        name_to_folder[name] = folder

    print(f"{'annotator':<10} {'done':>4} {'assg':>4} {'left':>4} {'extras':>6}  remaining batches")
    print("-" * 90)
    total_left = 0
    total_extras = 0
    for name in sorted(assignments.keys()):
        assigned = set(assignments[name])
        folder = name_to_folder.get(name)
        if folder is None:
            done: set[str] = set()
        else:
            _, done = submitted_batches(folder)

        left = sorted(assigned - done)
        extras = sorted(done - assigned)
        total_left += len(left)
        total_extras += len(extras)
        short_left = ", ".join(
            f"{b.replace('batch_', '')}({primary_sub.get(b, '?')})" for b in left[:6]
        )
        if len(left) > 6:
            short_left += f" …+{len(left) - 6}"
        print(
            f"{name:<10} {len(done & assigned):>4} {len(assigned):>4} {len(left):>4} {len(extras):>6}  {short_left}"
        )
    print("-" * 90)
    print(f"Total remaining: {total_left}    Total extras: {total_extras}")


if __name__ == "__main__":
    main()
