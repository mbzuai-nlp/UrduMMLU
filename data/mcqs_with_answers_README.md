# mcqs_with_answers.json

Cleaned dataset of native Urdu MCQs with correct answers, remapped to the final domain taxonomy.

## Overview

| Attribute | Value |
|---|---|
| Total questions | 15,090 |
| Language | Urdu (`ur`) |
| Answers included | Yes |
| Domains | 4 |

## Schema

```json
{
  "question":       "string  — question text in Urdu",
  "options":        {"A": "...", "B": "...", "C": "...", "D": "..."},
  "correct_answer": "A | B | C | D | null",
  "correct_index":  "0-based integer | null",
  "domain":         "string  — final domain (Humanities | Social Sciences | Profession | Other)",
  "subdomain":      "string  — normalized snake_case subdomain slug",
  "level":          "string  — difficulty level (often empty)",
  "source_url":     "string  — original source URL",
  "source":         "string  — source name (mcqtimes | pakmcqs | testpointpk | etest | gotest | examaunty)",
  "language":       "ur"
}
```

## Domain Distribution

| Domain | Questions | % |
|---|---:|---:|
| Humanities | 11,142 | 73.8% |
| Social Sciences | 1,657 | 11.0% |
| Other | 1,622 | 10.8% |
| Profession | 669 | 4.4% |
| **Total** | **15,090** | **100%** |

## Subdomain Breakdown

### Humanities — 11,142

| Subdomain | Count |
|---|---:|
| `urdu_language` | 4,825 |
| `urdu_literature` | 4,767 |
| `islamic_studies` | 1,082 |
| `urdu_grammar` | 468 |

### Social Sciences — 1,657

| Subdomain | Count |
|---|---:|
| `pakistan_studies` | 1,330 |
| `current_and_international_affairs` | 191 |
| `psychometrics` | 126 |
| `pedagogy` | 10 |

### Other — 1,622

| Subdomain | Count |
|---|---:|
| `general_knowledge` | 1,607 |
| `federal_investigation_law` | 13 |
| `professional_psychology` | 2 |

### Profession — 669

| Subdomain | Count |
|---|---:|
| `professional_development` | 598 |
| `hajj_management` | 67 |
| `clerical_services` | 4 |

## Source Distribution

| Source | Questions | % |
|---|---:|---:|
| mcqtimes | 6,170 | 40.9% |
| testpointpk | 3,690 | 24.5% |
| etest | 3,442 | 22.8% |
| examaunty | 694 | 4.6% |
| gotest | 636 | 4.2% |
| pakmcqs | 458 | 3.0% |
| **Total** | **15,090** | **100%** |

## Generation

```bash
# Produce from data/mcqs_with_answers.json
python3.10 domain_analysis/remap_domains.py data/mcqs_with_answers.json
```
