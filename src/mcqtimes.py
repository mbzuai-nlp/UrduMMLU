import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://mcqtimes.com/category/urdu/"
TOTAL_PAGES = 617
OUT_FILE = "data/mcqtimes_urdu.json"

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s

def page_url(page_num: int) -> str:
    if page_num == 1:
        return BASE_URL
    return f"{BASE_URL}page/{page_num}/"

def extract_page_data(page):
    # Click once so answers become visible/styled
    btn = page.locator("text=Show/Hide Answers").first
    if btn.count():
        try:
            btn.click(timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

    fieldsets = page.locator("fieldset.mcqs")
    data = []

    count = fieldsets.count()
    for i in range(count):
        fs = fieldsets.nth(i)

        # Domain / sub-category
        domain = ""
        try:
            domain = clean_text(fs.locator("legend .catitle").inner_text())
        except Exception:
            pass

        # Question
        question = ""
        try:
            question = clean_text(fs.locator("a.questiontxt").inner_text())
        except Exception:
            pass

        # Options
        option_labels = fs.locator("label")
        options = []
        correct_option = None
        correct_index = None

        label_count = option_labels.count()
        for j in range(label_count):
            label = option_labels.nth(j)

            # Option text
            text = ""
            try:
                # Preferred node from your HTML screenshot
                if label.locator(".ans_text").count():
                    text = clean_text(label.locator(".ans_text").inner_text())
                else:
                    text = clean_text(label.inner_text())
            except Exception:
                text = ""

            if not text:
                continue

            options.append(text)

            # Detect correct answer by rendered styling after toggle
            try:
                info = label.evaluate("""
                (el) => {
                    const st = getComputedStyle(el);
                    const before = getComputedStyle(el, '::before');
                    return {
                        bg: st.backgroundColor,
                        borderTop: st.borderTopColor,
                        borderRight: st.borderRightColor,
                        borderBottom: st.borderBottomColor,
                        borderLeft: st.borderLeftColor,
                        beforeBg: before.backgroundColor,
                        beforeContent: before.content,
                        color: st.color
                    };
                }
                """)

                vals = " ".join(str(v).lower() for v in info.values())

                # Heuristic: correct option becomes greenish after Show/Hide Answers
                if (
                    "rgb(223, 240, 216)" in vals or
                    "rgb(92, 184, 92)" in vals or
                    "rgb(76, 174, 76)" in vals or
                    "rgb(93, 184, 92)" in vals or
                    "✔" in vals or
                    "check" in vals
                ):
                    correct_option = text
                    correct_index = len(options) - 1
            except Exception:
                pass

        data.append({
            "domain": domain,
            "question": question,
            "options": options,
            "correct_option": correct_option,
            "correct_index": correct_index,
        })

    return data

def main():
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="ur-PK",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36")
        )
        page = context.new_page()

        for page_num in range(1, TOTAL_PAGES + 1):
            url = page_url(page_num)
            print(f"Scraping page {page_num}/{TOTAL_PAGES}: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                rows = extract_page_data(page)
                for row in rows:
                    row["page"] = page_num
                    row["source_url"] = url

                all_rows.extend(rows)

                # Save incrementally every page
                Path(OUT_FILE).write_text(
                    json.dumps(all_rows, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

            except Exception as e:
                print(f"Failed on page {page_num}: {e}")

        browser.close()

    print(f"Saved {len(all_rows)} MCQs to {OUT_FILE}")

if __name__ == "__main__":
    main()