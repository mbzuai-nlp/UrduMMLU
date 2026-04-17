import argparse
import base64
import io
import json
import os
import re
import time
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_ROOT = BASE_DIR / "raw_data" / "SSC_1A25_QP_images"
CLASSIFICATIONS_ROOT = BASE_DIR / "output" / "SSC_1A25_QP"
QUESTIONS_ROOT = BASE_DIR / "output_questions" / "SSC_1A25_QP"

MAX_IMAGE_BYTES = 5 * 1024 * 1024

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3-flash-preview"

REQUEST_DELAY_SECONDS = 1.5
RETRY_LIMIT = 5

EXTRACTOR_PROMPT = """You are an expert OCR system for Urdu exam papers.

Extract ALL multiple choice questions from this image.

IMPORTANT LAYOUT NOTES:
- This is an Urdu exam bubble sheet. Text reads RIGHT to LEFT.
- Some pages have BOTH English and Urdu versions of the same question side by side. Extract ONLY the Urdu text. Ignore the English completely.
- Each row in the table is one MCQ. The RIGHT-MOST column contains the question text.
- Some questions contain a verse (شعر) or quote followed by a question about it. The verse and the question are in the SAME cell. Read the verse first, then the question. Keep them together but clearly separated.
  Example format: "سفید اس کا سیاہ اس کا، نفس نفس ہے گواہ اس کا / جو شعلہ جاں جلا رہا ہے، وہی خدا ہے — اس شعر میں کون سی صنعت استعمال ہوئی ہے؟"
- The option columns (الف، ب، ج، د or A, B, C, D) are to the LEFT of the question column.

For each question, extract:
1. Question number
2. The full question text in Urdu only (including any verse/quote that is part of the question)
3. All answer options in Urdu only.

Return ONLY a JSON array, no other text:
[
  {
    "question_number": 1,
    "question": "...",
    "options": ["...", "...", "...", "..."],
    "has_image": false,
    "image_bbox": null
  }
]

If has_image is true, set image_bbox to [x_min, y_min, x_max, y_max] as normalized coordinates (0.0 to 1.0) relative to the full page image, representing the bounding box of the image/diagram/figure associated with that question.
If has_image is false, set image_bbox to null.

Rules:
- ONLY extract Urdu text. If a question or option has both English and Urdu, keep only the Urdu.
- Extract Urdu text faithfully. Do not translate or paraphrase.
- If options use A/B/C/D labels, map them to الف/ب/ج/د.
- Use " — " (em dash) to separate verse/quote from the question about it.
- If you cannot clearly read or understand any part of a question or its options, SKIP that question entirely. Do NOT guess or hallucinate text. Only include questions you can read with high confidence.
- Return valid JSON only. No markdown, no code blocks, no explanation.
"""


def encode_image(path: str) -> tuple[str, str]:
    ext = os.path.splitext(path)[1].lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    with open(path, "rb") as f:
        data = f.read()

    if len(data) <= MAX_IMAGE_BYTES:
        return base64.standard_b64encode(data).decode("utf-8"), media_type

    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    quality = 85
    while quality >= 30:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
        quality -= 10

    img.thumbnail((max(1, img.width // 2), max(1, img.height // 2)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


def extract_anthropic(image_path: str, model: str):
    import anthropic

    client = anthropic.Anthropic()
    b64, media_type = encode_image(image_path)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                },
                {"type": "text", "text": EXTRACTOR_PROMPT},
            ],
        }],
    )
    return response.content[0].text


def extract_openai(image_path: str, model: str):
    import openai

    client = openai.OpenAI()
    b64, media_type = encode_image(image_path)

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{b64}"},
                },
                {"type": "text", "text": EXTRACTOR_PROMPT},
            ],
        }],
    )
    return response.choices[0].message.content


def extract_gemini(image_path: str, model: str):
    from google import genai

    client = genai.Client()
    b64, media_type = encode_image(image_path)

    response = client.models.generate_content(
        model=model,
        contents=[
            {"inline_data": {"mime_type": media_type, "data": b64}},
            EXTRACTOR_PROMPT,
        ],
    )
    return response.text


PROVIDERS = {
    "anthropic": extract_anthropic,
    "openai": extract_openai,
    "gemini": extract_gemini,
}


def parse_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Model response is not a JSON array")

    normalized = []
    for item in data:
        if not isinstance(item, dict):
            continue

        question_number = item.get("question_number")
        question = item.get("question")
        options = item.get("options")
        has_image = item.get("has_image", False)
        image_bbox = item.get("image_bbox", None)

        if question_number is None or not isinstance(question, str) or not isinstance(options, list):
            continue

        normalized.append({
            "question_number": question_number,
            "question": question.strip(),
            "options": [str(opt).strip() for opt in options],
            "has_image": bool(has_image),
            "image_bbox": image_bbox if has_image else None,
        })

    return normalized


def sanitize_model_name(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def get_questions_file(folder_name: str, model: str) -> Path:
    safe_model = sanitize_model_name(model)
    return QUESTIONS_ROOT / folder_name / f"questions_{safe_model}.json"


def load_questions(folder_name: str, model: str) -> list[dict]:
    path = get_questions_file(folder_name, model)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data if isinstance(data, list) else []


def save_questions(questions: list[dict], folder_name: str, model: str) -> None:
    path = get_questions_file(folder_name, model)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)


def extract_page_number(filename: str) -> int:
    # Handles: name_page_0017.png  name_page-0017.jpg  name-page-0017.jpg
    m = re.search(r'[_-]page[_-](\d+)', filename, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: last digit sequence before the extension
    m = re.search(r'(\d+)\.[^.]+$', filename)
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract page number from filename: {filename}")


def get_images(image_dir: Path) -> dict[str, Path]:
    images = {}
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for path in image_dir.glob(ext):
            images[path.name] = path
    return dict(sorted(images.items()))


def load_classifications(classifications_file: Path) -> dict:
    if not classifications_file.exists():
        return {}

    with open(classifications_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data if isinstance(data, dict) else {}


def get_existing_pages(all_questions: list[dict]) -> set[int]:
    pages = set()
    for q in all_questions:
        page = q.get("page")
        if isinstance(page, int):
            pages.add(page)
    return pages


def retry_extract(extract_fn, image_path: str, model: str, retries: int = RETRY_LIMIT) -> str:
    for attempt in range(retries):
        try:
            return extract_fn(image_path, model=model)
        except Exception as e:
            error_text = str(e).lower()

            if "429" in error_text or "rate limit" in error_text or "resource exhausted" in error_text:
                wait_time = min(60, 2 ** attempt)
                print(f"    Rate limited for {os.path.basename(image_path)}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

            raise

    raise RuntimeError(f"Failed after retries: {image_path}")


def process_folder(folder_name: str, image_dir: Path, classifications_file: Path, provider: str, model: str, max_pages: int | None) -> None:
    extract_fn = PROVIDERS[provider]

    print(f"\n=== Processing folder: {folder_name} ===")
    print(f"Image dir: {image_dir}")
    print(f"Classifications file: {classifications_file}")

    if not classifications_file.exists():
        print("  No classifications found for this folder. Skipping.")
        return

    classifications = load_classifications(classifications_file)
    images_by_name = get_images(image_dir)

    mcq_pages = []
    domains = {}

    for name, entry in classifications.items():
        label = entry["label"] if isinstance(entry, dict) else entry
        if label == "urdu_mcq":
            if name in images_by_name:
                mcq_pages.append(name)
                if isinstance(entry, dict) and "domain" in entry:
                    domains[name] = entry["domain"]

    mcq_pages.sort()

    all_questions = load_questions(folder_name, model)
    existing_pages = get_existing_pages(all_questions)

    new_mcq_pages = []
    for name in mcq_pages:
        page_num = extract_page_number(name)
        if page_num not in existing_pages:
            new_mcq_pages.append(name)

    if max_pages:
        new_mcq_pages = new_mcq_pages[:max_pages]

    if not new_mcq_pages:
        print("  All MCQ pages already extracted.")
        return

    print(f"  Found {len(mcq_pages)} MCQ-classified pages")
    print(f"  Skipping {len(mcq_pages) - len(new_mcq_pages)} already extracted pages")
    print(f"  Extracting {len(new_mcq_pages)} new pages with {provider} ({model})\n")

    for name in new_mcq_pages:
        img_path = str(images_by_name[name])
        print(f"  Processing: {name}")

        try:
            raw = retry_extract(extract_fn, img_path, model=model)
            questions = parse_response(raw)
            page_num = extract_page_number(name)

            labels = ["A", "B", "C", "D"]
            for q in questions:
                options_list = q.get("options", [])
                q["domain"] = domains.get(name, "")
                q["subdomain"] = ""
                q["question"] = q.get("question", "").strip()
                q["options"] = {labels[i]: opt for i, opt in enumerate(options_list[:4])}
                q["correct_option"] = None
                q["correct_index"] = None
                q["level"] = ""
                q["page"] = page_num
                q["source_url"] = ""
                q["source_image"] = name
                q["folder"] = folder_name
                q["provider"] = provider
                q["model"] = model

            all_questions.extend(questions)
            save_questions(all_questions, folder_name, model)
            print(f"    -> Extracted {len(questions)} questions")

        except json.JSONDecodeError as e:
            print(f"    -> Warning: JSON parse error: {e}")
        except Exception as e:
            print(f"    -> Error: {e}")

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nDone with {folder_name}! Total questions in file: {len(all_questions)}")
    print(f"Saved to: {get_questions_file(folder_name, model)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=PROVIDERS.keys(), default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name to use")
    parser.add_argument("--max-pages", type=int, default=None, help="Max pages per folder")
    args = parser.parse_args()

    if not INPUT_ROOT.exists():
        raise FileNotFoundError(f"INPUT_ROOT does not exist: {INPUT_ROOT}")

    QUESTIONS_ROOT.mkdir(parents=True, exist_ok=True)

    subfolders = sorted([p for p in INPUT_ROOT.iterdir() if p.is_dir()])
    if not subfolders:
        print(f"No subfolders found in {INPUT_ROOT}")
        return

    print(f"Provider: {args.provider}")
    print(f"Model: {args.model}")
    print("Folders to process:")
    for folder in subfolders:
        print(f"  - {folder.name}")

    for folder in subfolders:
        folder_name = folder.name
        classifications_file = CLASSIFICATIONS_ROOT / folder_name / "classifications.json"
        process_folder(
            folder_name=folder_name,
            image_dir=folder,
            classifications_file=classifications_file,
            provider=args.provider,
            model=args.model,
            max_pages=args.max_pages,
        )


if __name__ == "__main__":
    main()