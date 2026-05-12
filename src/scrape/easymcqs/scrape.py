import requests
import json
import os
import re

URLS = [
    "https://www.easymcqs.com/2019/11/ppsc-urdu-general-knowledge-mcqs-quiz.html",
    "https://www.easymcqs.com/2019/11/kppsc-urdu-general-knowledge-mcqs-quiz.html",
    "https://www.easymcqs.com/2019/11/spsc-urdu-general-knowledge-mcqs.html",
    "https://www.easymcqs.com/2019/11/urdu-general-knowledge-fpsc-mcqs-with.html",
    "https://www.easymcqs.com/2019/11/basic-urdu-general-knowledge-mcqs-quiz.html",
    "https://www.easymcqs.com/2019/11/nts-test-urdu-grammar-mcqs-with-answers.html",
    "https://www.easymcqs.com/2019/11/objective-type-urdu-general-knowledge.html",
    "https://www.easymcqs.com/2019/11/ppsc-urdu-mcqs-competitive-exams-test.html",
    "https://www.easymcqs.com/2019/11/educators-urdu-mcqs-quiz-test.html",
    "https://www.easymcqs.com/2019/11/urdu-mcqs-for-public-service-commission.html",
]

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcqs.json")
ANSWER_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}


def extract_domain(html):
    matches = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL)
    for m in matches:
        text = re.sub(r'<[^>]+>', '', m).strip()
        if text and 'advertisement' not in text.lower() and ('mcq' in text.lower() or 'urdu' in text.lower()):
            return text
    return None


def parse_mcqs(html):
    domain = extract_domain(html)
    questions = []
    # Split by each question div
    blocks = html.split('images_solve-quiz_div')

    for block in blocks[1:]:  # skip first (before any question)
        # Extract question number and text
        q_match = re.search(r'mcqslistings">\s*Q\.(\d+):\s*</span>(.*?)<br', block, re.DOTALL)
        if not q_match:
            continue

        q_num = int(q_match.group(1))
        q_text = re.sub(r'<[^>]+>', '', q_match.group(2)).strip()

        # Extract options — only from the first <ol> to avoid footer junk
        ol_match = re.search(r'<ol>(.*?)</ol>', block, re.DOTALL)
        if not ol_match:
            continue
        options = re.findall(r'<li>(.*?)</li>', ol_match.group(1))
        options = [re.sub(r'<[^>]+>', '', o).strip() for o in options]

        # Extract correct answer
        ans_match = re.search(r'ans_frmt">\s*([A-D])\s*<', block)
        correct_answer = ans_match.group(1) if ans_match else None
        correct_index = ANSWER_MAP.get(correct_answer)

        q = {
            "question_number": q_num,
            "question": q_text,
            "options": options,
            "correct_answer": correct_answer,
            "correct_index": correct_index,
        }
        if domain:
            q["domain"] = domain
        questions.append(q)

    return questions


def main():
    all_mcqs = []

    for i, url in enumerate(URLS, 1):
        print(f"Scraping Test {i}: {url}")
        resp = requests.get(url)
        resp.encoding = 'utf-8'
        questions = parse_mcqs(resp.text)
        for q in questions:
            q["source"] = f"test_{i}"
            q["url"] = url
        all_mcqs.extend(questions)
        print(f"  → {len(questions)} questions")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_mcqs, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(all_mcqs)} total questions saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
