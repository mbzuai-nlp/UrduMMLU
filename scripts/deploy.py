#!/usr/bin/env python3
"""Deploy the ``web/`` folder to the public mirror repo.

The private repo keeps the pipeline + source. The public repo
(``hasaniqbal777/urdu-mmlu-web``) is a deploy-only mirror containing
only the contents of ``web/`` at its root, served via GitHub Pages.

Usage:

    python scripts/deploy.py

Steps it performs:

    1. Clone the public mirror to a sibling directory (first run only).
    2. Pull latest from the mirror.
    3. Wipe everything in the mirror except ``.git``.
    4. Copy ``web/`` contents into the mirror's root.
    5. Commit (with the private-repo HEAD hash in the message) and push.

Override the mirror location with ``--clone-dir`` or change the
``DEFAULT_PUBLIC_REPO`` constant below if you ever rename the public
repo.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"

DEFAULT_PUBLIC_REPO = "git@github.com:hasaniqbal777/urdu-mmlu-web.git"
DEFAULT_CLONE_DIR = REPO_ROOT.parent / "urdu-mmlu-web"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = False) -> str:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if check and result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return (result.stdout or "").strip()


def short_head(repo_path: Path) -> str:
    return run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path, capture=True)


def ensure_clone(clone_dir: Path, public_repo: str) -> None:
    if clone_dir.exists() and (clone_dir / ".git").exists():
        return
    if clone_dir.exists():
        sys.exit(f"refusing to use existing non-git dir at {clone_dir}")
    print(f"Cloning {public_repo} → {clone_dir} (first deploy) ...")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", public_repo, str(clone_dir)])


def wipe_except_git(target: Path) -> None:
    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_web_into(target: Path) -> None:
    for child in WEB.iterdir():
        dst = target / child.name
        if child.is_dir():
            shutil.copytree(child, dst)
        else:
            shutil.copy(child, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clone-dir", default=str(DEFAULT_CLONE_DIR),
                        help=f"local clone of the public mirror (default: {DEFAULT_CLONE_DIR})")
    parser.add_argument("--repo", default=DEFAULT_PUBLIC_REPO,
                        help=f"public mirror URL (default: {DEFAULT_PUBLIC_REPO})")
    parser.add_argument("--message", default=None,
                        help="custom commit message (default: deploy: from main@<short hash>)")
    args = parser.parse_args()

    clone_dir = Path(args.clone_dir).resolve()
    if not WEB.exists():
        sys.exit(f"missing {WEB} — run scripts/build_site.py first")

    ensure_clone(clone_dir, args.repo)
    run(["git", "pull", "--ff-only"], cwd=clone_dir)

    print(f"\nWiping {clone_dir} (except .git) ...")
    wipe_except_git(clone_dir)

    print(f"Copying {WEB} → {clone_dir} ...")
    copy_web_into(clone_dir)

    run(["git", "add", "-A"], cwd=clone_dir)

    head = short_head(REPO_ROOT)
    message = args.message or f"deploy: from main@{head}"

    diff = run(["git", "diff", "--cached", "--shortstat"], cwd=clone_dir, capture=True)
    if not diff:
        print("\nNothing to deploy — public mirror already matches web/.")
        return

    run(["git", "commit", "-m", message], cwd=clone_dir)
    run(["git", "push"], cwd=clone_dir)

    print("\n✓ Deployed.")
    print(f"  public repo: {args.repo}")
    print(f"  message:     {message}")
    print()
    print("Don't forget to enable GitHub Pages on the public repo:")
    print("  Settings → Pages → Source: main / (root)")


if __name__ == "__main__":
    main()
