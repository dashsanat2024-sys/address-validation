#!/usr/bin/env bash
# Initialise git repo and push to Google Cloud Source Repositories
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
PROJECT_ID="${GCP_PROJECT_ID:-$("$GCLOUD" config get-value project 2>/dev/null)}"
REPO_NAME="${GCP_REPO_NAME:-arthavi-address-validation}"

if [[ ! -d .git ]]; then
  git init -b main
fi

git add -A
git status

if git diff --cached --quiet; then
  echo "Nothing to commit."
else
  git commit -m "$(cat <<'EOF'
Initial commit: Arthavi UK Address Validation platform.

Flask API, batch CSV processing, Postcodes.io/Ideal Postcodes validators,
local Ollama normalization, Arthavi-branded review UI, and Cloud Run deploy.
EOF
)"
fi

echo "Creating Cloud Source Repository (if needed)..."
"$GCLOUD" source repos create "$REPO_NAME" --project="$PROJECT_ID" 2>/dev/null || true

if ! git remote get-url google &>/dev/null; then
  git remote add google "https://source.developers.google.com/p/${PROJECT_ID}/r/${REPO_NAME}"
fi

echo "Pushing to Google Cloud Source Repositories..."
git push google main

echo ""
echo "Repository: https://source.cloud.google.com/${PROJECT_ID}/repos/${REPO_NAME}"
