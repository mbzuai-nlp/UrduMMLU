#!/usr/bin/env python3
"""
Text LLM Unified 0-Shot Inference Pipeline
===========================================
Supports: Gemini, GPT (OpenAI), Claude (Anthropic), HuggingFace text LLMs,
          HuggingFace Inference API (provider: hf_inference, requires HF_TOKEN).

Usage:
    python src/run_text_experiment.py --config config.yaml
    python src/run_text_experiment.py --config config.yaml --limit 50
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from typing import Optional
from itertools import islice

import yaml
from dotenv import load_dotenv

load_dotenv()

# ===================== PATHS ===================== #

ROOT = Path(__file__).parent.parent


# ===================== COMMON HELPERS ===================== #


def load_metadata(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_results(path: Path) -> dict:
    """Load existing predictions keyed by entry id."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["id"]: r for r in json.load(f)}


def atomic_write_json(path: Path, data: list) -> None:
    """Write JSON atomically to avoid partial-write corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_system_prompt(cfg: dict, lang: str) -> str:
    return cfg["prompts"][lang]["system"].strip()


def build_user_prompt(cfg: dict, lang: str, entry: dict) -> str:
    opts = entry.get("options", {})
    template = cfg["prompts"][lang]["user_template"]
    return template.format(
        domain=entry.get("domain", ""),
        subdomain=entry.get("subdomain", ""),
        level=entry.get("level", ""),
        question=entry.get("question", ""),
        A=opts.get("A", ""),
        B=opts.get("B", ""),
        C=opts.get("C", ""),
        D=opts.get("D", ""),
    )


def safe_model_name(name: str) -> str:
    """Convert model name to a filesystem-safe string."""
    return name.replace("/", "__").replace(":", "-").replace(" ", "_")


# ===================== GEMINI ===================== #


async def _gemini_query(
    model,
    prompt: str,
    retries: int = 5,
    wait: int = 8,
) -> tuple:
    _zero = {"input": 0, "output": 0, "cached": 0}
    for attempt in range(retries):
        try:
            resp = await asyncio.to_thread(model.generate_content, prompt)
            um = getattr(resp, "usage_metadata", None)
            tokens = {
                "input": getattr(um, "prompt_token_count", 0) or 0,
                "output": getattr(um, "candidates_token_count", 0) or 0,
                "cached": getattr(um, "cached_content_token_count", 0) or 0,
            } if um else _zero
            if getattr(resp, "text", None):
                return resp.text.strip(), tokens
            return f"ERROR: finish_reason={resp.candidates[0].finish_reason}", tokens
        except Exception as exc:
            if attempt == retries - 1:
                return f"CONNECTION_FAILED: {exc}", _zero
            await asyncio.sleep(wait)
    return "CONNECTION_FAILED", _zero


async def run_gemini_pipeline(
    cfg: dict,
    lang: str,
    model_cfg: dict,
    samples: list,
    results: dict,
    out_path: Path,
) -> None:
    try:
        import google.generativeai as genai
        from google.generativeai import types
    except ImportError:
        print(
            "[ERROR] google-generativeai not installed. Run: pip install google-generativeai"
        )
        return

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_cfg["name"],
        system_instruction=get_system_prompt(cfg, lang),
        generation_config=types.GenerationConfig(
            temperature=model_cfg.get("temperature", 0),
            top_p=1,
            max_output_tokens=model_cfg.get("max_output_tokens", 16),
        ),
    )

    batch_size = cfg["experiment"]["batch_size"]
    pending = [e for e in samples if e["id"] not in results]
    total_batches = (len(pending) + batch_size - 1) // batch_size
    print(f"  [{len(pending)} pending]")

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        tasks = [_gemini_query(model, build_user_prompt(cfg, lang, e)) for e in batch]

        responses = await asyncio.gather(*tasks)
        for entry, (pred, tokens) in zip(batch, responses):
            results[entry["id"]] = {**entry, "prediction": pred, "token_used": tokens}

        atomic_write_json(out_path, list(results.values()))
        print(f"  [flush] batch {i // batch_size + 1}/{total_batches}")


# ===================== GPT (OpenAI) ===================== #


async def _gpt_query(
    client,
    model_name: str,
    prompt: str,
    system: str,
    model_cfg: dict,
    retries: int = 5,
    wait: int = 8,
) -> tuple:
    _zero = {"input": 0, "output": 0, "cached": 0}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_completion_tokens=model_cfg.get("max_completion_tokens", 16),
                temperature=model_cfg.get("temperature", 0),
                top_p=1.0,
            )
            choice = resp.choices[0]
            content = choice.message.content
            usage = getattr(resp, "usage", None)
            details = getattr(usage, "prompt_tokens_details", None)
            tokens = {
                "input": getattr(usage, "prompt_tokens", 0) or 0,
                "output": getattr(usage, "completion_tokens", 0) or 0,
                "cached": getattr(details, "cached_tokens", 0) or 0,
            } if usage else _zero

            if content and content.strip():
                return content.strip(), tokens

            return (
                f"EMPTY_OUTPUT: "
                f"finish_reason={choice.finish_reason}; "
                f"usage={usage}",
                tokens,
            )
        except Exception as exc:
            if attempt == retries - 1:
                return f"CONNECTION_FAILED: {exc}", _zero
            await asyncio.sleep(wait)
    return "CONNECTION_FAILED", _zero


async def run_gpt_pipeline(
    cfg: dict,
    lang: str,
    model_cfg: dict,
    samples: list,
    results: dict,
    out_path: Path,
) -> None:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("[ERROR] openai not installed. Run: pip install openai")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = AsyncOpenAI(api_key=api_key)
    system = get_system_prompt(cfg, lang)
    batch_size = cfg["experiment"]["batch_size"]
    pending = [e for e in samples if e["id"] not in results]
    total_batches = (len(pending) + batch_size - 1) // batch_size
    print(f"  [{len(pending)} pending]")

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        tasks = [
            _gpt_query(
                client,
                model_cfg["name"],
                build_user_prompt(cfg, lang, e),
                system,
                model_cfg,
            )
            for e in batch
        ]

        responses = await asyncio.gather(*tasks)
        for entry, (pred, tokens) in zip(batch, responses):
            results[entry["id"]] = {**entry, "prediction": pred, "token_used": tokens}

        atomic_write_json(out_path, list(results.values()))
        print(f"  [flush] batch {i // batch_size + 1}/{total_batches}")


# ===================== CLAUDE (Anthropic) ===================== #


async def _claude_query(
    client,
    model_name: str,
    prompt: str,
    system: str,
    model_cfg: dict,
    retries: int = 5,
    wait: int = 8,
) -> tuple:
    _zero = {"input": 0, "output": 0, "cached": 0}
    for attempt in range(retries):
        try:
            resp = await client.messages.create(
                model=model_name,
                max_tokens=model_cfg.get("max_tokens", 16),
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            usage = resp.usage
            tokens = {
                "input": getattr(usage, "input_tokens", 0) or 0,
                "output": getattr(usage, "output_tokens", 0) or 0,
                "cached": getattr(usage, "cache_read_input_tokens", 0) or 0,
            }
            return resp.content[0].text.strip(), tokens
        except Exception as exc:
            if attempt == retries - 1:
                return f"CONNECTION_FAILED: {exc}", _zero
            await asyncio.sleep(wait)
    return "CONNECTION_FAILED", _zero


async def run_claude_pipeline(
    cfg: dict,
    lang: str,
    model_cfg: dict,
    samples: list,
    results: dict,
    out_path: Path,
) -> None:
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        print("[ERROR] anthropic not installed. Run: pip install anthropic")
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = AsyncAnthropic(api_key=api_key)
    system = get_system_prompt(cfg, lang)
    batch_size = cfg["experiment"]["batch_size"]
    pending = [e for e in samples if e["id"] not in results]
    total_batches = (len(pending) + batch_size - 1) // batch_size
    print(f"  [{len(pending)} pending]")

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        tasks = [
            _claude_query(
                client,
                model_cfg["name"],
                build_user_prompt(cfg, lang, e),
                system,
                model_cfg,
            )
            for e in batch
        ]

        responses = await asyncio.gather(*tasks)
        for entry, (pred, tokens) in zip(batch, responses):
            results[entry["id"]] = {**entry, "prediction": pred, "token_used": tokens}

        atomic_write_json(out_path, list(results.values()))
        print(f"  [flush] batch {i // batch_size + 1}/{total_batches}")


# ===================== HUGGINGFACE INFERENCE API ===================== #


async def _hf_inference_query(
    client,
    model_name: str,
    prompt: str,
    system: str,
    model_cfg: dict,
    retries: int = 5,
    wait: int = 8,
) -> tuple:
    _zero = {"input": 0, "output": 0, "cached": 0}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=model_cfg.get("max_completion_tokens", 16),
                temperature=model_cfg.get("temperature", 0),
            )
            choice = resp.choices[0]
            content = choice.message.content
            usage = getattr(resp, "usage", None)
            tokens = {
                "input": getattr(usage, "prompt_tokens", 0) or 0,
                "output": getattr(usage, "completion_tokens", 0) or 0,
                "cached": 0,
            } if usage else _zero

            if content and content.strip():
                return content.strip(), tokens

            return (
                f"EMPTY_OUTPUT: "
                f"finish_reason={choice.finish_reason}; "
                f"usage={usage}",
                tokens,
            )
        except Exception as exc:
            if attempt == retries - 1:
                return f"CONNECTION_FAILED: {exc}", _zero
            await asyncio.sleep(wait)
    return "CONNECTION_FAILED", _zero


async def run_hf_inference_pipeline(
    cfg: dict,
    lang: str,
    model_cfg: dict,
    samples: list,
    results: dict,
    out_path: Path,
) -> None:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("[ERROR] openai not installed. Run: pip install openai")
        return

    api_key = os.getenv("HF_TOKEN")
    if not api_key:
        raise ValueError("HF_TOKEN environment variable not set")

    client = AsyncOpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=api_key,
    )

    # Append :router_suffix if hf_router is specified (e.g., "novita")
    hf_router = model_cfg.get("hf_router")
    model_name = f"{model_cfg['name']}:{hf_router}" if hf_router else model_cfg["name"]

    system = get_system_prompt(cfg, lang)
    batch_size = cfg["experiment"]["batch_size"]
    pending = [e for e in samples if e["id"] not in results]
    total_batches = (len(pending) + batch_size - 1) // batch_size
    print(f"  [{len(pending)} pending]  (HF router model: {model_name})")

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        tasks = [
            _hf_inference_query(
                client,
                model_name,
                build_user_prompt(cfg, lang, e),
                system,
                model_cfg,
            )
            for e in batch
        ]

        responses = await asyncio.gather(*tasks)
        for entry, (pred, tokens) in zip(batch, responses):
            results[entry["id"]] = {**entry, "prediction": pred, "token_used": tokens}

        atomic_write_json(out_path, list(results.values()))
        print(f"  [flush] batch {i // batch_size + 1}/{total_batches}")


# ===================== HUGGINGFACE ===================== #


def _load_hf_model(model_cfg: dict):
    """Load a HuggingFace text LLM tokenizer and model directly."""
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
    except ImportError:
        raise ImportError(
            "transformers and torch not installed. Run: pip install transformers torch"
        )

    model_name = model_cfg["name"]
    device = model_cfg.get("device", "auto")
    dtype_str = model_cfg.get("dtype", "float16")
    load_in_4bit = model_cfg.get("load_in_4bit", False)
    load_in_8bit = model_cfg.get("load_in_8bit", False)

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map.get(dtype_str, torch.float16)

    print(f"  Loading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

    load_kwargs = {
        "torch_dtype": torch_dtype,
        "device_map": device,
        "trust_remote_code": True,
    }
    if load_in_4bit:
        load_kwargs["load_in_4bit"] = True
        load_kwargs.pop("torch_dtype", None)
    elif load_in_8bit:
        load_kwargs["load_in_8bit"] = True
        load_kwargs.pop("torch_dtype", None)

    print(f"  Loading model weights: {model_name} ...")
    model = AutoModelForCausalLM.from_pretrained(model_name, **load_kwargs)
    model.eval()
    print(f"  Model loaded on device: {next(model.parameters()).device}")
    return tokenizer, model


def _query_hf_single(
    tokenizer,
    model,
    prompt: str,
    system: str,
    max_new_tokens: int,
) -> tuple:
    import torch

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    try:
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        text = f"System: {system}\nUser: {prompt}\nAssistant:"

    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False
        )

    input_len = inputs["input_ids"].shape[-1]
    generated_ids = output_ids[0][input_len:]
    tokens = {"input": input_len, "output": len(generated_ids), "cached": 0}
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip(), tokens


def run_hf_pipeline(
    cfg: dict,
    lang: str,
    model_cfg: dict,
    samples: list,
    results: dict,
    out_path: Path,
) -> None:
    system = get_system_prompt(cfg, lang)
    max_new_tokens = model_cfg.get("max_new_tokens", 16)
    flush_every = 10

    tokenizer, model = _load_hf_model(model_cfg)

    pending = [e for e in samples if e["id"] not in results]
    print(f"  [{len(pending)} pending]")

    for idx, entry in enumerate(pending):
        try:
            pred, tokens = _query_hf_single(
                tokenizer,
                model,
                build_user_prompt(cfg, lang, entry),
                system,
                max_new_tokens,
            )
        except Exception as exc:
            pred, tokens = f"ERROR: {exc}", {"input": 0, "output": 0, "cached": 0}
        results[entry["id"]] = {**entry, "prediction": pred, "token_used": tokens}

        if (idx + 1) % flush_every == 0 or (idx + 1) == len(pending):
            atomic_write_json(out_path, list(results.values()))
            print(f"  [flush] {idx + 1}/{len(pending)}")


# ===================== MAIN ===================== #


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Text LLM Unified 0-Shot Inference Pipeline"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml at project root)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override: process only the first N samples",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    lang = cfg["experiment"]["prompt_language"]
    if lang not in cfg.get("prompts", {}):
        print(f"[ERROR] prompt_language={lang!r} not found in config prompts section.")
        sys.exit(1)

    limit = args.limit if args.limit is not None else cfg["experiment"].get("limit")
    out_dir = ROOT / "output" / lang

    metadata_path = ROOT / cfg["data"]["metadata_path"]
    if not metadata_path.exists():
        print(f"[ERROR] Metadata file not found: {metadata_path}")
        sys.exit(1)

    metadata = load_metadata(metadata_path)
    samples = list(islice(metadata, limit))
    print(f"[INFO] Dataset: {len(samples)} samples  (limit={limit or 'none'})")
    print(f"[INFO] Prompt language: {lang}  →  output: {out_dir}")

    enabled_models = [m for m in cfg["models"] if m.get("enabled", False)]
    if not enabled_models:
        print(
            "[WARN] No models are enabled in config. Set `enabled: true` for at least one model."
        )
        return

    for model_cfg in enabled_models:
        provider = model_cfg["provider"]
        name = model_cfg["name"]
        out_path = out_dir / safe_model_name(name) / "predictions.json"

        print(f"\n{'='*60}")
        print(f"[RUN] provider={provider}  model={name}")
        print(f"      output -> {out_path}")
        print(f"{'='*60}")

        results = load_results(out_path)

        if provider == "gemini":
            await run_gemini_pipeline(cfg, lang, model_cfg, samples, results, out_path)
        elif provider == "gpt":
            await run_gpt_pipeline(cfg, lang, model_cfg, samples, results, out_path)
        elif provider == "claude":
            await run_claude_pipeline(cfg, lang, model_cfg, samples, results, out_path)
        elif provider == "hf_inference":
            await run_hf_inference_pipeline(cfg, lang, model_cfg, samples, results, out_path)
        elif provider == "huggingface":
            await asyncio.to_thread(
                run_hf_pipeline, cfg, lang, model_cfg, samples, results, out_path
            )
        else:
            print(f"[WARN] Unknown provider: {provider!r} — skipping.")

    print(f"\n[DONE] All enabled models completed. Results in: {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
