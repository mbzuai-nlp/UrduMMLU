import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://pakmcqs.com/category/urdu-general-knowledge"
TOTAL_PAGES = 46
OUTPUT_FILE = "pakmcqs_urdu_general_knowledge.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_page_url(page_num):
    return BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}"


def parse_options(excerpt_div):
    text = excerpt_div.get_text("\n", strip=True)
    lines = [clean_text(x) for x in text.split("\n") if clean_text(x)]

    options = []
    correct_option = None
    correct_index = None
    submitted_by = None

    for line in lines:
        if re.match(r"^[A-D][\.\)]\s*", line):
            option_text = re.sub(r"^[A-D][\.\)]\s*", "", line).strip()
            options.append(option_text)

        elif line.lower().startswith("submitted by:"):
            submitted_by = clean_text(line.split(":", 1)[1])

    # correct option = bold/strong text inside excerpt
    strong_tags = excerpt_div.find_all("strong")
    for st in strong_tags:
        st_text = clean_text(st.get_text(" ", strip=True))
        if re.match(r"^[A-D][\.\)]\s*", st_text):
            candidate = re.sub(r"^[A-D][\.\)]\s*", "", st_text).strip()
            if candidate in options:
                correct_option = candidate
                correct_index = options.index(candidate)
                break

    return options, correct_option, correct_index, submitted_by


def scrape_page(session, page_num):
    url = get_page_url(page_num)
    print(f"Scraping page {page_num}/{TOTAL_PAGES}: {url}")

    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []

    # More reliable than article.post
    for h2 in soup.select("h2.is-title.post-title, h2.is-title"):
        a = h2.find("a", href=True)
        if not a:
            continue

        question = clean_text(a.get_text(" ", strip=True))
        detail_url = urljoin(url, a["href"])

        # walk forward until we find the excerpt block for this question
        container = h2.parent
        excerpt_div = None

        for _ in range(6):
            if not container:
                break
            excerpt_div = container.find("div", class_="excerpt")
            if excerpt_div:
                break
            container = container.parent

        if not excerpt_div:
            # fallback: next excerpt after this h2 in document order
            excerpt_div = h2.find_next("div", class_="excerpt")

        if not excerpt_div:
            continue

        options, correct_option, correct_index, submitted_by = parse_options(excerpt_div)

        if question and options:
            rows.append({
                "domain": "Urdu General Knowledge",
                "question": question,
                "options": options,
                "correct_option": correct_option,
                "correct_index": correct_index,
                "page": page_num,
                "source_url": detail_url,
                "submitted_by": submitted_by,
            })

    return rows


def main():
    all_data = []

    with requests.Session() as session:
        for page_num in range(1, TOTAL_PAGES + 1):
            try:
                items = scrape_page(session, page_num)
                print(f"  -> found {len(items)} MCQs")
                all_data.extend(items)

                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=2)

                time.sleep(1)

            except Exception as e:
                print(f"Failed on page {page_num}: {e}")

    print(f"Saved {len(all_data)} MCQs to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()