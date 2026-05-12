#!/usr/bin/env python3
"""
Merge all questions_gemini-3-flash-preview.json files found (recursively)
inside a given folder into a single JSON file named after that folder.

Usage:
  python merge_questions.py --input pipeline_output/BISE_Multan_25
      → writes  pipeline_output/BISE_Multan_25.json

  python merge_questions.py --input pipeline_output/fbise/2024
      → writes  pipeline_output/fbise/2024.json

  python merge_questions.py --input output_questions/SSC_1A25_QP
      → writes  output_questions/SSC_1A25_QP.json

  # Override the output path explicitly
  python merge_questions.py --input pipeline_output/BISE_Multan_25 --output merged/all.json

  # Use a different source filename pattern
  python merge_questions.py --input pipeline_output/BISE_Multan_25 \
      --filename questions_claude-sonnet-4-6.json
"""

import argparse
import json
import sys
from pathlib import Path


FILENAME = "questions_gemini-3-flash-preview.json"


def find_question_files(root: Path, filename: str) -> list[Path]:
    return sorted(root.rglob(filename))


def merge(files: list[Path]) -> list[dict]:
    merged = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [WARN] Skipping {f}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"  [WARN] Skipping {f}: expected a JSON list, got {type(data).__name__}", file=sys.stderr)
            continue
        merged.extend(data)
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge all question JSON files inside a folder into one.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", required=True,
        help="Folder to scan recursively for question JSON files.",
    )
    parser.add_argument(
        "--output",
        help="Output file path. Defaults to <parent>/<folder_name>.json.",
    )
    parser.add_argument(
        "--filename", default=FILENAME,
        help=f"Filename to search for inside subfolders (default: {FILENAME}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.is_dir():
        print(f"Error: '{input_path}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else input_path.parent / f"{input_path.name}.json"
    )

    files = find_question_files(input_path, args.filename)
    if not files:
        print(f"No '{args.filename}' files found under: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} file(s) under: {input_path}")
    for f in files:
        print(f"  {f.relative_to(input_path)}")

    merged = merge(files)
    print(f"\nTotal questions: {len(merged)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved → {output_path}")


if __name__ == "__main__":
    main()
