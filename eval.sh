#!/bin/bash
# =============================================================================
# Urdu MMLU — zero-shot, 3-shot, 5-shot evaluation via lm-evaluation-harness
#
# Models  : Llama-3.2-3B-Instruct | gemma-3-4b-it | Phi-4-mini-instruct
# Shots   : 0, 3, 5  (tasks registered in lm-eval-harness as urdummlu_*)
# Metric  : exact_match on "Answer key: X" (generate_until)
# Data    : data/26-hf/mcqs.json (test) | data/26-hf/mcqs_dev.json (few-shot)
# Results : output/lm_eval/<model_slug>/
#
# Each model is loaded once and all three shot configs are evaluated together.
#
# Requirements:
#   pip install lm-eval accelerate
#   Task registered at:
#     lm_eval/tasks/urdummlu/  (inside lm-evaluation-harness install)
# =============================================================================

set -uo pipefail

# ── Knobs ────────────────────────────────────────────────────────────────────
SEED=42
BATCH_SIZE=4         # generate_until is heavier than loglikelihood; drop if OOM
DEVICE=auto          # "cuda", "cuda:0", "mps", or "auto"
OVERWRITE=false      # true = re-run even if results exist
LIMIT=20             # null = full dataset; integer = first N samples (testing only)

# All three shot configs evaluated in one pass per model (single model load).
TASKS="urdummlu_zeroshot,urdummlu_3shot,urdummlu_5shot"
RESULTS_DIR="$(pwd)/output/lm_eval"

MODELS=(
    "meta-llama/Llama-3.2-1B"
)

# ── Helper ───────────────────────────────────────────────────────────────────
model_slug() { echo "$1" | tr '/' '__'; }

run_eval() {
    local model="$1"
    local slug
    slug=$(model_slug "${model}")
    local out="${RESULTS_DIR}/${slug}"

    if [ "${OVERWRITE}" = false ] && compgen -G "${out}/results_*.json" > /dev/null 2>&1; then
        echo "(skip — results exist) ${slug}"
        return 0
    fi

    mkdir -p "${out}"
    echo ""
    echo "==> ${slug}"

    lm-eval \
        --model hf \
        --model_args "pretrained=${model},dtype=bfloat16,trust_remote_code=True" \
        --tasks "${TASKS}" \
        --batch_size "${BATCH_SIZE}" \
        --device "${DEVICE}" \
        --log_samples \
        --output_path "${out}" \
        --seed "${SEED}" \
        ${LIMIT:+--limit "${LIMIT}"}

    # Uncomment to score instruction-tuned models with their chat templates:
    # --apply_chat_template \
    # --fewshot_as_multiturn \
}

# ── Main loop ────────────────────────────────────────────────────────────────
mkdir -p "${RESULTS_DIR}"

for MODEL in "${MODELS[@]}"; do
    run_eval "${MODEL}" || {
        echo -e "\033[31mFAILED: ${MODEL} (continuing)\033[0m"
    }
done

# ── Summary table ────────────────────────────────────────────────────────────
echo ""
echo "All runs done. Results: ${RESULTS_DIR}/"
echo ""

python3 - <<'PY'
import json, glob, os

results_dir = "output/lm_eval"
task_order = ["urdummlu_zeroshot", "urdummlu_3shot", "urdummlu_5shot"]
label_map  = {"urdummlu_zeroshot": "0-shot", "urdummlu_3shot": "3-shot", "urdummlu_5shot": "5-shot"}

rows = []
for result_file in sorted(glob.glob(f"{results_dir}/**/results_*.json", recursive=True)):
    with open(result_file) as f:
        data = json.load(f)
    slug = result_file.replace(results_dir + "/", "").split("/")[0]
    model = slug.replace("__", "/")
    task_results = data.get("results", {})
    for task in task_order:
        if task not in task_results:
            continue
        acc = task_results[task].get("exact_match,none") or task_results[task].get("exact_match")
        rows.append((model, label_map[task], acc))

if not rows:
    print("No results found yet.")
else:
    print(f"{'Model':<48} {'Setting':<10} {'Exact Match %':>14}")
    print("-" * 76)
    for model, setting, acc in rows:
        acc_s = f"{acc*100:.2f}" if acc is not None else "—"
        print(f"{model:<48} {setting:<10} {acc_s:>14}")
PY
