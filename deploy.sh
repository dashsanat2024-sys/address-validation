#!/usr/bin/env bash
# Deploy Arthavi Address Validation to Google Cloud Run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
if [[ ! -x "$GCLOUD" ]]; then
  GCLOUD="$(command -v gcloud || true)"
fi
if [[ -z "$GCLOUD" ]]; then
  echo "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# Load optional local overrides
if [[ -f gcp.env ]]; then
  # shellcheck disable=SC1091
  source gcp.env
fi

PROJECT_ID="${GCP_PROJECT_ID:-$("$GCLOUD" config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-europe-west2}"
SERVICE="${GCP_SERVICE_NAME:-arthavi-address-validation}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Service:  $SERVICE"

"$GCLOUD" config set project "$PROJECT_ID"

echo "Enabling required APIs..."
"$GCLOUD" services enable run.googleapis.com cloudbuild.googleapis.com containerregistry.googleapis.com --quiet

echo "Building container..."
"$GCLOUD" builds submit --tag "$IMAGE" .

ENV_VARS="ADDRESS_VALIDATOR=${ADDRESS_VALIDATOR:-postcodes_io},FLASK_DEBUG=0"
if [[ -n "${OLLAMA_HOST:-}" ]]; then
  ENV_VARS="${ENV_VARS},OLLAMA_HOST=${OLLAMA_HOST},OLLAMA_MODEL=${OLLAMA_MODEL:-qwen3:8b},CLOUD_DEFAULT_SKIP_LLM=0"
else
  ENV_VARS="${ENV_VARS},CLOUD_DEFAULT_SKIP_LLM=${CLOUD_DEFAULT_SKIP_LLM:-1}"
fi
if [[ -n "${IDEAL_POSTCODES_API_KEY:-}" ]]; then
  ENV_VARS="${ENV_VARS},IDEAL_POSTCODES_API_KEY=${IDEAL_POSTCODES_API_KEY}"
fi

echo "Deploying to Cloud Run..."
"$GCLOUD" run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 900 \
  --max-instances 5 \
  --set-env-vars "$ENV_VARS"

URL="$("$GCLOUD" run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo ""
echo "Deployed successfully!"
echo "URL: $URL"
echo "Health: ${URL}/health"
