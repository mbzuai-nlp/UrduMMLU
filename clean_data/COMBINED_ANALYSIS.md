# Urdu MMLU — Combined Data Analysis

Aggregated statistics across both clean datasets.

---

## Files

| File | Questions | Answers |
|---|---:|---|
| `mcqs_with_answers.json` | 15,090 | Yes |
| `mcqs_without_answers.json` | 17,183 | No |
| **Total** | **32,273** | — |

---

## Domain Distribution

### Combined

| Domain | Questions | % |
|---|---:|---:|
| STEM | 14,604 | 45.3% |
| Humanities | 12,099 | 37.5% |
| Social Sciences | 2,848 | 8.8% |
| Other | 1,622 | 5.0% |
| Profession | 1,100 | 3.4% |
| **Total** | **32,273** | **100%** |

### Per File

| Domain | mcqs_with_answers | % | mcqs_without_answers | % |
|---|---:|---:|---:|---:|
| STEM | — | — | 14,604 | 85.0% |
| Humanities | 11,142 | 73.8% | 957 | 5.6% |
| Social Sciences | 1,657 | 11.0% | 1,191 | 6.9% |
| Other | 1,622 | 10.7% | — | — |
| Profession | 669 | 4.4% | 431 | 2.5% |
| **Total** | **15,090** | **100%** | **17,183** | **100%** |

---

## Subdomain Breakdown

### Humanities — 12,099

| Subdomain | with_answers | without_answers | Total | % of domain |
|---|---:|---:|---:|---:|
| `urdu_language` | 4,825 | 253 | 5,078 | 42.0% |
| `urdu_literature` | 4,767 | — | 4,767 | 39.4% |
| `islamic_studies` | 1,082 | 565 | 1,647 | 13.6% |
| `urdu_grammar` | 468 | — | 468 | 3.9% |
| `art_and_model_drawing` | — | 79 | 79 | 0.7% |
| `ethics` | — | 60 | 60 | 0.5% |
| **Total** | **11,142** | **957** | **12,099** | **100%** |

### STEM — 14,604

| Subdomain | with_answers | without_answers | Total | % of domain |
|---|---:|---:|---:|---:|
| `mathematics` | — | 6,886 | 6,886 | 47.2% |
| `biology` | — | 2,610 | 2,610 | 17.9% |
| `chemistry` | — | 2,435 | 2,435 | 16.7% |
| `computer_science` | — | 1,339 | 1,339 | 9.2% |
| `physics` | — | 1,111 | 1,111 | 7.6% |
| `general_science` | — | 223 | 223 | 1.5% |
| **Total** | **—** | **14,604** | **14,604** | **100%** |

### Social Sciences — 2,848

| Subdomain | with_answers | without_answers | Total | % of domain |
|---|---:|---:|---:|---:|
| `pakistan_studies` | 1,330 | 218 | 1,548 | 54.4% |
| `civics` | — | 555 | 555 | 19.5% |
| `current_and_international_affairs` | 191 | — | 191 | 6.7% |
| `education` | — | 150 | 150 | 5.3% |
| `psychometrics` | 126 | — | 126 | 4.4% |
| `geography` | — | 102 | 102 | 3.6% |
| `economics` | — | 90 | 90 | 3.2% |
| `health_and_physical_education` | — | 76 | 76 | 2.7% |
| `pedagogy` | 10 | — | 10 | 0.4% |
| **Total** | **1,657** | **1,191** | **2,848** | **100%** |

### Profession — 1,100

| Subdomain | with_answers | without_answers | Total | % of domain |
|---|---:|---:|---:|---:|
| `professional_development` | 598 | — | 598 | 54.4% |
| `home_economics` | — | 143 | 143 | 13.0% |
| `food_and_nutrition` | — | 72 | 72 | 6.5% |
| `electrical_and_wiring` | — | 68 | 68 | 6.2% |
| `hajj_management` | 67 | — | 67 | 6.1% |
| `clothing_and_textile` | — | 60 | 60 | 5.5% |
| `dress_making_and_fashion_designing` | — | 52 | 52 | 4.7% |
| `tourism` | — | 12 | 12 | 1.1% |
| `internet_of_things` | — | 12 | 12 | 1.1% |
| `plumbing_and_solar_water_heating` | — | 6 | 6 | 0.5% |
| `media_production` | — | 6 | 6 | 0.5% |
| `clerical_services` | 4 | — | 4 | 0.4% |
| **Total** | **669** | **431** | **1,100** | **100%** |

### Other — 1,622

| Subdomain | with_answers | without_answers | Total | % of domain |
|---|---:|---:|---:|---:|
| `general_knowledge` | 1,607 | — | 1,607 | 99.1% |
| `federal_investigation_law` | 13 | — | 13 | 0.8% |
| `professional_psychology` | 2 | — | 2 | 0.1% |
| **Total** | **1,622** | **—** | **1,622** | **100%** |

---

## Level Distribution

Levels are only present in `mcqs_without_answers.json` (SSC curriculum). All `mcqs_with_answers.json` entries have no level assigned.

| Level | Questions | % of total |
|---|---:|---:|
| Not specified | 15,090 | 46.8% |
| SSC-I | 9,588 | 29.7% |
| SSC-II | 7,595 | 23.5% |
| **Total** | **32,273** | **100%** |

### Level × Domain (`mcqs_without_answers.json` only)

| Domain | SSC-I | SSC-II | Total |
|---|---:|---:|---:|
| STEM | 8,039 | 6,565 | 14,604 |
| Social Sciences | 722 | 469 | 1,191 |
| Humanities | 516 | 441 | 957 |
| Profession | 311 | 120 | 431 |
| **Total** | **9,588** | **7,595** | **17,183** |

---

## Source Distribution

### Combined

| Source | File | Questions | % of total |
|---|---|---:|---:|
| Ustad 360 | without_answers | 13,836 | 42.9% |
| mcqtimes | with_answers | 6,170 | 19.1% |
| testpointpk | with_answers | 3,690 | 11.4% |
| etest | with_answers | 3,442 | 10.7% |
| FBISE | without_answers | 2,574 | 8.0% |
| BISE Multan 2025 | without_answers | 893 | 2.8% |
| examaunty | with_answers | 694 | 2.2% |
| gotest | with_answers | 636 | 2.0% |
| pakmcqs | with_answers | 458 | 1.4% |
| **Total** | | **32,393** | **100%** |

### mcqs_with_answers.json sources

| Source | Questions | % |
|---|---:|---:|
| mcqtimes | 6,170 | 40.9% |
| testpointpk | 3,690 | 24.5% |
| etest | 3,442 | 22.8% |
| examaunty | 694 | 4.6% |
| gotest | 636 | 4.2% |
| pakmcqs | 458 | 3.0% |
| **Total** | **15,090** | **100%** |

### mcqs_without_answers.json sources

| Source | Questions | % |
|---|---:|---:|
| Ustad 360 | 13,836 | 80.5% |
| FBISE | 2,574 | 15.0% |
| BISE Multan 2025 | 893 | 5.2% |
| **Total** | **17,183** | **100%** |
