"""
Apply subdomain merges and removals to clean_data JSONs.

Changes:
  - Remove arabic_language and punjabi_language
  - social_studies          → pakistan_studies
  - current_affairs
    + international_affairs → current_and_international_affairs
  - tarjamatul_quran        → islamic_studies

Run from repo root:
    python scrape/subdomain_merging.py
"""

import json
from collections import Counter
from pathlib import Path

FILES = [
    Path("clean_data/mcqs_with_answers.json"),
    Path("clean_data/mcqs_without_answers.json"),
]

REMOVE = {"arabic_language", "punjabi_language"}

MERGE = {
    "social_studies":       "pakistan_studies",
    "current_affairs":      "current_and_international_affairs",
    "international_affairs":"current_and_international_affairs",
    "tarjamatul_quran":     "islamic_studies",
}


def apply(item: dict) -> dict | None:
    sub = item.get("subdomain", "")
    if sub in REMOVE:
        return None
    item["subdomain"] = MERGE.get(sub, sub)
    return item


def main():
    for path in FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        before = len(data)
        processed = [apply(item) for item in data]
        data = [item for item in processed if item is not None]
        removed = before - len(data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n{path.name}  ({before} → {len(data)}, removed {removed})")
        dist = Counter(f"{i['domain']} / {i['subdomain']}" for i in data)
        for key, cnt in sorted(dist.items(), key=lambda x: (x[0].split(" / ")[0], -x[1])):
            print(f"  {cnt:>5}  {key}")

    print("\nDone.")


if __name__ == "__main__":
    main()
