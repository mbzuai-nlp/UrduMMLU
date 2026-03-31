import anthropic
import asyncio
import base64
import os
import glob
import json
import io
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, "raw/SSC-I Normal")
CLASSIFICATIONS_FILE = os.path.join(BASE_DIR, "output/classifications.json")
MAX_PAGES = None
CONCURRENCY = 10

CLASSIFIER_PROMPT = """Look at this exam page image. Classify it into exactly ONE category:

- "urdu_mcq" — the page has multiple choice questions AND contains Urdu script in the question text or options. This includes BILINGUAL pages where questions appear in both English AND Urdu side by side — if Urdu is present alongside MCQ options, classify as urdu_mcq.
- "urdu_other" — the page contains Urdu text but NOT multiple choice questions (e.g. long questions, essays, short answers)
- "english" — the page has ONLY English text with NO Urdu script anywhere in the question/option content
- "skip" — blank page, cover page, instructions only, or not useful

If the category is "urdu_mcq", also extract the subject/domain from the top of the page (e.g. "Urdu SSC-I", "Pakistan Studies SSC-I", "Islamiat SSC-I").

Respond with ONLY valid JSON, no other text:
- For urdu_mcq: {"label": "urdu_mcq", "domain": "..."}
- For all others: {"label": "english"} or {"label": "urdu_other"} or {"label": "skip"}"""


MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB API limit


def encode_image(path: str) -> tuple[str, str]:
    """Encode image to base64, resizing if over 5MB. Returns (b64, media_type)."""
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


def parse_result(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
        label = result.get("label", "skip")
        valid = {"urdu_mcq", "urdu_other", "english", "skip"}
        if label not in valid:
            return {"label": "skip"}
        return result
    except json.JSONDecodeError:
        label = text.lower().strip('"').strip()
        valid = {"urdu_mcq", "urdu_other", "english", "skip"}
        return {"label": label if label in valid else "skip"}


async def classify_page(client, image_path):
    b64, media_type = encode_image(image_path)

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[
            {
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
                    {"type": "text", "text": CLASSIFIER_PROMPT},
                ],
            }
        ],
    )
    return parse_result(response.content[0].text)


def load_classifications():
    if not os.path.exists(CLASSIFICATIONS_FILE):
        return {}
    with open(CLASSIFICATIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_classifications(data):
    with open(CLASSIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def process_batch(client, batch, existing):
    """Process a batch of images concurrently."""
    tasks = {
        os.path.basename(img_path): asyncio.create_task(classify_page(client, img_path))
        for img_path in batch
    }
    for name, task in tasks.items():
        try:
            result = await task
            existing[name] = result
            label = result["label"]
            domain = result.get("domain", "")
            suffix = f" [{domain}]" if domain else ""
            print(f"  {name} → {label}{suffix}")
        except Exception as e:
            print(f"  {name} → ERROR: {e}")
            existing[name] = {"label": "skip"}
        save_classifications(existing)


async def main():
    client = anthropic.AsyncAnthropic()
    images = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))
    if MAX_PAGES:
        images = images[:MAX_PAGES]
    print(f"Processing {len(images)} pages (concurrency={CONCURRENCY})\n")

    os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

    existing = load_classifications()
    for k, v in existing.items():
        if isinstance(v, str):
            existing[k] = {"label": v}
    new_images = [img for img in images if os.path.basename(img) not in existing]

    if not new_images:
        print("All pages already classified.")
        return

    print(f"Skipping {len(images) - len(new_images)} already classified pages\n")

    # Process in batches of CONCURRENCY
    for i in range(0, len(new_images), CONCURRENCY):
        batch = new_images[i:i + CONCURRENCY]
        await process_batch(client, batch, existing)

    counts = {}
    for entry in existing.values():
        label = entry["label"] if isinstance(entry, dict) else entry
        counts[label] = counts.get(label, 0) + 1

    print(f"\nDone! {len(existing)} pages classified:")
    for label, count in counts.items():
        print(f"  {label}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
