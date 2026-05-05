# Urdu-MMLU Dataset Report

## Overview

| Category | Count |
|---|---:|
| **Total MCQs** | 58,607 |
| Original (native Urdu options) | 9,023 |
| Translated (English options + Urdu translations) | 49,584 |

## Source Breakdown

### Original MCQs

| Source | Count |
|---|---:|
| testpointpk.com | 4,076 |
| etest.com.pk | 3,608 |
| examaunty.com | 698 |
| gotest.com.pk | 641 |

### Translated MCQs

| Source | Count |
|---|---:|
| testpointpk.com | 49,584 |

## Domain Distribution

| Domain | Original | Translated | Total |
|---|---:|---:|---:|
| Social Sciences | 2,455 | 19,717 | 22,172 |
| STEM | 180 | 15,008 | 15,188 |
| Humanities | 4,481 | 2,898 | 7,379 |
| Islamic Studies | 1,152 | 5,840 | 6,992 |
| Psychology & Education | 138 | 4,052 | 4,190 |
| Law & Governance | 13 | 1,183 | 1,196 |
| Professional | 604 | 302 | 906 |
| Business & Finance | 0 | 584 | 584 |
| **Total** | **9,023** | **49,584** | **58,607** |

## Subdomain Breakdown by Domain

> Subdomain names follow standardised taxonomy slugs.

### Social Sciences &nbsp; *(Original: 2,455 · Translated: 19,717 · Total: 22,172)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `general_knowledge` | 1,153 | 8,601 | 9,754 |
| `pakistan_studies` | 1,109 | 7,789 | 8,898 |
| `international_affairs` | 16 | 1,786 | 1,802 |
| `current_affairs` | 175 | 1,448 | 1,623 |
| `social_studies` | 2 | 93 | 95 |

#### ahmer_mcqs.json — Social Sciences

| Subdomain | Count |
|---|---:|
| `general_knowledge` | 458 |

### STEM &nbsp; *(Original: 180 · Translated: 15,008 · Total: 15,188)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `everyday_science` | 157 | 10,527 | 10,684 |
| `high_school_computer_science` | 9 | 3,188 | 3,197 |
| `agriculture` | 0 | 553 | 553 |
| `civil_engineering` | 0 | 282 | 282 |
| `fine_arts` | 0 | 142 | 142 |
| `first_aid` | 0 | 133 | 133 |
| `elementary_mathematics` | 4 | 94 | 98 |
| `physical_education` | 0 | 88 | 88 |
| `electrical_engineering` | 10 | 0 | 10 |
| `high_school_biology` | 0 | 1 | 1 |

### Humanities &nbsp; *(Original: 4,481 · Translated: 2,898 · Total: 7,379)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `urdu_language` | 3,240 | 2,265 | 5,505 |
| `sindhi_language` | 330 | 384 | 714 |
| `urdu_grammar` | 469 | 0 | 469 |
| `pakistan_studies` | 223 | 54 | 277 |
| `urdu_literature` | 214 | 0 | 214 |
| `english_language` | 5 | 195 | 200 |

#### ahmer_mcqs.json — Humanities

| Subdomain | Count |
|---|---:|
| `urdu_literature` | 4,558 |
| `urdu_language` | 1,612 |

### Islamic Studies &nbsp; *(Original: 1,152 · Translated: 5,840 · Total: 6,992)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `islamic_studies` | 1,085 | 4,823 | 5,908 |
| `hajj_management` | 67 | 1,017 | 1,084 |

### Psychology & Education &nbsp; *(Original: 138 · Translated: 4,052 · Total: 4,190)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `pedagogy` | 10 | 3,769 | 3,779 |
| `psychometrics` | 126 | 81 | 207 |
| `professional_psychology` | 2 | 197 | 199 |
| `analytical_reasoning` | 0 | 5 | 5 |

### Law & Governance &nbsp; *(Original: 13 · Translated: 1,183 · Total: 1,196)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `criminal_and_civil_law` | 0 | 771 | 771 |
| `security_law` | 0 | 146 | 146 |
| `federal_investigation_law` | 13 | 66 | 79 |
| `tax_law` | 0 | 43 | 43 |
| `election_law` | 0 | 43 | 43 |
| `criminal_law` | 0 | 43 | 43 |
| `anti_corruption_law` | 0 | 36 | 36 |
| `drug_control_law` | 0 | 13 | 13 |
| `financial_regulation_law` | 0 | 11 | 11 |
| `public_administration` | 0 | 9 | 9 |
| `counter_terrorism_law` | 0 | 2 | 2 |

### Professional &nbsp; *(Original: 604 · Translated: 302 · Total: 906)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `professional_development` | 600 | 0 | 600 |
| `photography` | 0 | 201 | 201 |
| `clerical_services` | 4 | 91 | 95 |
| `stenography` | 0 | 6 | 6 |
| `professional_medicine` | 0 | 4 | 4 |

### Business & Finance &nbsp; *(Original: 0 · Translated: 584 · Total: 584)*

| Subdomain | Original | Translated | Total |
|---|---:|---:|---:|
| `professional_accounting` | 0 | 382 | 382 |
| `agricultural_banking` | 0 | 196 | 196 |
| `tax_administration` | 0 | 6 | 6 |

## Standardised Taxonomy Reference

Subdomain slugs are based on the project's Taxonomy.pdf with Pakistan-specific
extensions for Islamic Studies, Law & Governance, and local professional domains.

| Domain | Subdomain slug | Description |
|---|---|---|
| Business & Finance | `agricultural_banking` | ZTBL OG III Job Related MCQs |
| Business & Finance | `professional_accounting` | Accounting MCQs PDF |
| Business & Finance | `tax_administration` | Inspector Inland Revenue MCQs PDF |
| Humanities | `english_language` | English 1000 Important MCQs 2026 PDF from Past Papers |
| Humanities | `pakistan_studies` | Pakistan Study MCQs in Urdu |
| Humanities | `sindhi_language` | Sindhi Language MCQs PDF |
| Humanities | `urdu_grammar` | Urdu Grammar MCQs |
| Humanities | `urdu_language` | Urdu Mcqs |
| Humanities | `urdu_literature` | Urdu Language Adab (Literature) Info Test Online |
| Islamic Studies | `hajj_management` | Top 1000 MCQs for Moavineen-e-Hujjaj / Nazims for Hajj Op… |
| Islamic Studies | `islamic_studies` | Islamic Studies MCQs Urdu PDF |
| Law & Governance | `anti_corruption_law` | NAB Ordinance, 1999 MCQs PDF |
| Law & Governance | `counter_terrorism_law` | CTD Law, Functions, NACTA, FATF, Terrorism, National Acti… |
| Law & Governance | `criminal_and_civil_law` | LAW MCQs (Top 100 CrPc, PPC, QSO, General Laws, MPL, Civi… |
| Law & Governance | `criminal_law` | Jail Police Prisons Act |
| Law & Governance | `drug_control_law` | ANF Act 1997 MCQs PDF |
| Law & Governance | `election_law` | Election Act 2017 MCQs PDF |
| Law & Governance | `federal_investigation_law` | FIA Act MCQs PDF |
| Law & Governance | `financial_regulation_law` | PERA Act 2024 MCQs PDF |
| Law & Governance | `public_administration` | Public Administration Past Papers MCQs PDF |
| Law & Governance | `security_law` | Security Measures to Maintain Law & Order (ASF Act, 1975)… |
| Law & Governance | `tax_law` | FBR Act & Job Related MCQs PDF |
| Professional | `clerical_services` | Assistant , UDC, LDC Jobs Related Q MCQs PDF |
| Professional | `photography` | Photographer Job related MCQs for Test Preparation |
| Professional | `professional_development` | Interview MCQs |
| Professional | `professional_medicine` | Medical Officer, Women Medical Officer Post Related MCQs PDF |
| Professional | `stenography` | Stenotypist & Shorthand Past Papers Question MCQs (Downlo… |
| Psychology & Education | `analytical_reasoning` | Analytical Reasoning Past Papers MCQs PDF |
| Psychology & Education | `pedagogy` | Pedagogy MCQs 2026 PDF for Teacher, Lecturer, Professor P… |
| Psychology & Education | `professional_psychology` | Psychology MCQ PDF |
| Psychology & Education | `psychometrics` | Psychological Assessment MCQs PDF 2026 |
| STEM | `agriculture` | Agriculture MCQs 2026 for all Test Preparations |
| STEM | `civil_engineering` | Sub Engineer Civil Past Papers MCQs PDF |
| STEM | `electrical_engineering` | Engineering MCQs |
| STEM | `elementary_mathematics` | Math MCQs Urdu PDF |
| STEM | `everyday_science` | Everyday Science MCQs |
| STEM | `fine_arts` | Drawing Master Questions, MCQs for Tests and Worksheets |
| STEM | `first_aid` | First Aid MCQs PDF |
| STEM | `high_school_biology` | General Science MCQs (Class 4 to 12) |
| STEM | `high_school_computer_science` | Computer 1000 Important MCQs 2026 PDF from Past Papers |
| STEM | `physical_education` | Top 100 Physical Education MCQs for Test Preparations PDF |
| Social Sciences | `current_affairs` | Current Affairs MCQs |
| Social Sciences | `general_knowledge` | General Knowledge (GK) 1000 Important MCQs 2026 PDF from … |
| Social Sciences | `international_affairs` | International Affairs MCQs |
| Social Sciences | `pakistan_studies` | Pak Studies 1000 Important MCQs PDF 2026 from Past Papers |
| Social Sciences | `public_administration` | Public Administration Past Papers MCQs PDF |
| Social Sciences | `social_studies` | Social Studies Past Papers MCQs Questions PDF |
