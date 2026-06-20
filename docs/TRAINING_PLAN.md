# UK Address Training Plan — Arthavi Address Validation

Client requirement: **no Ideal Postcodes**. Validate postcodes (free via Postcodes.io) and map messy vendor addresses into the 17-field SAP client schema — including reordered components (flat, building, house number, road, city).

---

## Architecture

```
Vendor address (any format/order)
    │
    ├─► Postcodes.io (free) ── postcode exists? district, region
    │
    └─► Fine-tuned Ollama (arthavi-address) ── street_2…postal_code + llm_validation
    │
    ▼
Client DB CSV (17 fields)
```

| Layer | Role | Cost |
|-------|------|------|
| Postcodes.io | Postcode **existence** + admin metadata | Free |
| Rule engine | Fast fallback (comma/space parsers) | Free |
| `arthavi-address` model | Order-invariant field mapping + format checks | Free (local) |

---

## Field mapping (client schema)

| Vendor concept | SAP field | Example |
|----------------|-----------|---------|
| Flat / Apartment no. | `street_2` | Apartment 7 |
| Building name | `street_3` | Elliot's Yard |
| House / building number | `street_house_number` | 8 |
| Road name | `street_4` | Gulson Road |
| City / post town | `other_city` | Coventry |
| Borough / admin area | `district` | Coventry |
| Postcode | `postal_code` | CV1 2NF |

---

## Training pipeline (implemented)

### 1. Generate dataset

```bash
cd /Users/sanat/Address_Validation
source .venv/bin/activate

# Fetch ~400 postcodes from Postcodes.io + ~2000 synthetic rows
python tools/generate_training_dataset.py --count 2000 --postcodes 400 --merge-corrections

# Outputs:
#   data/training/synthetic.jsonl
#   data/training/train.jsonl          (synthetic + human corrections)
#   data/training/postcodes_cache.json (cached lookups)
```

Each row:

```json
{
  "instruction": "Validate the UK postcode and map…",
  "input": "8 Gulson Road, Apartment 7, Elliot's Yard, Coventry CV1 2NF",
  "output": "{\"llm_validation\":{\"postcode_format_valid\":true,...},\"street_2\":\"Apartment 7\",...}"
}
```

Includes:

- Valid postcodes from Postcodes.io
- **Order permutations** (comma, space, reversed components)
- **Invalid postcodes** (~15%): bad format, non-existent (mutated valid PC)

### 2. Evaluate baseline (rules / Ollama)

```bash
# Rule-based mapper vs gold labels
python tools/evaluate_mapper.py --data data/training/synthetic.jsonl --max-rows 200

# Fine-tuned or base Ollama model
python tools/evaluate_mapper.py --use-llm --model qwen2.5:7b --max-rows 50
```

### 3. Fine-tune (Unsloth → Ollama)

```bash
python -m venv .venv-finetune
source .venv-finetune/bin/activate
pip install -r requirements-finetune.txt
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"

python tools/finetune_unsloth.py --data data/training/train.jsonl --epochs 2

ollama create arthavi-address -f artifacts/arthavi-address/Modelfile
```

Update `.env`:

```
OLLAMA_MODEL=arthavi-address
```

### 4. Human corrections (ongoing)

Use the review UI → **Save correction** → appends to `data/review/corrections.csv`.

Re-export and merge:

```bash
python tools/generate_training_dataset.py --count 2000 --merge-corrections
python tools/finetune_unsloth.py --data data/training/train.jsonl
```

---

## Production defaults (no Ideal Postcodes)

```bash
ADDRESS_VALIDATOR=postcodes_io
OLLAMA_MODEL=arthavi-address
ADDRESS_SKIP_VALIDATION=0
```

- **Validation ON** → Postcodes.io confirms postcode
- **Ollama ON** → fine-tuned model maps fields
- **Ollama OFF** → fast rule-based mode for batch

---

## Success criteria

| Metric | Target |
|--------|--------|
| Field accuracy (held-out synthetic) | ≥ 95% |
| Postcode existence (via Postcodes.io at runtime) | 100% authoritative |
| Exact match on permuted addresses | ≥ 90% after fine-tune |
| Human correction rows | 200+ for vendor-specific retrain |

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Dataset generation | 1 day | 2000+ JSONL rows |
| Baseline evaluation | 1 day | Rule vs gold report |
| Fine-tune on Mac M5 | 2–4 hours | `arthavi-address` Ollama model |
| Client sample CSV eval | 1 week | Accuracy report + corrections |
| Retrain with corrections | Quarterly | Updated model |

---

## Files

| Path | Purpose |
|------|---------|
| `tools/generate_training_dataset.py` | Build JSONL from Postcodes.io + synthetics |
| `tools/evaluate_mapper.py` | Score mapper vs gold |
| `tools/finetune_unsloth.py` | QLoRA train → GGUF → Modelfile |
| `src/address_validation/training/` | Synthetic generator, export format |
| `data/training/train.jsonl` | Merged training set |
| `artifacts/arthavi-address/` | Fine-tuned export + Modelfile |

See also: [FINE_TUNING_PHASE2.md](FINE_TUNING_PHASE2.md)
