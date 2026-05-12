#!/usr/bin/env python3
import json
import sys
from pathlib import Path

TARGET_FILENAME = "questions_gemini-3-flash-preview.json"

REQUIRED_KEYS_IN_ORDER = [
    "question_number",
    "question",
    "options",
    "has_image",
    "image_bbox",
    "domain",
    "subdomain",
    "correct_option",
    "correct_index",
    "level",
    "page",
    "source_url",
    "source_image",
    "folder",
    "provider",
    "model",
]


def index_to_letters(idx: int) -> str:
    """Convert 0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA, ..."""
    result = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def normalize_options(options):
    if isinstance(options, dict):
        return dict(options)

    if isinstance(options, list):
        normalized = {}
        for idx, value in enumerate(options):
            normalized[index_to_letters(idx)] = value
        return normalized

    return {}


def normalize_item(item):
    if not isinstance(item, dict):
        return None

    normalized = {
        "question_number": item.get("question_number", None),
        "question": item.get("question", ""),
        "options": normalize_options(item.get("options", [])),
        "has_image": bool(item.get("has_image", False)),
        "image_bbox": item.get("image_bbox", None),
        "domain": item.get("domain", ""),
        "subdomain": item.get("subdomain", ""),
        "correct_option": item.get("correct_option", None),
        "correct_index": item.get("correct_index", None),
        "level": item.get("level", ""),
        "page": item.get("page", None),
        "source_url": item.get("source_url", ""),
        "source_image": item.get("source_image", ""),
        "folder": item.get("folder", ""),
        "provider": item.get("provider", "gemini"),
        "model": item.get("model", "gemini-3-flash-preview"),
    }

    ordered = {}
    for key in REQUIRED_KEYS_IN_ORDER:
        ordered[key] = normalized[key]
    return ordered


def process_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"Skipping non-list JSON: {file_path}")
        return

    normalized_data = []
    for item in data:
        normalized_item = normalize_item(item)
        if normalized_item is not None:
            normalized_data.append(normalized_item)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(normalized_data, f, ensure_ascii=False, indent=2)

    print(f"Updated: {file_path} ({len(normalized_data)} items)")


def find_target_files(root: Path):
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.name == TARGET_FILENAME
    )


def main():
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python update_questions_json.py <root_folder_or_file>")
        sys.exit(1)

    root = Path(sys.argv[1]).expanduser().resolve()

    if not root.exists():
        print(f"Error: path does not exist: {root}")
        sys.exit(1)

    if root.is_file():
        if root.name != TARGET_FILENAME:
            print(f"Error: file must be named {TARGET_FILENAME}")
            sys.exit(1)
        files = [root]
    else:
        files = find_target_files(root)

    if not files:
        print(f"No files named '{TARGET_FILENAME}' found under: {root}")
        sys.exit(0)

    print(f"Found {len(files)} matching file(s)\n")

    for file_path in files:
        try:
            process_file(file_path)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()