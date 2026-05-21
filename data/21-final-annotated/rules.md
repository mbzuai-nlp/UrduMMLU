# Stage 21 — Final-Annotated Rules

Filters `data/20-annotated-combined/mcqs.json` into the final benchmark.
Re-run `python src/final_annotated/build.py` whenever new annotations land.

## Inclusion (an MCQ must pass all)

| Check | Drop if … |
|---|---|
| Dual annotation | only one annotator submitted |
| Flag | either annotator flagged |
| Unsure | either annotator picked the UI's "unsure" / skip button |
| Valid pick | either annotator didn't pick `A`/`B`/`C`/`D` |
| Consensus | the two annotators picked different keys |
| Extras | annotator wasn't currently assigned to that batch (silent drop) |

The agreed key becomes `correct_key`. A consensus pick on the option whose
**text** happens to be "ان میں سے کوئی نہیں" (none of these) is treated as a
real answer, not an abstain — only the `selected_key = "unsure"` UI button
counts as abstention.

## Edits (question / options / subdomain)

| Case | Behaviour |
|---|---|
| Only one annotator edited a field | use that edit |
| Both edited, same value | use the agreed edit |
| Both edited, different values | use the **longer** edit |
| No edits | keep Stage-16 original |

`domain` follows the post-edit `subdomain` via a majority-vote canonical map
built from the input data. Annotators only have to edit `subdomain` to
relocate an MCQ — the domain auto-corrects.

## Output

- One file: `data/21-final-annotated/mcqs.json`, bidi marks stripped, Stage-16
  IDs preserved.
- Schema: every Stage-16 field + `correct_key` (consensus) + `annotator_metadata`
  (dict keyed by annotator name, full submitted record per annotator).
- Sidecar: `data/21-final-annotated/stats.json` (drop counts, distributions,
  overall & per-pair agreement / Cohen κ).
