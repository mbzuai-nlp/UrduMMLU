# Urdu MMLU — OCR Pipeline

Automated pipeline for extracting Urdu multiple-choice questions (MCQs) from PDF exam papers.

**Flow:** PDF → Page Images → Classify Pages → Extract MCQs (JSON)

---

## Prerequisites

- Python 3.10+
- API keys for the services you plan to use

---

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd urdu-mmlu

# Create and activate a virtual environment (recommended)
python3.10 -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
pip install PyMuPDF Pillow
```

---

## API Keys

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_anthropic_key_here
GEMINI_API_KEY=your_gemini_key_here       # if using Gemini for OCR
OPENAI_API_KEY=your_openai_key_here       # if using OpenAI for OCR
```

> **Note:** `ANTHROPIC_API_KEY` is always required — it is used for the page classification step regardless of which OCR provider you choose.

---

## Project Structure

```
urdu-mmlu/
├── data/                        ← scraped MCQ datasets
│   ├── mcqtimes_urdu.json
│   └── pakmcqs_urdu_general_knowledge.json
├── ocr/
│   ├── pipeline.py              ← main entry point
│   ├── classify.py              ← page classification (Anthropic)
│   ├── ocr.py                   ← MCQ extraction (Gemini / OpenAI / Anthropic)
│   └── pdf_to_images.py         ← standalone PDF → images utility
├── review_json_structure.py     ← post-processing: normalize questions JSONs
└── requirements.txt
```

---

## Running the Pipeline

Place your PDF files in a folder and pass that path to `--input`.

### Single PDF

```bash
python ocr/pipeline.py --input path/to/exam.pdf
```

### All PDFs inside a folder (recursive)

```bash
python ocr/pipeline.py --input path/to/folder/
```

This finds every `.pdf` file recursively under the folder and processes each one.

### Image directory (PDFs already converted)

```bash
python ocr/pipeline.py --input path/to/images/
```

The pipeline saves all output under `pipeline_output/`, mirroring the input path structure:

```
pipeline_output/
└── exam/
    ├── images/                  ← page JPEGs
    ├── classifications.json     ← classify results
    └── questions_{model}.json   ← extracted MCQs
```

---

## All Options

| Flag | Default | Description |
|---|---|---|
| `--input` | *(required)* | Path to a `.pdf`, an image directory, or a folder containing PDFs |
| `--provider` | `gemini` | OCR provider: `gemini`, `anthropic`, or `openai` |
| `--model` | `gemini-3-flash-preview` | Model name for MCQ extraction |
| `--dpi` | `300` | Resolution for PDF-to-image conversion |
| `--max-pages` | *(none)* | Limit extraction to N pages (useful for testing) |
| `--skip-classify` | `false` | Skip classification — requires existing `classifications.json` |
| `--skip-ocr` | `false` | Skip OCR — run classification only |
| `--name` | *(auto)* | Override the output folder name (single PDF/directory only) |

---

## Common Usage Examples

```bash
# Use Anthropic (Claude) instead of Gemini for OCR
python ocr/pipeline.py --input path/to/exam.pdf --provider anthropic --model claude-sonnet-4-6

# Test on the first 5 pages only
python ocr/pipeline.py --input path/to/exam.pdf --max-pages 5

# Classify only (no OCR API calls)
python ocr/pipeline.py --input path/to/exam.pdf --skip-ocr

# Re-run OCR after classifications are already done
python ocr/pipeline.py --input path/to/exam.pdf --skip-classify
```

---

## Output Format

Each extracted question is saved as a JSON object:

```json
{
  "question_number": 1,
  "question": "کیمیائی توازن کی حالت میں کیا ہوتا ہے؟",
  "options": {
    "A": "ری ایکشن رک جاتی ہے",
    "B": "آگے اور پیچھے کی شرح برابر ہو جاتی ہے",
    "C": "صرف پروڈکٹس بنتی ہیں",
    "D": "ری ایکٹنٹس ختم ہو جاتے ہیں"
  },
  "has_image": false,
  "image_bbox": null,
  "domain": "Chemistry SSC-II",
  "subdomain": "",
  "correct_option": null,
  "correct_index": null,
  "level": "",
  "page": 1,
  "source_url": "",
  "source_image": "Chemistry 10th_page_0001.jpg",
  "folder": "Chemistry 10th",
  "provider": "gemini",
  "model": "gemini-3-flash-preview"
}
```

---

## Resumability

The pipeline is fully resumable. If it stops mid-run (error, rate limit, Ctrl+C), just re-run the same command — each step checks what already exists and skips completed work:

- **PDF → Images**: skips if all page images already exist
- **Classify**: skips images already recorded in `classifications.json`
- **Extract MCQs**: skips pages already present in the questions JSON

---

## Post-processing: Normalize Questions JSON

If you have existing questions files with inconsistent structure (missing keys, options as a list instead of a dict), run `review_json_structure.py` to normalize them in-place.

```bash
# Normalize all questions files under a folder (recursive)
python review_json_structure.py path/to/output/folder/

# Normalize a single file
python review_json_structure.py path/to/questions_gemini-3-flash-preview.json
```

This script:
- Ensures all required keys are present (fills missing ones with empty string / null)
- Converts `options` from a list to a dict (`["A text", "B text"]` → `{"A": "A text", "B": "B text"}`)
- Enforces a consistent key order across all items

> **Note:** The script targets files named exactly `questions_gemini-3-flash-preview.json`. Update `TARGET_FILENAME` at the top of the file if you used a different model.

---

## Merging Questions into a Single File

After running the pipeline across multiple PDFs or subjects, use `merge_questions.py` to combine all per-folder JSON files into one consolidated file named after the parent folder.

```bash
# Merge all subjects under BISE_Multan_25 → pipeline_output/BISE_Multan_25.json
python merge_questions.py --input pipeline_output/BISE_Multan_25

# Merge all years/exams under fbise → pipeline_output/fbise.json
python merge_questions.py --input pipeline_output/fbise

# Works on any output folder, not just pipeline_output/
python merge_questions.py --input output_questions/SSC_1A25_QP

# Write to a custom location
python merge_questions.py --input pipeline_output/BISE_Multan_25 --output merged/bise.json

# Use a different source filename (e.g. from a different model run)
python merge_questions.py --input pipeline_output/BISE_Multan_25 \
    --filename questions_claude-sonnet-4-6.json
```

The script searches **recursively**, so nested structures (e.g. `fbise/2024/SSC-I CSG/questions_*.json`) are handled automatically.

**Default output location:** `<parent_of_input>/<folder_name>.json`

| Input | Output |
|---|---|
| `pipeline_output/BISE_Multan_25` | `pipeline_output/BISE_Multan_25.json` |
| `pipeline_output/fbise` | `pipeline_output/fbise.json` |
| `output_questions/SSC_1A25_QP` | `output_questions/SSC_1A25_QP.json` |

### Options

| Flag | Default | Description |
|---|---|---|
| `--input` | *(required)* | Folder to scan recursively |
| `--output` | `<parent>/<folder_name>.json` | Override the output file path |
| `--filename` | `questions_gemini-3-flash-preview.json` | Source filename to search for |

---

## Page Classification Labels

| Label | Meaning |
|---|---|
| `urdu_mcq` | Page has Urdu MCQs — will be sent for extraction |
| `urdu_other` | Urdu text but not MCQs (essays, short answers) |
| `english` | English-only page |
| `skip` | Blank, cover, or instructions page |
