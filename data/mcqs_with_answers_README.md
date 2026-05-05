# mcqs_with_answers.json

Merged dataset of native Urdu MCQs with correct answers.

## Sources

| File | Questions |
|---|---:|
| `ahmer_mcqs.json` | 6,628 |
| `native_urdu_mcqs.json` | 9,023 |
| Duplicates removed | 47 |
| **Total** | **15,604** |

`ahmer_mcqs.json` entries take priority; 47 questions found in both files were dropped from the native set.

## Schema

```json
{
  "question":       "string  — question text in Urdu",
  "options":        {"A": "...", "B": "...", "C": "...", "D": "..."},
  "correct_answer": "A | B | C | D | null",
  "correct_index":  "0-based integer | null",
  "domain":         "string  — top-level domain",
  "subdomain":      "string  — subdomain slug",
  "level":          "string  — difficulty level (often empty)",
  "source_url":     "string  — original source URL",
  "language":       "ur"
}
```

> `correct_answer` for `ahmer_mcqs` entries is derived from `correct_index` (e.g. index `1` → `"B"`).

## Domain Distribution

| Domain | Questions | % |
|---|---:|---:|
| Humanities | 10,617 | 68.0% |
| Social Sciences | 2,906 | 18.6% |
| Islamic Studies | 1,149 | 7.4% |
| Professional | 602 | 3.9% |
| Psychology & Education | 138 | 0.9% |
| STEM | 179 | 1.1% |
| Law & Governance | 13 | 0.1% |
| **Total** | **15,604** | **100%** |

## Subdomain Breakdown

### Humanities — 10,617

| Subdomain | Count |
|---|---:|
| `urdu_language` | 4,825 |
| `urdu_literature` | 4,767 |
| `urdu_grammar` | 468 |
| `sindhi_language` | 330 |
| `pakistan_studies` | 222 |
| `english_language` | 5 |

### Social Sciences — 2,906

| Subdomain | Count |
|---|---:|
| `general_knowledge` | 1,607 |
| `pakistan_studies` | 1,106 |
| `current_affairs` | 175 |
| `international_affairs` | 16 |
| `social_studies` | 2 |

### Islamic Studies — 1,149

| Subdomain | Count |
|---|---:|
| `islamic_studies` | 1,082 |
| `hajj_management` | 67 |

### Professional — 602

| Subdomain | Count |
|---|---:|
| `professional_development` | 598 |
| `clerical_services` | 4 |

### Psychology & Education — 138

| Subdomain | Count |
|---|---:|
| `psychometrics` | 126 |
| `pedagogy` | 10 |
| `professional_psychology` | 2 |

### STEM — 179

| Subdomain | Count |
|---|---:|
| `everyday_science` | 156 |
| `electrical_engineering` | 10 |
| `high_school_computer_science` | 9 |
| `elementary_mathematics` | 4 |

### Law & Governance — 13

| Subdomain | Count |
|---|---:|
| `federal_investigation_law` | 13 |

## Generation

```bash
python scrape/merge_native_ahmer.py

# Custom paths
python scrape/merge_native_ahmer.py \
  --ahmer  data/ahmer_mcqs.json \
  --native data/native_urdu_mcqs.json \
  --output data/mcqs_with_answers.json
```
