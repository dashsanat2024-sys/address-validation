# Phase 2: Fine-tune Qwen with LoRA (optional)

Only start this after you have **2,000+ human-corrected** rows in `data/review/corrections.csv`.

## 1. Export training data

```bash
python -c "
from pathlib import Path
from address_validation.review_store import corrections_to_instruction_jsonl
import sys
sys.path.insert(0, 'src')
corrections_to_instruction_jsonl(
    Path('data/review/corrections.csv'),
    Path('data/training/from_corrections.jsonl'),
)
"
```

## 2. Install Unsloth (separate env recommended)

On 16GB Mac, use **Qwen3 8B** (not 14B) with 4-bit QLoRA:

```bash
python -m venv .venv-finetune
source .venv-finetune/bin/activate
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
```

## 3. Fine-tune script outline

- Base model: `Qwen/Qwen3-8B` (or your Ollama base)
- LoRA rank: 16
- Max seq length: 512 (addresses are short)
- Epochs: 2–3
- Merge LoRA → export GGUF → `ollama create arthavi-address -f Modelfile`

## 4. Modelfile for Ollama

```
FROM ./arthavi-address-q4_k_m.gguf
PARAMETER temperature 0.1
SYSTEM You are a UK address normalization assistant. Output JSON only.
```

```bash
ollama create arthavi-address -f Modelfile
```

Update `.env`: `OLLAMA_MODEL=arthavi-address`

## When prompting is enough

For structured UK address formatting, **prompt + Postcodes.io** often reaches >90% accuracy.
Fine-tune when you see repeated mistakes on your vendor's specific address style.
