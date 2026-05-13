#!/usr/bin/env python3
"""Refresh the bundled data folders under ``web/``.

``web/`` is the single source of truth for the deployable site. Its
HTML/CSS/JS files are edited directly; only the bundled ``data/``
subfolders are regenerated from the pipeline outputs. This script
copies the latest pipeline data into:

  web/
  ├── annotator/data/      ← manifest + assignments + every batch file
  ├── admin/data/          ← manifest + assignments
  └── preview/data/        ← selected pipeline stages used by the preview

Re-run any time the pipeline regenerates:

    python scripts/build_site.py

Then ``git add web/ && git commit && git push``. GitHub Pages serves
from ``main`` branch, folder ``/web``.
"""

from __future__ import annotations
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
DATA = REPO_ROOT / "data"

SRC_BATCHING = DATA / "16-batching"
SRC_ASSIGNMENTS = DATA / "17-assignments" / "assignments.json"

PREVIEW_STAGES = ["!-final", "14-english-filtered", "15-subsampling", "16-batching"]


def refresh_dir(dst: Path) -> None:
    """Wipe `dst` and recreate it empty."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)


def copy_tree(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    n = 0
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, target)
            n += 1
    return n


def refresh_annotator() -> int:
    if not SRC_BATCHING.exists() or not SRC_ASSIGNMENTS.exists():
        raise SystemExit(f"missing {SRC_BATCHING} or {SRC_ASSIGNMENTS}")
    dst = WEB / "annotator" / "data"
    refresh_dir(dst)
    n = 0
    shutil.copy(SRC_BATCHING / "manifest.json", dst / "manifest.json"); n += 1
    shutil.copy(SRC_ASSIGNMENTS, dst / "assignments.json"); n += 1
    n += copy_tree(SRC_BATCHING / "batches", dst / "batches")
    return n


def refresh_admin() -> int:
    dst = WEB / "admin" / "data"
    refresh_dir(dst)
    n = 0
    if (SRC_BATCHING / "manifest.json").exists():
        shutil.copy(SRC_BATCHING / "manifest.json", dst / "manifest.json"); n += 1
    if SRC_ASSIGNMENTS.exists():
        shutil.copy(SRC_ASSIGNMENTS, dst / "assignments.json"); n += 1
    return n


def refresh_preview() -> int:
    dst = WEB / "preview" / "data"
    refresh_dir(dst)
    n = 0
    for stage in PREVIEW_STAGES:
        src = DATA / stage
        if src.exists():
            n += copy_tree(src, dst / stage)
    return n


def main() -> None:
    print(f"Refreshing web/ data folders ...\n")
    print(f"  annotator/data : {refresh_annotator()} files")
    print(f"  admin/data     : {refresh_admin()} files")
    print(f"  preview/data   : {refresh_preview()} files")

    total = sum(1 for _ in WEB.rglob("*") if _.is_file())
    print(f"\nweb/ now has {total} files total.")
    print()
    print("Commit and push to deploy:")
    print("  git add web/")
    print("  git commit -m \"refresh: web data\"")
    print("  git push")
    print()
    print("In GitHub repo settings → Pages → Source: main branch, folder /web.")


if __name__ == "__main__":
    main()
