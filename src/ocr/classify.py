import anthropic
import asyncio
import base64
import os
import json
import io
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_ROOT = BASE_DIR / "raw_data" / "SSC_1A25_QP_images"
OUTPUT_ROOT = BASE_DIR / "output" / "SSC_1A25_QP"

MAX_PAGES = None
CONCURRENCY = 2
BATCH_DELAY_SECONDS = 2
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

CLASSIFIER_PROMPT = """Look at this exam page image. Classify it into exactly ONE category:

- "urdu_mcq" — the page has multiple choice questions AND contains Urdu script in the question text or options. This includes BILINGUAL pages where questions appear in both English AND Urdu side by side — if Urdu is present alongside MCQ options, classify as urdu_mcq.
- "urdu_other" — the page contains Urdu text but NOT multiple choice questions (e.g. long questions, essays, short answers)
- "english" — the page has ONLY English text with NO Urdu script anywhere in the question/option content
- "skip" — blank page, cover page, instructions only, or not useful

If the category is "urdu_mcq", also extract the subject/domain from the top of the page (e.g. "Urdu SSC-I", "Pakistan Studies SSC-II", "Islamiat SSC-I").

Respond with ONLY valid JSON, no other text:
- For urdu_mcq: {"label": "urdu_mcq", "domain": "..."}
- For all others: {"label": "english"} or {"label": "urdu_other"} or {"label": "skip"}"""

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB API limit
VALID_LABELS = {"urdu_mcq", "urdu_other", "english", "skip"}
FINAL_DONE_LABELS = {"urdu_mcq", "urdu_other", "english"}  # "skip" will be rerun


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


def parse_result(text: str) -> dict:
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return {"label": "skip"}

        label = result.get("label", "skip")
        if label not in VALID_LABELS:
            return {"label": "skip"}

        if label == "urdu_mcq":
            domain = result.get("domain", "")
            if not isinstance(domain, str):
                domain = str(domain)
            return {"label": "urdu_mcq", "domain": domain.strip()}

        return {"label": label}

    except json.JSONDecodeError:
        label = text.lower().strip('"').strip()
        return {"label": label if label in VALID_LABELS else "skip"}


async def classify_page(client, image_path: str, retries: int = 5) -> dict:
    b64, media_type = encode_image(image_path)

    for attempt in range(retries):
        try:
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

        except Exception as e:
            error_text = str(e)

            if "429" in error_text or "rate_limit_error" in error_text:
                wait_time = min(60, 2 ** attempt)
                print(f"    Rate limited for {os.path.basename(image_path)}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue

            raise

    raise RuntimeError(f"Failed after retries due to rate limit: {image_path}")


def load_classifications(classifications_file: Path) -> dict:
    if not classifications_file.exists():
        return {}

    with open(classifications_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return {}

    normalized = {}
    for k, v in data.items():
        if isinstance(v, str):
            normalized[k] = {"label": v}
        elif isinstance(v, dict):
            label = v.get("label", "skip")
            if label == "urdu_mcq":
                normalized[k] = {
                    "label": "urdu_mcq",
                    "domain": str(v.get("domain", "")).strip()
                }
            elif label in VALID_LABELS:
                normalized[k] = {"label": label}
            else:
                normalized[k] = {"label": "skip"}
        else:
            normalized[k] = {"label": "skip"}

    return normalized


def save_classifications(data: dict, classifications_file: Path) -> None:
    classifications_file.parent.mkdir(parents=True, exist_ok=True)
    with open(classifications_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_images(image_dir: Path) -> list[str]:
    images = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        images.extend(image_dir.glob(ext))
    return sorted(str(p) for p in images)


def get_done_files(existing: dict) -> set[str]:
    return {
        name
        for name, result in existing.items()
        if isinstance(result, dict) and result.get("label") in FINAL_DONE_LABELS
    }


def count_skip_files(existing: dict) -> int:
    return sum(
        1
        for result in existing.values()
        if isinstance(result, dict) and result.get("label") == "skip"
    )


async def process_batch(client, batch: list[str], existing: dict, classifications_file: Path) -> None:
    tasks = {
        os.path.basename(img_path): asyncio.create_task(classify_page(client, img_path))
        for img_path in batch
    }

    for name, task in tasks.items():
        try:
            result = await task
            old_result = existing.get(name)
            existing[name] = result

            label = result["label"]
            domain = result.get("domain", "")
            suffix = f" [{domain}]" if domain else ""

            if old_result and isinstance(old_result, dict) and old_result.get("label") == "skip":
                print(f"  {name} -> {label}{suffix} (updated from skip)")
            else:
                print(f"  {name} -> {label}{suffix}")

            save_classifications(existing, classifications_file)

        except Exception as e:
            print(f"  {name} -> ERROR: {e}")
            # Do not save as skip. Leave it unmodified so it can rerun later.


async def process_folder(client, image_dir: Path) -> None:
    folder_name = image_dir.name
    classifications_file = OUTPUT_ROOT / folder_name / "classifications.json"

    print(f"\n=== Processing folder: {folder_name} ===")
    print(f"Image dir: {image_dir}")
    print(f"Output file: {classifications_file}")

    classifications_file.parent.mkdir(parents=True, exist_ok=True)

    images = get_images(image_dir)
    if MAX_PAGES:
        images = images[:MAX_PAGES]

    print(f"Found {len(images)} images")

    existing = load_classifications(classifications_file)
    done_files = get_done_files(existing)
    rerun_skip_count = count_skip_files(existing)

    new_images = [
        img for img in images
        if os.path.basename(img) not in done_files
    ]

    if not new_images:
        print("All non-skip pages already classified.")
        return

    print(f"Skipping {len(images) - len(new_images)} already classified non-skip pages")
    print(f"Retrying {rerun_skip_count} pages previously marked as skip")
    print(f"Processing {len(new_images)} pages (concurrency={CONCURRENCY})\n")

    for i in range(0, len(new_images), CONCURRENCY):
        batch = new_images[i:i + CONCURRENCY]
        await process_batch(client, batch, existing, classifications_file)
        await asyncio.sleep(BATCH_DELAY_SECONDS)

    counts = {}
    for entry in existing.values():
        label = entry["label"] if isinstance(entry, dict) else str(entry)
        counts[label] = counts.get(label, 0) + 1

    print(f"\nDone with {folder_name}! {len(existing)} pages currently stored:")
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")


async def main() -> None:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

    if not INPUT_ROOT.exists():
        raise FileNotFoundError(f"INPUT_ROOT does not exist: {INPUT_ROOT}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    subfolders = sorted([p for p in INPUT_ROOT.iterdir() if p.is_dir()])

    if not subfolders:
        print(f"No subfolders found in {INPUT_ROOT}")
        return

    print("Folders to process:")
    for folder in subfolders:
        print(f"  - {folder.name}")

    for folder in subfolders:
        await process_folder(client, folder)


if __name__ == "__main__":
    asyncio.run(main())