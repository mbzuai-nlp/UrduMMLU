"""
Flatten data/26-eval/mcqs.json for lm-evaluation-harness.

Flattens nested options dict to top-level fields.
Adds integer `answer` field (A=0, B=1, C=2, D=3).
Output: data/26-eval/mcqs_eval.jsonl

The non-ABCD skip below is now a no-op assertion: the 42 items whose gold answer
landed outside A-D are dropped upstream by src/eval_snapshot/build.py, so this
script emits every record it reads. It used to be the only place they were
removed, which is why mcqs_eval.jsonl (26,389) disagreed with mcqs.json (26,431).
A non-zero `skipped` count means the upstream repair regressed.

Operates on the frozen eval snapshot (original ids), NOT the sorted/renumbered
Hugging Face release (data/27-hf/).
"""
import json
import pathlib

SRC = pathlib.Path("data/26-eval/mcqs.json")
DST = pathlib.Path("data/26-eval/mcqs_eval.jsonl")

data = json.loads(SRC.read_text(encoding="utf-8"))
key_to_idx = {"A": 0, "B": 1, "C": 2, "D": 3}

kept, skipped = 0, 0
with DST.open("w", encoding="utf-8") as f:
    for d in data:
        if d["correct_key"] not in key_to_idx:
            skipped += 1
            continue
        row = {
            "id": d["id"],
            "question": d["question"],
            "option_a": d["options"]["A"],
            "option_b": d["options"]["B"],
            "option_c": d["options"]["C"],
            "option_d": d["options"]["D"],
            "answer": key_to_idx[d["correct_key"]],
            "domain": d["domain"],
            "subdomain": d["subdomain"],
            "level": d["level"],
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        kept += 1

print(f"Written {kept} items to {DST}  (skipped {skipped} non-ABCD items)")
