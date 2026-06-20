#!/usr/bin/env bash
# Provision a GCE VM running Ollama for production (Cloud Run calls this host).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
PROJECT_ID="${GCP_PROJECT_ID:-$("$GCLOUD" config get-value project 2>/dev/null)}"
ZONE="${GCP_ZONE:-europe-west2-a}"
VM_NAME="${OLLAMA_VM_NAME:-arthavi-ollama}"
MACHINE_TYPE="${OLLAMA_MACHINE_TYPE:-e2-standard-4}"

STARTUP_SCRIPT='#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
mkdir -p /etc/systemd/system/ollama.service.d
cat >/etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:11434/api/tags && break
  sleep 5
done
ollama pull qwen3:8b
'

echo "Project: $PROJECT_ID  Zone: $ZONE  VM: $VM_NAME"

"$GCLOUD" config set project "$PROJECT_ID"
"$GCLOUD" services enable compute.googleapis.com --quiet

if ! "$GCLOUD" compute instances describe "$VM_NAME" --zone="$ZONE" &>/dev/null; then
  echo "Creating Ollama VM (this may take a few minutes)..."
  "$GCLOUD" compute instances create "$VM_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --boot-disk-size=50GB \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=ollama-server \
    --metadata=startup-script="$STARTUP_SCRIPT"
else
  echo "VM $VM_NAME already exists."
fi

if ! "$GCLOUD" compute firewall-rules describe allow-ollama-arthavi &>/dev/null; then
  echo "Opening firewall tcp:11434 for Ollama (demo — tighten for production)..."
  "$GCLOUD" compute firewall-rules create allow-ollama-arthavi \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:11434 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=ollama-server
fi

EXTERNAL_IP="$("$GCLOUD" compute instances describe "$VM_NAME" --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"

OLLAMA_URL="http://${EXTERNAL_IP}:11434"
echo ""
echo "Ollama URL: $OLLAMA_URL"
echo "Waiting for Ollama API (model pull may take 5–15 min on first boot)..."

for i in $(seq 1 60); do
  if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo "Ollama is responding."
    break
  fi
  echo "  attempt $i/60..."
  sleep 15
done

# Write gcp.env for deploy.sh
cat > gcp.env <<EOF
GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=europe-west2
GCP_SERVICE_NAME=arthavi-address-validation

ADDRESS_VALIDATOR=postcodes_io
OLLAMA_HOST=${OLLAMA_URL}
OLLAMA_MODEL=qwen3:8b
CLOUD_DEFAULT_SKIP_LLM=0
EOF

echo ""
echo "Wrote gcp.env with OLLAMA_HOST=${OLLAMA_URL}"
echo "Run ./deploy.sh to update Cloud Run."
