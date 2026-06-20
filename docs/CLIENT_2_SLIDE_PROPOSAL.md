# Arthavi Address Validation LLM  
## 2-Slide Client Proposal (SAP CPI One-by-One Processing)

**Skywork-style deck (ready to present):** [`SAP_CPI_Address_Validation_Arthavi_LLM.pptx`](SAP_CPI_Address_Validation_Arthavi_LLM.pptx)

Regenerate: `python tools/generate_skywork_client_ppt.py`

Use the markdown below for speaker notes or copy edits.

---

## Slide 1 - Business Value & Why Arthavi LLM

### Title
**SAP CPI Address Validation with Arthavi LLM (Record-by-Record)**

### Problem Statement
- SAP CPI sends customer addresses one by one from multiple upstream sources.
- Raw inputs are inconsistent (order changes, abbreviations, missing commas, mixed casing).
- Manual correction before SAP posting slows operations and introduces errors.
- Standard postcode APIs validate locations but do not map into your custom SAP target schema.

### Proposed Solution
- Use the existing Arthavi application as an API service behind SAP CPI.
- For each incoming address:
  1) validate postcode and region context,  
  2) normalize via Arthavi fine-tuned LLM (`arthavi-address`),  
  3) return mapped fields in your required SAP structure.
- Human corrections feed retraining, so accuracy improves over time on your own data patterns.

### How the LLM Helps
- Understands messy and reordered UK addresses better than static rules.
- Splits key elements correctly into mapped fields (`co`, `street_2`, `street_3`, `street_house_number`, `street_4`, `district`, `other_city`, `postal_code`).
- Handles vendor-specific patterns that repetitive rule engines miss.
- Provides consistency at scale for CPI one-by-one transactions.

### Client Benefits
- **Higher data quality:** fewer wrong postings in SAP.
- **Faster turnaround:** less manual address cleanup.
- **Lower operational risk:** standardization before downstream processing.
- **Continuous improvement:** saved corrections become future model intelligence.
- **Data control:** local/private deployment options available.

### KPI Targets (Recommended)
- Field-level mapping accuracy: **>=95%** after stabilization.
- Manual correction rate reduction: **30-60%** in first phase.
- Processing latency: **seconds per address** in standard mode.
- Throughput: designed for CPI sequential processing with scalable API deployment.

---

## Slide 2 - Technical Flow, Cost Analysis & Delivery Model

### Title
**Architecture, Cost, and Implementation Plan**

### End-to-End Flow (SAP CPI One-by-One)
1. **SAP CPI -> Arthavi API** (`/api/normalize`) with single customer address.
2. **Preprocess Layer** extracts postcode + cleans vendor text.
3. **Validation Layer**  
   - Default: Postcodes.io (free)  
   - Optional: Ideal Postcodes (street-level confidence).
4. **Arthavi LLM Layer** (`arthavi-address` on Ollama) maps to SAP output fields.
5. **Response to CPI** with normalized schema + validation metadata.
6. **Feedback Loop** (optional UI/API correction capture) -> retrain dataset -> improved model.

### Core Tech Stack Requirements
- **API/Orchestration:** Python + Flask
- **LLM Runtime:** Ollama
- **Model:** `arthavi-address` (fine-tuned for UK address mapping)
- **Validators:** Postcodes.io (free) / Ideal Postcodes (optional premium)
- **Integration:** SAP CPI REST call per address
- **Deployment options:**  
  - Client VM/on-prem (recommended for private workloads), or  
  - Cloud Run + Ollama host VM

### Cost Analysis (Client-Friendly)
#### Option A - Cost-Optimized (Recommended Start)
- Postcodes.io + local `arthavi-address` model
- API validation cost: **£0** (Postcodes.io)
- LLM token/API cost: **£0 external** (local inference)
- Infra: existing VM/Mac or small cloud VM
- Best for pilot and fast ROI demonstration

#### Option B - Higher Validation Precision
- Ideal Postcodes + `arthavi-address`
- Validation API: pay-per-lookup (typically pence-level per record)
- Better street-level confidence signals for critical address quality use cases

### Why This Impresses Enterprise Stakeholders
- **Business + technical fit:** directly aligned to CPI one-by-one pattern.
- **Low-risk adoption:** current app already implemented; this is extension, not re-platforming.
- **Clear economics:** free-to-start model with premium validation upgrade path.
- **Governance-ready:** auditable mapping, controlled schema, retrain lifecycle.
- **Scalable roadmap:** start UK-only, extend to additional countries/rules later.

### Delivery Plan (Suggested)
- **Week 1:** CPI endpoint contract + sample payload testing.
- **Week 2:** UAT with real addresses + correction loop enabled.
- **Week 3:** Accuracy review, retrain pass, go-live recommendation.

---

## Presenter Notes (Optional)
- Emphasize this is not a generic chatbot; it is a domain-tuned mapping engine for SAP address structures.
- Position Arthavi as an intelligent normalization layer between CPI and SAP master data quality.
- Show 2-3 before/after real examples to demonstrate practical value quickly.
