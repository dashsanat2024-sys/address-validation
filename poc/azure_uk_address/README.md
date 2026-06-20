# Azure AI UK Address Validation POC

Proof-of-concept for UK vendor address validation and SAP field mapping using **Azure OpenAI**, aligned with the main Arthavi Address Validation app (`arthavi-address` / Ollama).

## Folder structure

```
poc/azure_uk_address/
├── README.md
├── .env.example
├── requirements.txt
├── run_poc.py                 # CLI entry point
├── prompts/
│   └── system_prompt.txt      # Production-aligned system prompt
├── examples/
│   └── addresses.json         # Sample addresses + expected mapping
├── results/                   # JSON output from runs (gitignored)
└── src/
    ├── azure_client.py        # Azure OpenAI call + JSON parse
    ├── prompts.py             # Prompt builders
    ├── postcode_validate.py   # Postcodes.io lookup (free)
    ├── schema.py              # StandardAddress (SAP fields)
    └── cost_analysis.py       # Token usage + USD cost projections
```

## Credentials: OpenAI vs Azure OpenAI

These are **different** — you cannot put an `OPENAI_API_KEY` into the Azure fields.

| | Direct OpenAI | Azure OpenAI |
|--|---------------|--------------|
| Where you get the key | [platform.openai.com](https://platform.openai.com) | Azure Portal → your OpenAI resource |
| `.env` variables | `OPENAI_API_KEY`, `OPENAI_MODEL` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` |
| Model name | `gpt-4o-mini` (model id) | Your deployment name (e.g. `gpt-4o-mini`) |

**Direct OpenAI** (simplest for POC):

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Azure OpenAI** (enterprise / Azure billing):

```env
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
```

If only `OPENAI_API_KEY` is set (no Azure endpoint), the POC auto-uses direct OpenAI.

## Quick start

```bash
cd poc/azure_uk_address
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — use EITHER OpenAI OR Azure (see below)

# Dry run — prompts + token estimate only (no API key needed)
python run_poc.py --dry-run

# Live run with default example address
python run_poc.py

# Custom address
python run_poc.py --address "Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF"
```

## Default example address

```
Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF
```

**Expected mapping** (from human corrections in main app):

| Field | Value |
|-------|-------|
| street_2 | APARTMENT 7 |
| street_3 | ELLIOT'S YARD |
| street_house_number | 8 |
| street_4 | GULSON ROAD |
| district | COVENTRY |
| other_city | COVENTRY |
| postal_code | CV1 2NF |
| postal_code_city | CV1 2NF COVENTRY |
| country | GB |
| time_zone | GMTUK |

## Prompt design

The system prompt mirrors `src/address_validation/normalize.py` in the main app:

1. **Validate** — UK postcode format + Postcodes.io metadata injected into user message
2. **Normalize** — Azure OpenAI maps vendor text to 17 SAP fields
3. **Post-process** — `StandardAddress` Pydantic model enforces postcode format, country=GB, postal_code_city

The user prompt includes:
- Original vendor address
- Postcodes.io validation context (post town, admin district)
- Optional `rule_parser_hint` for reversed space-separated addresses

## Token usage & cost analysis

Each run reports:

| Metric | Source |
|--------|--------|
| `prompt_tokens` | Azure API `usage.prompt_tokens` |
| `completion_tokens` | Azure API `usage.completion_tokens` |
| `total_tokens` | Azure API `usage.total_tokens` |
| Offline estimate | `tiktoken` (dry-run mode) |

Cost is calculated from configurable USD pricing per 1M tokens:

| Model | Input / 1M | Output / 1M |
|-------|------------|-------------|
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4.1-mini | $0.40 | $1.60 |
| gpt-4.1 | $2.00 | $8.00 |

Override via `.env`:
```
AZURE_INPUT_PRICE_PER_1M=0.15
AZURE_OUTPUT_PRICE_PER_1M=0.60
```

**Volume projections** (per request cost × volume):
- 1,000 addresses
- 10,000 addresses
- 100,000 addresses
- 1,000,000 addresses

### Illustrative cost (gpt-4o-mini, ~900 prompt + ~180 completion tokens)

| Volume | Est. cost (USD) |
|--------|-----------------|
| 1 address | ~$0.00025 |
| 1,000 | ~$0.25 |
| 10,000 | ~$2.50 |
| 100,000 | ~$25 |
| 1,000,000 | ~$250 |

*Run `python run_poc.py` for exact token counts from your deployment.*

## Azure vs local Ollama (`arthavi-address`)

| | Azure OpenAI POC | Main app (Ollama) |
|--|------------------|-------------------|
| Cost per address | ~$0.0002–0.003 (model dependent) | $0 (local inference) |
| Latency | 1–3 s (network) | 5–30 s (local, cold start) |
| Data privacy | Sent to Azure | Stays on-prem |
| Fine-tuning | Azure fine-tuning / prompt only | `arthavi-address` LoRA |
| Best for | Client POC, compare quality | Production CPI |

## Output

Results are saved to `results/poc_YYYYMMDD_HHMMSS.json` with:
- Normalized SAP fields
- `llm_validation` block
- Full prompts (system + user)
- Token usage and cost breakdown
- Latency in ms

## Compare with main app

```bash
# Main app (local Ollama)
curl -s -X POST http://localhost:5050/api/normalize \
  -H "Content-Type: application/json" \
  -d '{"vendor_address": "Apartment 7 Elliot'\''s Yard 8 Gulson Road Coventry CV1 2NF"}'
```
