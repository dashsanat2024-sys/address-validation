# Phase 2: Fine-tune Qwen with LoRA

**Full client-facing plan:** [TRAINING_PLAN.md](TRAINING_PLAN.md)

## Quick start

```bash
# 1. Generate 2000+ training rows (Postcodes.io + synthetics)
python tools/generate_training_dataset.py --count 2000 --postcodes 400 --merge-corrections

# 2. Evaluate rule-based baseline
python tools/evaluate_mapper.py --data data/training/synthetic.jsonl --max-rows 200

# 3. Fine-tune (separate env — see requirements-finetune.txt)
python tools/finetune_unsloth.py --data data/training/train.jsonl
ollama create arthavi-address -f artifacts/arthavi-address/Modelfile
```

Human corrections export now includes `llm_validation` in each JSONL row automatically.

---

## Legacy notes

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

## LLM-only validation mode (no Postcodes.io)

Set `ADDRESS_SKIP_VALIDATION=1` or uncheck **External validation** in the UI.

Ollama then:
1. Checks UK postcode **format** (regex-backed in code).
2. Assesses postcode **plausibility** vs city (model knowledge — not a live registry).
3. Maps to your 17-field client schema.

**Limits:** An LLM cannot replace Postcodes.io for *existence* checks (retired postcodes, wrong sector).
Use hybrid mode (validator + Ollama) for production database loads.

## Fine-tune for validation + mapping (Phase 2+)

Yes — you can train the local model on **both** tasks in one JSON output:

```json
{
  "llm_validation": {
    "postcode_format_valid": true,
    "postcode_plausible": true,
    "validation_notes": ""
  },
  "postal_code": "SW1A 1AA",
  "other_city": "LONDON",
  "street_house_number": "10",
  "street_4": "Downing Street"
}
```

Training data sources:
- `data/review/corrections.csv` — human fixes (best quality).
- Synthetic pairs: vendor text → corrected JSON with `llm_validation` labels.
- Optional: merge Postcodes.io lookup results as `postcode_plausible=true` examples.

Recommended approach:
1. **Months 1–2:** Prompt engineering + optional external validator (current default).
2. **Months 3+:** LoRA on Qwen3 8B with 2,000+ correction rows including validation labels.
3. **Production:** Keep Postcodes.io as optional toggle; use fine-tuned Ollama for mapping and format checks on messy vendor data.

Export instruction JSONL from corrections (extend `review_store` to emit `llm_validation` when you start Phase 2).
