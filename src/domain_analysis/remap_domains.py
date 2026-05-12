"""
Remap domains and normalize subdomains in MCQ JSON files.
Output is written to clean_data/ preserving the original filename.

Final domains: STEM, Humanities, Social Sciences, Profession, Other

Run from repo root:
    python domain_analysis/remap_domains.py data/mcqs_with_answers.json
    python domain_analysis/remap_domains.py data/mcqs_without_answers.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

OUTPUT_DIR = Path("clean_data")

# Aliases to fix inconsistent subdomain names before domain mapping.
# All values use snake_case lowercase.
SUBDOMAIN_ALIASES = {
    # Spacing / punctuation variants
    "pakistan studies":                           "pakistan_studies",
    "islamic studies":                            "islamic_studies",
    "tarjamatul quran ul majeed":                 "tarjamatul_quran",
    "d.science":                                  "general_science",
    "general science":                            "general_science",
    "health and physical education":              "health_and_physical_education",
    "art and model drawing":                      "art_and_model_drawing",
    "computer science":                           "computer_science",
    "home economics":                             "home_economics",
    "food and nutrition":                         "food_and_nutrition",
    "clothing and textile":                       "clothing_and_textile",
    "dress making and fashion designing":         "dress_making_and_fashion_designing",
    "electrical and wiring":                      "electrical_and_wiring",
    "internet of things":                         "internet_of_things",
    "media production":                           "media_production",
    "plumbing and solar water heating system-ii": "plumbing_and_solar_water_heating",
    # Language subjects stored without _language suffix
    "urdu":    "urdu_language",
    "arabic":  "arabic_language",
    "punjabi": "punjabi_language",
}

# Explicit subdomain → final domain mapping.
# Takes priority over any existing domain value on the item.
SUBDOMAIN_TO_DOMAIN = {
    # ── Humanities ──────────────────────────────────────────────────────────
    "islamic_studies":          "Humanities",
    "tarjamatul_quran":         "Humanities",
    "ethics":                   "Humanities",
    "urdu_language":            "Humanities",
    "urdu_literature":          "Humanities",
    "urdu_grammar":             "Humanities",
    "sindhi_language":          "Humanities",
    "english_language":         "Humanities",
    "arabic_language":          "Humanities",
    "punjabi_language":         "Humanities",
    "art_and_model_drawing":    "Humanities",

    # ── STEM ────────────────────────────────────────────────────────────────
    "biology":                      "STEM",
    "chemistry":                    "STEM",
    "physics":                      "STEM",
    "mathematics":                  "STEM",
    "computer_science":             "STEM",
    "general_science":              "STEM",
    "high_school_computer_science": "STEM",
    "electrical_engineering":       "STEM",
    "elementary_mathematics":       "STEM",
    "everyday_science":             "STEM",

    # ── Social Sciences ─────────────────────────────────────────────────────
    "pakistan_studies":              "Social Sciences",
    "civics":                        "Social Sciences",
    "pedagogy":                      "Social Sciences",
    "psychometrics":                 "Social Sciences",
    "health_and_physical_education": "Social Sciences",
    "education":                     "Social Sciences",
    "current_affairs":               "Social Sciences",
    "international_affairs":         "Social Sciences",
    "social_studies":                "Social Sciences",
    "economics":                     "Social Sciences",
    "geography":                     "Social Sciences",

    # ── Profession ──────────────────────────────────────────────────────────
    "hajj_management":                    "Profession",
    "professional_development":           "Profession",
    "clerical_services":                  "Profession",
    "clothing_and_textile":               "Profession",
    "dress_making_and_fashion_designing": "Profession",
    "electrical_and_wiring":             "Profession",
    "food_and_nutrition":                 "Profession",
    "home_economics":                     "Profession",
    "internet_of_things":                 "Profession",
    "media_production":                   "Profession",
    "plumbing_and_solar_water_heating":   "Profession",
    "tourism":                            "Profession",

    # ── Other ────────────────────────────────────────────────────────────────
    "general_knowledge":         "Other",
    "federal_investigation_law": "Other",
    "professional_psychology":   "Other",
}

FINAL_DOMAINS = {"STEM", "Humanities", "Social Sciences", "Profession", "Other"}

# Fallback: legacy domain names → final domain (used when subdomain has no explicit mapping)
DOMAIN_RENAME = {
    "Professional":           "Profession",
    "Islamic Studies":        "Humanities",
    "Law & Governance":       "Other",
    "Languages":              "Humanities",
    "Psychology & Education": "Other",  # individual subdomains override via SUBDOMAIN_TO_DOMAIN
}


def normalize_subdomain(raw: str) -> str:
    key = raw.strip().lower()
    if key in SUBDOMAIN_ALIASES:
        return SUBDOMAIN_ALIASES[key]
    return key.replace(" ", "_")


def remap_item(item: dict) -> dict:
    sub = normalize_subdomain(item.get("subdomain", ""))
    item["subdomain"] = sub

    if sub in SUBDOMAIN_TO_DOMAIN:
        item["domain"] = SUBDOMAIN_TO_DOMAIN[sub]
    else:
        current = item.get("domain", "")
        if current in FINAL_DOMAINS:
            pass  # already a valid final domain
        elif current in DOMAIN_RENAME:
            item["domain"] = DOMAIN_RENAME[current]
        else:
            item["domain"] = "Other"

    return item


def domain_stats(data: list) -> dict:
    counts = defaultdict(int)
    for item in data:
        counts[item.get("domain", "")] += 1
    return dict(counts)


def subdomain_stats(data: list) -> dict:
    tree = defaultdict(lambda: defaultdict(int))
    for item in data:
        tree[item.get("domain", "")][item.get("subdomain", "")] += 1
    return {d: dict(subs) for d, subs in sorted(tree.items())}


def main():
    parser = argparse.ArgumentParser(description="Remap domains and normalize subdomains.")
    parser.add_argument("input", help="Path to input JSON file (e.g. data/mcqs_with_answers.json)")
    args = parser.parse_args()

    input_path = Path(args.input)
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / input_path.name

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    before = domain_stats(data)
    data = [remap_item(item) for item in data]
    after = subdomain_stats(data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"  {input_path}  ({sum(before.values())} items)")
    print(f"  Saved → {output_path}")
    print(f"{'='*55}")
    print(f"  {'Domain':<25}  {'Before':>7}  {'After':>7}")
    print(f"  {'-'*25}  {'-'*7}  {'-'*7}")
    for d in sorted(set(before) | set(after)):
        b = before.get(d, 0)
        a = sum(after.get(d, {}).values())
        print(f"  {d:<25}  {b:>7}  {a:>7}")

    print(f"\n  Subdomain breakdown after remapping:")
    for domain, subs in after.items():
        print(f"    [{domain}]")
        for sub, cnt in sorted(subs.items(), key=lambda x: -x[1]):
            print(f"      {sub}: {cnt}")

    print("\nDone.")


if __name__ == "__main__":
    main()
