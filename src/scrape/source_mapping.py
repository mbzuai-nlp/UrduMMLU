"""
Adds a 'source' key to each MCQ in mcqs_with_answers.json based on source_url.
Writes the updated data back to the same file.
"""

import json
from urllib.parse import urlparse

INPUT_FILE = "data/mcqs_with_answers.json"

SOURCE_MAP = {
    "mcqtimes.com": "mcqtimes",
    "pakmcqs.com": "pakmcqs",
    "testpointpk.com": "testpointpk",
    "etest.com.pk": "etest",
    "gotest.com.pk": "gotest",
    "examaunty.com": "examaunty",
}


def resolve_source(url: str) -> str:
    if not url:
        return ""
    netloc = urlparse(url).netloc.lower()
    # Strip www. prefix if present
    netloc = netloc.removeprefix("www.")
    return SOURCE_MAP.get(netloc, "")


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    unmatched = set()
    for item in data:
        source_url = item.get("source_url", "")
        item["source"] = resolve_source(source_url)
        if not item["source"] and source_url:
            unmatched.add(source_url)

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    matched = sum(1 for item in data if item["source"])
    print(f"Done. {matched}/{len(data)} items got a source.")
    if unmatched:
        print(f"Unmatched URLs ({len(unmatched)}):")
        for url in sorted(unmatched):
            print(f"  {url}")


if __name__ == "__main__":
    main()
