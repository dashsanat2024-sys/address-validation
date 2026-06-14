# Deploy to Google Cloud Run

## Prerequisites

- Google Cloud project: `arthavi-492410` (or set `GCP_PROJECT_ID`)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated
- Billing enabled on the project

## Quick deploy

```bash
cd /Users/sanat/Address_Validation
cp gcp.env.example gcp.env    # optional overrides
chmod +x deploy.sh setup_repo.sh
./setup_repo.sh               # git init + push to Cloud Source Repositories
./deploy.sh                   # build image + deploy Cloud Run
```

## What gets deployed

| Component | GCP service |
|-----------|-------------|
| Flask API + UI | **Cloud Run** |
| Container image | **Container Registry** (`gcr.io`) |
| Source code | **Cloud Source Repositories** |

## Cloud vs local behaviour

Cloud Run does **not** include Ollama (local LLM). By default the cloud deployment sets:

```
CLOUD_DEFAULT_SKIP_LLM=1
ADDRESS_VALIDATOR=postcodes_io
```

This means cloud batch processing uses **postcode validation + rule-based mapping** (fast, no GPU).

### Enable LLM on cloud (optional)

Run Ollama on a **Compute Engine VM** and set in `gcp.env`:

```bash
OLLAMA_HOST=http://YOUR_VM_IP:11434
OLLAMA_MODEL=qwen3:8b
CLOUD_DEFAULT_SKIP_LLM=0
```

### Enable Ideal Postcodes on cloud

```bash
IDEAL_POSTCODES_API_KEY=your_key
ADDRESS_VALIDATOR=ideal_postcodes
```

## Environment variables (Cloud Run)

| Variable | Default (cloud) | Purpose |
|----------|-----------------|---------|
| `ADDRESS_VALIDATOR` | `postcodes_io` | Validation source |
| `CLOUD_DEFAULT_SKIP_LLM` | `1` | Skip Ollama when not available |
| `IDEAL_POSTCODES_API_KEY` | — | Street-level validation |
| `OLLAMA_HOST` | — | Remote Ollama URL |
| `PORT` | `8080` | Set by Cloud Run |

## Manual gcloud commands

```bash
export CLOUDSDK_PYTHON=python3
GCLOUD=$HOME/google-cloud-sdk/bin/gcloud

$GCLOUD run services describe arthavi-address-validation \
  --region europe-west2 --format='value(status.url)'

$GCLOUD run logs read arthavi-address-validation --region europe-west2
```

## GitHub (optional)

`gh` CLI was not available on this machine. To mirror to GitHub:

```bash
gh repo create arthavi-address-validation --public --source=. --push
```

Or create a repo on GitHub and:

```bash
git remote add origin git@github.com:YOUR_ORG/arthavi-address-validation.git
git push -u origin main
```
