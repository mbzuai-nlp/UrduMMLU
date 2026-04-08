import argparse
import base64
import io
import os
import glob
import json
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, "raw/SSC-I Normal")
CLASSIFICATIONS_FILE = os.path.join(BASE_DIR, "output/classifications.json")
QUESTIONS_FILE_TEMPLATE = os.path.join(BASE_DIR, "output/questions_{model}.json")
MAX_IMAGE_BYTES = 5 * 1024 * 1024

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
- Return valid JSON only. No markdown, no code blocks, no explanation."""


# --- Image encoding ---

def encode_image(path: str) -> tuple[str, str]:
    ext = os.path.splitext(path)[1].lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    with open(path, "rb") as f:
        data = f.read()

    if len(data) <= MAX_IMAGE_BYTES:
        return base64.standard_b64encode(data).decode("utf-8"), media_type

    img = Image.open(path)
    quality = 85
    while quality >= 30:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
        quality -= 10

    img.thumbnail((img.width // 2, img.height // 2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


# --- Providers ---

def extract_anthropic(image_path, model="claude-sonnet-4-6"):
    import anthropic
    client = anthropic.Anthropic()
    b64, media_type = encode_image(image_path)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": EXTRACTOR_PROMPT},
            ],
        }],
    )
    return response.content[0].text


def extract_openai(image_path, model="gpt-4o"):
    import openai
    client = openai.OpenAI()
    b64, media_type = encode_image(image_path)

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": EXTRACTOR_PROMPT},
            ],
        }],
    )
    return response.choices[0].message.content


def extract_gemini(image_path, model="gemini-2.5-flash"):
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


# --- Core logic ---

def parse_response(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def get_questions_file(model):
    safe_model = model.replace("/", "_").replace(":", "_")
    return QUESTIONS_FILE_TEMPLATE.format(model=safe_model)


def load_questions(model):
    path = get_questions_file(model)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_questions(questions, model):
    with open(get_questions_file(model), "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=PROVIDERS.keys(), default="anthropic")
    parser.add_argument("--model", default=None, help="Override default model for provider")
    parser.add_argument("--max-pages", type=int, default=None, help="Max MCQ pages to process")
    args = parser.parse_args()

    defaults = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o", "gemini": "gemini-2.5-flash"}
    model = args.model or defaults[args.provider]
    extract_fn = PROVIDERS[args.provider]

    if not os.path.exists(CLASSIFICATIONS_FILE):
        print("No classifications found. Run classify.py first.")
        return

    with open(CLASSIFICATIONS_FILE, "r", encoding="utf-8") as f:
        classifications = json.load(f)

    mcq_pages = []
    domains = {}
    for name, entry in classifications.items():
        label = entry["label"] if isinstance(entry, dict) else entry
        if label == "urdu_mcq":
            mcq_pages.append(name)
            if isinstance(entry, dict) and "domain" in entry:
                domains[name] = entry["domain"]
    mcq_pages.sort()

    all_questions = load_questions(model)
    existing_pages = {q["page"] for q in all_questions}

    new_mcq_pages = [
        name for name in mcq_pages
        if int(name.split("-")[-1].split(".")[0]) not in existing_pages
    ]

    if args.max_pages:
        new_mcq_pages = new_mcq_pages[:args.max_pages]

    if not new_mcq_pages:
        print("All MCQ pages already extracted.")
        return

    print(f"Provider: {args.provider} ({model})")
    print(f"Found {len(new_mcq_pages)} new Urdu MCQ pages to extract\n")

    for name in new_mcq_pages:
        img_path = os.path.join(IMAGE_DIR, name)
        print(f"  Processing: {name}")
        try:
            raw = extract_fn(img_path, model=model)
            questions = parse_response(raw)
            page_num = int(name.split("-")[-1].split(".")[0])
            for q in questions:
                q["page"] = page_num
                q["provider"] = args.provider
                if name in domains:
                    q["domain"] = domains[name]
            all_questions.extend(questions)
            print(f"    → Extracted {len(questions)} questions")
        except json.JSONDecodeError as e:
            print(f"    → Warning: JSON parse error: {e}")
        except Exception as e:
            print(f"    → Error: {e}")

        save_questions(all_questions, model)

    print(f"\nDone! {len(all_questions)} total questions in {get_questions_file(model)}")


if __name__ == "__main__":
    main()
