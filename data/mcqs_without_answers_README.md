# mcqs_without_answers.json

Cleaned dataset of Urdu MCQs without correct answers, remapped to the final domain taxonomy.

## Overview

| Attribute | Value |
|---|---|
| Total questions | 17,183 |
| Language | Urdu (`ur`) |
| Answers included | No |
| Domains | 4 |

## Schema

```json
{
  "question_number": "integer  — sequential question number",
  "question":        "string   — question text in Urdu",
  "options":         {"A": "...", "B": "...", "C": "...", "D": "..."},
  "has_image":       "boolean  — whether the question has an associated image",
  "image_bbox":      "object | null  — bounding box of image in source scan",
  "domain":          "string   — final domain (STEM | Humanities | Social Sciences | Profession)",
  "subdomain":       "string   — normalized snake_case subdomain slug",
  "correct_option":  "string | null  — correct option letter (if available)",
  "correct_index":   "integer | null — 0-based index of correct option",
  "level":           "string   — difficulty / grade level",
  "page":            "integer  — page number in source document",
  "source_url":      "string   — original source URL or identifier",
  "source_image":    "string   — filename of the source scan image",
  "folder":          "string   — folder path of the source image",
  "provider":        "string   — OCR / extraction provider",
  "model":           "string   — model used for extraction",
  "source":          "string   — source name (Ustad 360 | FBISE | BISE Multan 2025)"
}
```

## Domain Distribution

| Domain | Questions | % |
|---|---:|---:|
| STEM | 14,604 | 85.0% |
| Social Sciences | 1,191 | 6.9% |
| Humanities | 957 | 5.6% |
| Profession | 431 | 2.5% |
| **Total** | **17,183** | **100%** |

## Subdomain Breakdown

### STEM — 14,604

| Subdomain | Count |
|---|---:|
| `mathematics` | 6,886 |
| `biology` | 2,610 |
| `chemistry` | 2,435 |
| `computer_science` | 1,339 |
| `physics` | 1,111 |
| `general_science` | 223 |

### Social Sciences — 1,191

| Subdomain | Count |
|---|---:|
| `civics` | 555 |
| `pakistan_studies` | 218 |
| `education` | 150 |
| `geography` | 102 |
| `economics` | 90 |
| `health_and_physical_education` | 76 |

### Humanities — 957

| Subdomain | Count |
|---|---:|
| `islamic_studies` | 565 |
| `urdu_language` | 253 |
| `art_and_model_drawing` | 79 |
| `ethics` | 60 |

### Profession — 431

| Subdomain | Count |
|---|---:|
| `home_economics` | 143 |
| `food_and_nutrition` | 72 |
| `electrical_and_wiring` | 68 |
| `clothing_and_textile` | 60 |
| `dress_making_and_fashion_designing` | 52 |
| `internet_of_things` | 12 |
| `tourism` | 12 |
| `media_production` | 6 |
| `plumbing_and_solar_water_heating` | 6 |

## Source Distribution

| Source | Questions | % |
|---|---:|---:|
| Ustad 360 | 13,836 | 80.5% |
| FBISE | 2,574 | 15.0% |
| BISE Multan 2025 | 893 | 5.2% |
| **Total** | **17,183** | **100%** |

## Generation

```bash
# Produce from data/mcqs_without_answers.json
python domain_analysis/remap_domains.py data/mcqs_without_answers.json
```
