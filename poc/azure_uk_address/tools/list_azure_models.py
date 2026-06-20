#!/usr/bin/env python3
"""List Azure models available on your resource (catalog). Deploy one in the portal before running POC."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
if not key or not endpoint:
    print("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env", file=sys.stderr)
    sys.exit(1)

base = endpoint if "/openai/v1" in endpoint else f"{endpoint}/openai/v1"
url = f"{base.rstrip('/')}/models"
r = requests.get(url, headers={"api-key": key}, timeout=30)
r.raise_for_status()

chat_models = [
    m["id"]
    for m in r.json().get("data", [])
    if m.get("capabilities", {}).get("chat_completion")
]
print(f"Chat-capable models in catalog ({len(chat_models)}):")
for name in sorted(chat_models):
    if any(x in name.lower() for x in ("gpt-4o", "gpt-4.1", "kimi", "qwen", "llama")):
        print(f"  {name}")

print(
    "\nNote: catalog models ≠ deployments. Create a deployment in Azure AI Studio,\n"
    "then set AZURE_OPENAI_DEPLOYMENT to the deployment name you chose."
)
