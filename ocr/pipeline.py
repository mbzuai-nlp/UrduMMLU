#!/usr/bin/env python3
"""
Urdu MCQ OCR Pipeline
=====================
Automates: PDF → Images → Classify → Extract MCQs

All output is written under pipeline_output/, mirroring the input path:

  Input:  raw_data/fbise/2023/SSC-I.pdf
  Output: pipeline_output/fbise/2023/SSC-I/
            images/               ← page PNGs
            classifications.json  ← classify step
            questions_{model}.json

The pipeline is resumable: each step checks what already exists and skips
completed work, so re-running after a failure picks up where it left off.

Usage examples:
  # Full pipeline from a single PDF
  python ocr/pipeline.py --input raw_data/fbise/2023/exam.pdf

  # All PDFs inside a folder (searched recursively)
  python ocr/pipeline.py --input raw_data/fbise/2023/

  # Classify only (no OCR API calls)
  python ocr/pipeline.py --input raw_data/fbise/2023/exam.pdf --skip-ocr

  # OCR only (classifications already exist)
  python ocr/pipeline.py --input raw_data/fbise/2023/exam.pdf --skip-classify

  # Use Anthropic for OCR instead of Gemini
  python ocr/pipeline.py --input raw_data/exam.pdf --provider anthropic --model claude-sonnet-4-6

  # Test on a small batch first
  python ocr/pipeline.py --input raw_data/exam.pdf --max-pages 5
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OCR_DIR = Path(__file__).resolve().parent
PIPELINE_OUTPUT = BASE_DIR / "pipeline_output"

# Allow importing sibling modules (classify.py, ocr.py) without package setup
sys.path.insert(0, str(OCR_DIR))

DIVIDER = "=" * 60


def _banner(step: int, total: int, title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  Step {step}/{total}: {title}")
    print(DIVIDER)


def get_output_subdir(path: Path) -> Path:
    """
    Return the relative subdir under pipeline_output/ that mirrors the input path.
    Strips a leading 'raw_data/' segment when present.
    For PDF files the stem (no extension) is used as the leaf folder name.

    Examples (BASE_DIR = /project):
      /project/raw_data/fbise/2023/exam.pdf  →  fbise/2023/exam
      /project/raw_data/exam.pdf             →  exam
      /project/data/images/                  →  data/images
      /outside/path/exam.pdf                 →  exam
    """
    try:
        rel = path.relative_to(BASE_DIR)
        parts = list(rel.parts)
    except ValueError:
        parts = [path.stem if path.is_file() else path.name]

    if parts and parts[0] == "raw_data":
        parts = parts[1:]

    if path.is_file():
        parts[-1] = path.stem  # drop extension

    if not parts:
        return Path(path.stem if path.is_file() else path.name)

    return Path(*parts)


# ── Step 1: PDF → Images ──────────────────────────────────────────────────────

def run_pdf_to_images(pdf_path: Path, images_dir: Path, dpi: int = 300) -> None:
    """Convert each PDF page to a JPEG in images_dir. Skips if already done.

    JPEG is used instead of PNG because PNG at 200-300 DPI can exceed the 5 MB
    limit imposed by the Anthropic classify API.  JPEG at quality 92 produces
    files of ~100 KB–1 MB per page — well within limits and still sharp enough
    for both classification and OCR.
    """
    try:
        import fitz
    except ImportError:
        print("Error: PyMuPDF not installed.  Run: pip install PyMuPDF")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    total = len(doc)

    existing = sorted(images_dir.glob("*.jpg")) if images_dir.exists() else []
    if len(existing) == total:
        print(f"  All {total} images already exist. Skipping conversion.")
        doc.close()
        return

    images_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    print(f"  Converting {total} pages at {dpi} DPI (JPEG)...")
    for page_num in range(total):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out_file = images_dir / f"{pdf_path.stem}_page_{page_num + 1:04d}.jpg"
        pix.save(str(out_file), jpg_quality=92)
        print(f"  [{page_num + 1}/{total}] {out_file.name}", end="\r")

    doc.close()
    print(f"\n  Done. {total} images saved to: {images_dir}")


# ── Step 2: Classify ──────────────────────────────────────────────────────────

async def run_classify(images_dir: Path, output_dir: Path) -> Path:
    """
    Classify each image as urdu_mcq / urdu_other / english / skip.
    Results are saved incrementally to output_dir/classifications.json so that
    re-running after a failure skips already-classified pages.
    """
    try:
        import anthropic as anthropic_lib
        import classify as classify_module
    except ImportError as e:
        print(f"Error: Missing dependency — {e}")
        print("Run: pip install -r ocr/requirements.txt")
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    classifications_file = output_dir / "classifications.json"

    client = anthropic_lib.AsyncAnthropic(api_key=api_key)

    images = classify_module.get_images(images_dir)
    print(f"  Found {len(images)} images")

    existing = classify_module.load_classifications(classifications_file)
    done_files = classify_module.get_done_files(existing)
    new_images = [img for img in images if os.path.basename(img) not in done_files]

    if not new_images:
        print("  All images already classified. Skipping.")
    else:
        skip_count = len(images) - len(new_images)
        if skip_count:
            print(f"  Skipping {skip_count} already classified images")
        print(f"  Classifying {len(new_images)} images (concurrency={classify_module.CONCURRENCY})\n")

        for i in range(0, len(new_images), classify_module.CONCURRENCY):
            batch = new_images[i : i + classify_module.CONCURRENCY]
            await classify_module.process_batch(client, batch, existing, classifications_file)
            await asyncio.sleep(classify_module.BATCH_DELAY_SECONDS)

    counts: dict[str, int] = {}
    for entry in existing.values():
        label = entry["label"] if isinstance(entry, dict) else str(entry)
        counts[label] = counts.get(label, 0) + 1

    print(f"\n  Classification summary ({len(existing)} pages):")
    for label, count in sorted(counts.items()):
        print(f"    {label}: {count}")

    return classifications_file


# ── Step 3: Extract MCQs ──────────────────────────────────────────────────────

def run_ocr(
    output_base_dir: Path,
    images_dir: Path,
    classifications_file: Path,
    provider: str,
    model: str,
    max_pages: int | None,
) -> Path:
    """
    Extract MCQ questions from pages classified as urdu_mcq.
    Output: output_base_dir/questions_{model}.json
    """
    try:
        import ocr as ocr_module
    except ImportError as e:
        print(f"Error: Missing dependency — {e}")
        print("Run: pip install -r ocr/requirements.txt")
        sys.exit(1)

    if provider not in ocr_module.PROVIDERS:
        print(f"Error: Unknown provider '{provider}'. Choose: {list(ocr_module.PROVIDERS)}")
        sys.exit(1)

    # Redirect the module's hardcoded QUESTIONS_ROOT so output lands in our folder.
    # ocr.py saves to:  QUESTIONS_ROOT / folder_name / questions_{model}.json
    # We want:          output_base_dir              / questions_{model}.json
    # So:               QUESTIONS_ROOT = output_base_dir.parent, folder_name = output_base_dir.name
    ocr_module.QUESTIONS_ROOT = output_base_dir.parent
    output_base_dir.mkdir(parents=True, exist_ok=True)

    ocr_module.process_folder(
        folder_name=output_base_dir.name,
        image_dir=images_dir,
        classifications_file=classifications_file,
        provider=provider,
        model=model,
        max_pages=max_pages,
    )

    safe_model = ocr_module.sanitize_model_name(model)
    return output_base_dir / f"questions_{safe_model}.json"


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

async def run_pipeline(
    args: argparse.Namespace,
    input_path: Path,
    output_base_dir: Path,
    is_pdf: bool,
    pdf_index: int | None = None,
    pdf_total: int | None = None,
) -> None:
    """Run the full pipeline for one PDF or one image directory."""
    images_dir = output_base_dir / "images"
    # When input is already an image directory, read images from there directly
    active_images_dir = images_dir if is_pdf else input_path

    run_pdf_step = is_pdf
    run_classify_step = not args.skip_classify
    run_ocr_step = not args.skip_ocr

    steps = []
    if run_pdf_step:
        steps.append("PDF → Images")
    if run_classify_step:
        steps.append("Classify")
    if run_ocr_step:
        steps.append(f"Extract MCQs ({args.provider})")
    total_steps = len(steps)

    progress = f"  ({pdf_index}/{pdf_total})" if pdf_index is not None else ""
    print(f"\n{DIVIDER}")
    print(f"  Urdu MCQ OCR Pipeline{progress}")
    print(f"{DIVIDER}")
    print(f"  Input  : {input_path}")
    print(f"  Output : {output_base_dir}/")
    print(f"  Steps  : {' → '.join(steps)}")

    current_step = 0

    # ── Step 1: PDF → Images ──────────────────────────────────────────────────
    if run_pdf_step:
        current_step += 1
        _banner(current_step, total_steps, "PDF → Images")
        run_pdf_to_images(input_path, images_dir, dpi=args.dpi)

    # ── Step 2: Classify ──────────────────────────────────────────────────────
    classifications_file = output_base_dir / "classifications.json"

    if run_classify_step:
        current_step += 1
        _banner(current_step, total_steps, "Classify Pages")
        classifications_file = await run_classify(active_images_dir, output_base_dir)
    else:
        if not classifications_file.exists():
            print(f"\nError: --skip-classify was used but no classifications.json found at:")
            print(f"  {classifications_file}")
            print("Run the pipeline without --skip-classify first.")
            sys.exit(1)
        print(f"\n[Classify] Skipped. Using: {classifications_file}")

    # ── Step 3: OCR ───────────────────────────────────────────────────────────
    questions_file: Path | None = None

    if run_ocr_step:
        current_step += 1
        _banner(current_step, total_steps, f"Extract MCQs  [{args.provider} / {args.model}]")
        questions_file = run_ocr(
            output_base_dir=output_base_dir,
            images_dir=active_images_dir,
            classifications_file=classifications_file,
            provider=args.provider,
            model=args.model,
            max_pages=args.max_pages,
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    img_count = len(list(images_dir.glob("*.*"))) if images_dir.exists() else 0
    print(f"\n{DIVIDER}")
    print(f"  Done{progress}")
    print(f"  {output_base_dir}/")
    if is_pdf:
        print(f"    images/  ({img_count} files)")
    print(f"    classifications.json")
    if questions_file:
        print(f"    {questions_file.name}")
    print(f"{DIVIDER}\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_pdfs(root: Path) -> list[Path]:
    """Recursively find all PDF files under root, sorted by path."""
    return sorted(root.rglob("*.pdf"))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Urdu MCQ OCR Pipeline: PDF/Images → Classify → Extract",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a .pdf file, an image directory, or a folder containing PDFs "
             "(searched recursively)",
    )
    parser.add_argument(
        "--name",
        help="Override the output folder name. Only applies to single-PDF or "
             "single-image-directory inputs; ignored when multiple PDFs are found.",
    )
    parser.add_argument(
        "--provider", choices=["anthropic", "openai", "gemini"], default="gemini",
        help="OCR provider for question extraction (default: gemini)",
    )
    parser.add_argument(
        "--model", default="gemini-3-flash-preview",
        help="Model name for OCR extraction (default: gemini-2.5-flash-preview-04-17)",
    )
    parser.add_argument(
        "--dpi", type=int, default=300,
        help="DPI for PDF-to-image conversion (default: 300)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Limit OCR extraction to N pages per PDF (useful for testing)",
    )
    parser.add_argument(
        "--skip-classify", action="store_true",
        help="Skip classification step — requires existing classifications.json",
    )
    parser.add_argument(
        "--skip-ocr", action="store_true",
        help="Skip OCR/extraction step (classify only)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)

    is_pdf = input_path.is_file() and input_path.suffix.lower() == ".pdf"
    is_dir = input_path.is_dir()

    if not is_pdf and not is_dir:
        print("Error: --input must be a .pdf file or a directory.")
        sys.exit(1)

    if is_pdf:
        # ── Single PDF ────────────────────────────────────────────────────────
        subdir = Path(args.name) if args.name else get_output_subdir(input_path)
        await run_pipeline(
            args, input_path,
            output_base_dir=PIPELINE_OUTPUT / subdir,
            is_pdf=True,
        )

    else:
        # ── Directory: search for PDFs recursively ────────────────────────────
        pdfs = find_pdfs(input_path)

        if pdfs:
            if args.name:
                print("Note: --name is ignored when processing multiple PDFs. "
                      "Names are derived from each PDF's path.")
            print(f"\nFound {len(pdfs)} PDF(s) under: {input_path}")
            for i, pdf in enumerate(pdfs, 1):
                print(f"  [{i}/{len(pdfs)}] {pdf.relative_to(input_path)}")

            for i, pdf in enumerate(pdfs, 1):
                subdir = get_output_subdir(pdf)
                await run_pipeline(
                    args, pdf,
                    output_base_dir=PIPELINE_OUTPUT / subdir,
                    is_pdf=True,
                    pdf_index=i,
                    pdf_total=len(pdfs),
                )

        else:
            # ── No PDFs found: treat as image directory ───────────────────────
            subdir = Path(args.name) if args.name else get_output_subdir(input_path)
            await run_pipeline(
                args, input_path,
                output_base_dir=PIPELINE_OUTPUT / subdir,
                is_pdf=False,
            )


if __name__ == "__main__":
    asyncio.run(main())
