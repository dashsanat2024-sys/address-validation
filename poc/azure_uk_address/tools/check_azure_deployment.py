#!/usr/bin/env python3
"""Verify Azure deployment name in .env can accept chat requests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.azure_client import _normalize_azure_v1_base  # noqa: E402

key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()

if not key or not endpoint or not deployment:
    print("Missing AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, or AZURE_OPENAI_DEPLOYMENT in .env")
    sys.exit(1)

print(f"Endpoint:    {endpoint}")
print(f"Deployment:  {deployment}")
print("Testing chat completion...")

try:
    use_v1 = "/openai/v1" in endpoint or ".services.ai.azure.com" in endpoint
    if use_v1:
        client = OpenAI(api_key=key, base_url=_normalize_azure_v1_base(endpoint))
    else:
        ver = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        client = AzureOpenAI(
            azure_endpoint=endpoint.rstrip("/") + "/",
            api_key=key,
            api_version=ver,
        )

    r = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": "Reply OK"}],
        max_tokens=5,
    )
    print(f"SUCCESS — deployment '{deployment}' is active.")
    print(f"Response: {r.choices[0].message.content!r}")
    if r.usage:
        print(f"Tokens: {r.usage.total_tokens}")
except Exception as exc:
    err = str(exc)
    print(f"FAILED — {err[:300]}")
    if "DeploymentNotFound" in err:
        print(
            "\nThe deployment name in .env does not exist on this resource yet.\n"
            "In Azure AI Foundry → Deployments → Deploy model → copy the exact deployment name.\n"
            "Catalog model ids (e.g. Kimi-K2.6-2026-04-20) only work after you deploy them."
        )
    sys.exit(1)
