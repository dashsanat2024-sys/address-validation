#!/usr/bin/env python3
"""
Fine-tune Qwen for UK address mapping with Unsloth → export GGUF → Ollama.

Requires: pip install -r requirements-finetune.txt
Run on Apple Silicon: uses MPS when available.

Usage:
  python tools/generate_training_dataset.py --merge-corrections
  python tools/finetune_unsloth.py --data data/training/train.jsonl
  ollama create arthavi-address -f artifacts/arthavi-address/Modelfile
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "training" / "train.jsonl"
DEFAULT_OUT = ROOT / "artifacts" / "arthavi-address"


def load_jsonl_messages(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(
                {
                    "instruction": row.get("instruction", ""),
                    "input": row.get("input", ""),
                    "output": row.get("output", ""),
                }
            )
    return rows


def to_chat_text(instruction: str, user_input: str, output: str) -> dict:
    system = instruction.strip()
    user = user_input.strip()
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": output},
        ]
    }


def write_modelfile(gguf_path: Path, out_dir: Path) -> None:
    modelfile = out_dir / "Modelfile"
    modelfile.write_text(
        f"""FROM {gguf_path.resolve()}
PARAMETER temperature 0.1
PARAMETER num_predict 512
SYSTEM You are a UK address validation and normalization assistant. Output JSON only with llm_validation and client address fields.
""",
        encoding="utf-8",
    )


def _device_config(base_model: str) -> dict:
    import torch

    if torch.cuda.is_available():
        return {
            "model_name": base_model or "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
            "load_in_4bit": True,
            "dtype": None,
        }
    if torch.backends.mps.is_available():
        # 16GB Mac: 7B OOM — Unsloth uses MLX backend; omit dtype (defaults to float16)
        return {
            "model_name": "unsloth/Qwen2.5-3B-Instruct",
            "load_in_4bit": False,
            "dtype": None,
            "use_mlx": True,
        }
    return {
        "model_name": base_model or "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
        "load_in_4bit": True,
        "dtype": None,
        "use_mlx": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune address model with Unsloth")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--max-seq-length", type=int, default=512)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--dry-run", action="store_true", help="Validate dataset only")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Training file not found: {args.data}", file=sys.stderr)
        print("Run: python tools/generate_training_dataset.py --merge-corrections", file=sys.stderr)
        return 1

    raw = load_jsonl_messages(args.data)
    if len(raw) < 100:
        print(f"Warning: only {len(raw)} rows — recommend 1000+ for fine-tuning.", file=sys.stderr)

    dataset = [to_chat_text(r["instruction"], r["input"], r["output"]) for r in raw]
    print(f"Loaded {len(dataset)} training examples from {args.data}")

    if args.dry_run:
        print("Dry run OK.")
        return 0

    try:
        from unsloth import FastLanguageModel
        from datasets import Dataset
    except ImportError:
        print(
            "Unsloth not installed. Create env and install:\n"
            "  python -m venv .venv-finetune && source .venv-finetune/bin/activate\n"
            "  pip install -r requirements-finetune.txt",
            file=sys.stderr,
        )
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    dev = _device_config(args.base_model)
    print(f"Device config: model={dev['model_name']} 4bit={dev['load_in_4bit']} mlx={dev.get('use_mlx')}")

    load_kwargs = {
        "model_name": dev["model_name"],
        "max_seq_length": args.max_seq_length,
        "load_in_4bit": dev["load_in_4bit"],
    }
    if dev["dtype"] is not None:
        load_kwargs["dtype"] = dev["dtype"]

    model, tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_r * 2,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    def formatting_func(example):
        messages = example["messages"]
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)

    hf_dataset = Dataset.from_list(dataset)

    if dev.get("use_mlx"):
        from unsloth_zoo.mlx.trainer import MLXTrainer, MLXTrainingConfig

        trainer = MLXTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=hf_dataset,
            formatting_func=formatting_func,
            max_seq_length=args.max_seq_length,
            args=MLXTrainingConfig(
                output_dir=str(args.output_dir / "checkpoints"),
                num_train_epochs=args.epochs,
                per_device_train_batch_size=1,
                gradient_accumulation_steps=8,
                learning_rate=args.learning_rate,
                logging_steps=10,
                max_seq_length=args.max_seq_length,
            ),
        )
    else:
        from trl import SFTTrainer
        from transformers import TrainingArguments

        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=hf_dataset,
            formatting_func=formatting_func,
            args=TrainingArguments(
                output_dir=str(args.output_dir / "checkpoints"),
                num_train_epochs=args.epochs,
                per_device_train_batch_size=args.batch_size,
                gradient_accumulation_steps=4,
                learning_rate=args.learning_rate,
                logging_steps=10,
                save_steps=200,
                fp16=True,
                bf16=False,
                optim="adamw_8bit",
                report_to="none",
            ),
        )

    print("Starting fine-tune…")
    trainer.train()

    merged_dir = args.output_dir / "merged"
    print(f"Saving merged weights → {merged_dir}")
    if dev.get("use_mlx"):
        model.save_pretrained_merged(str(merged_dir), tokenizer)
    else:
        model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")

    print(f"Exporting GGUF → {args.output_dir}")
    if dev.get("use_mlx"):
        model.save_pretrained_gguf(str(args.output_dir), tokenizer, quantization_method="q4_k_m")
    else:
        model.save_pretrained_gguf(str(args.output_dir), tokenizer, quantization_method="q4_k_m")

    # Unsloth may write with model name; find gguf
    ggufs = list(args.output_dir.glob("*.gguf"))
    if ggufs:
        gguf_path = ggufs[0]

    write_modelfile(gguf_path, args.output_dir)
    print(f"\nDone. Create Ollama model:\n  ollama create arthavi-address -f {args.output_dir / 'Modelfile'}")
    print("Then set .env: OLLAMA_MODEL=arthavi-address")
    return 0


def _use_mps() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
