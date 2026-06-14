# UK Address Validation & Normalization

Validate UK vendor addresses with **Postcodes.io** (free), then normalize into your storage schema with **local Qwen via Ollama**.

> You do **not** need to train a new LLM from scratch. The LLM formats messy text; **Postcodes.io** validates the postcode area.

## Architecture

```
Vendor Address
      │
      ▼
Preprocess (extract postcode, clean text)
      │
      ▼
Postcodes.io API (free postcode validation + metadata)
      │
      ▼
Qwen3 8B via Ollama (map to your JSON schema)
      │
      ▼
Standard format → Database
```

## Client address format (output schema)

```json
{
  "customer_id": "",
  "co": "",
  "street_2": "",
  "street_3": "",
  "street_house_number": "",
  "street_4": "",
  "street_5": "",
  "district": "",
  "other_city": "",
  "postal_code_city": "",
  "country": "GB",
  "time_zone": "GMTUK",
  "transportation_zone": "",
  "reg_struct_grp": "",
  "undeliverable": "",
  "po_box_address": "",
  "po_box": "",
  "postal_code": ""
}
```

See `config/schema.json` for field definitions and `GET /api/schema` for labels.

## Step-by-step setup (Mac M5, 16GB)

### Step 1 — Prerequisites

You already have Ollama and models. This project uses:

| Model | RAM | Recommendation |
|-------|-----|----------------|
| `qwen3:8b` | ~5GB | **Start here** — fast, fits 16GB comfortably |
| `qwen3:14b` | ~9GB | Slower; use only if 8B accuracy is insufficient |

```bash
ollama list   # confirm qwen3:8b is available
```

### Step 2 — Install Python dependencies

```bash
cd /Users/sanat/Address_Validation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 3 — Test postcode validation only (no LLM)

```bash
python cli.py "Flat 2, 10 high street, london, sw1a1aa" --skip-llm
```

### Step 4 — Full pipeline with Ollama

Ensure Ollama is running (`ollama serve` or the menu bar app), then:

```bash
python cli.py "Flat 2, 10 high street, london, sw1a1aa" --customer-id CUST-001
```

Batch from sample CSV:

```bash
python cli.py --file data/samples/vendor_addresses.csv
```

### Step 5 — Review UI (human corrections)

```bash
python app.py
# → http://localhost:5050
```

Open **http://localhost:5050** in your browser. You can:

1. Paste a vendor address and click **Normalize**
2. Edit the standard fields if the LLM got something wrong
3. Click **Save human correction** (stored for Phase 2 fine-tuning)
4. Upload a vendor CSV — auto-detects single-line or multi-column formats

### Step 6 — Run the API

**Normalize an address:**

```bash
curl -s -X POST http://localhost:5050/api/normalize \
  -H "Content-Type: application/json" \
  -d '{"address":"Flat 2, 10 high street, london, sw1a1aa","customer_id":"CUST-001"}' \
  | python3 -m json.tool
```

**Validate postcode only:**

```bash
curl -s -X POST http://localhost:5050/api/validate-postcode \
  -H "Content-Type: application/json" \
  -d '{"postcode":"SW1A1AA"}' | python3 -m json.tool
```

### Step 7 — Import vendor CSV (multi-column supported)

Auto-detects common headers (`delivery_address`, `addr_line1`, `post_code`, etc.).

Preview mapping:

```bash
curl -s -X POST http://localhost:5050/api/import/preview \
  -F "file=@data/samples/vendor_multi_column.csv" | python3 -m json.tool
```

Batch normalize and **download client-format CSV**:

```bash
curl -s -X POST http://localhost:5050/api/import/batch/export \
  -F "file=@data/samples/vendor_addresses.csv" \
  -F "skip_llm=true" \
  -o client_addresses.csv
```

Or via CLI:

```bash
python cli.py --file data/samples/vendor_addresses.csv --skip-llm --export-csv client_addresses.csv
```

Override column names in `config/vendor_mapping.json` → `"override"` if your vendor uses non-standard headers.

### Step 8 — Upgrade to Ideal Postcodes (street-level)

1. Sign up at [ideal-postcodes.co.uk](https://ideal-postcodes.co.uk) (free trial credits)
2. Add to `.env`:

```bash
ADDRESS_VALIDATOR=ideal_postcodes
IDEAL_POSTCODES_API_KEY=your_key_here
IDEAL_POSTCODES_MIN_CONFIDENCE=0.75
```

3. Restart `python app.py`

When confidence ≥ 0.9, the pipeline maps the validated address directly and **skips the LLM** (faster + more accurate).

### Step 9 — Human review loop (improves over time)

When staff correct an LLM output, save it for future fine-tuning:

```bash
curl -s -X POST http://localhost:5050/api/review \
  -H "Content-Type: application/json" \
  -d '{
    "vendor_address": "Flat 2, 10 high st london sw1a1aa",
    "customer_id": "CUST-001",
    "llm_output": {"street_2":"Flat 2","street_house_number":"10","street_4":"High St","other_city":"London","postal_code":"SW1A 1AA","country":"GB"},
    "human_corrected": {"street_2":"Flat 2","street_house_number":"10","street_4":"High Street","district":"Westminster","other_city":"London","postal_code":"SW1A 1AA","postal_code_city":"SW1A 1AA LONDON","country":"GB","time_zone":"GMTUK"}
  }'
```

Corrections are appended to `data/review/corrections.csv`.

### Step 10 — Run tests

```bash
python -m pytest tests/ -v
```

## Validation sources compared

| Source | Cost | Street-level? | Best for |
|--------|------|---------------|----------|
| **Postcodes.io** | Free | No — postcode area only | MVP, postcode check + city/region metadata |
| Royal Mail PAF | Paid | Yes | Production accuracy |
| Ideal Postcodes | Trial then paid | Yes | Easier API than Royal Mail |
| OS Places API | Free tier limited | Partial | Geospatial use cases |

**Important:** Postcodes.io confirms the postcode exists and returns `admin_district`, `region`, etc. It does **not** verify that "10 High Street" exists in that postcode. For production delivery validation, upgrade to Royal Mail or Ideal Postcodes.

## Phased roadmap

### Phase 1 (now) — Prompt engineering

- Postcodes.io validation
- Qwen3 8B normalization
- Store originals + outputs + human corrections

### Phase 2 (after 2k+ corrections) — LoRA fine-tune

See `docs/FINE_TUNING_PHASE2.md`.

### Phase 3 — Production

```
Vendor feed → Address Validator API → DB
```

Optionally swap Postcodes.io for Ideal Postcodes/Royal Mail when budget allows.

## Project layout

```
Address_Validation/
├── app.py                 # Flask API
├── cli.py                 # Command-line runner
├── config/schema.json     # Target storage format
├── data/
│   ├── samples/           # Test vendor addresses
│   └── training/          # Fine-tuning templates
├── docs/FINE_TUNING_PHASE2.md
├── src/address_validation/
│   ├── preprocess.py      # Extract postcode from messy text
│   ├── postcodes_io.py    # Free UK postcode API
│   ├── normalize.py       # Ollama / Qwen formatting
│   ├── pipeline.py        # Orchestrator
│   └── review_store.py    # Human correction logging
└── tests/
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `connection refused` to Ollama | Start Ollama app or `ollama serve` |
| Slow responses with 14B | Switch `.env` to `OLLAMA_MODEL=qwen3:8b` |
| No postcode found | Vendor address may lack UK postcode — reject or manual review |
| Invalid postcode | Pipeline returns 422 with error details |

## Example end-to-end

**Input (vendor):**
```
Flat 2, 10 high street, london, sw1a1aa
```

**Postcodes.io validates:** `SW1A 1AA` → region London, admin_district Westminster

**Output (client format):**
```json
{
  "customer_id": "CUST-001",
  "street_2": "Flat 2",
  "street_house_number": "10",
  "street_4": "High Street",
  "district": "Westminster",
  "other_city": "London",
  "postal_code": "SW1A 1AA",
  "postal_code_city": "SW1A 1AA LONDON",
  "country": "GB",
  "time_zone": "GMTUK"
}
```
