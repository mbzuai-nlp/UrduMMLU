"""
Flatten data/26-hf/mcqs.json for lm-evaluation-harness.

Removes 42 items with correct_key "E" (no E option in data).
Flattens nested options dict to top-level fields.
Adds integer `answer` field (A=0, B=1, C=2, D=3).
Output: data/26-hf/mcqs_eval.jsonl
"""
import json
import pathlib

SRC = pathlib.Path("data/26-hf/mcqs.json")
DST = pathlib.Path("data/26-hf/mcqs_eval.jsonl")

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
