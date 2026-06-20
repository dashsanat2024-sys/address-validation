#!/usr/bin/env python3
"""POC: street-first local lookup + Azure gpt-4o-mini normalization."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "poc" / "azure_uk_address" / ".env", override=False)

os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
os.environ.setdefault("AZURE_OPENAI_MAX_TOKENS", "384")
os.environ.setdefault("LOCAL_STREET_FIRST", "1")

from address_validation.azure_normalize import (  # noqa: E402
    _build_client,
    azure_configured,
    run_azure_normalize,
)
from address_validation.local_address_store import clear_cache, lookup  # noqa: E402
from address_validation.local_validator import LocalFirstValidator  # noqa: E402

CASES = [
    {
        "label": "missing_postcode",
        "address": "8 Gulson Road Apartment 7 Elliot's Yard Coventry",
        "expect_pc": "CV1 2NF",
    },
    {
        "label": "wrong_postcode",
        "address": "8 Gulson Road Apartment 7 Elliot's Yard Coventry CV1 2AA",
        "expect_pc": "CV1 2NF",
    },
    {
        "label": "correct_postcode",
        "address": "Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF",
        "expect_pc": "CV1 2NF",
    },
]


def _probe_deployment(name: str) -> tuple[bool, str, float | None]:
    try:
        client, deployment, _ = _build_client()
        t0 = time.perf_counter()
        r = client.chat.completions.create(
            model=name,
            messages=[{"role": "user", "content": "Reply OK"}],
            max_tokens=3,
        )
        ms = (time.perf_counter() - t0) * 1000
        return True, (r.choices[0].message.content or "").strip(), ms
    except Exception as exc:
        return False, str(exc)[:200], None


def run_poc(deployment: str | None = None) -> dict:
    clear_cache()
    deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    os.environ["AZURE_OPENAI_DEPLOYMENT"] = deployment

    if not azure_configured():
        raise RuntimeError("Azure OpenAI not configured — set AZURE_OPENAI_* in .env")

    azure_ok, azure_probe_msg, azure_probe_ms = _probe_deployment(deployment)
    validator = LocalFirstValidator()
    results: list[dict] = []

    for case in CASES:
        row: dict = {"case": case["label"], "input": case["address"]}
        t0 = time.perf_counter()
        local = lookup(case["address"])
        row["local_lookup_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        row["local_match"] = local.to_context_dict() if local else None

        t1 = time.perf_counter()
        validation = validator.cleanse_address(case["address"])
        row["validation_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        row["validation"] = {
            "valid": validation.valid,
            "postcode": validation.postcode,
            "tier": (validation.raw_result or {}).get("validation_tier"),
            "street_level": validation.street_level_validated,
        }
        row["expect_pc"] = case["expect_pc"]
        row["validation_postcode_ok"] = validation.postcode == case["expect_pc"]

        if azure_ok:
            t2 = time.perf_counter()
            pipeline_result, llm_analysis = run_azure_normalize(
                case["address"],
                use_rag=True,
                skip_validation=False,
            )
            row["azure_ms"] = round((time.perf_counter() - t2) * 1000, 1)
            row["normalized_postcode"] = pipeline_result.normalized_address.get("postal_code")
            row["llm_validation"] = llm_analysis.get("llm_validation")
            row["latency_ms"] = llm_analysis.get("latency_ms")
            row["tokens"] = llm_analysis.get("token_usage")
            row["success"] = pipeline_result.success
            row["postcode_ok"] = row["normalized_postcode"] == case["expect_pc"]
        else:
            row["azure_skipped"] = True
            row["azure_error"] = azure_probe_msg
            row["postcode_ok"] = row["validation_postcode_ok"]

        results.append(row)

    out_dir = ROOT / "poc" / "azure_uk_address" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"street_first_gpt4o_mini_{stamp}.json"
    summary = {
        "deployment_requested": deployment,
        "deployment_available": azure_ok,
        "deployment_probe_ms": azure_probe_ms,
        "deployment_probe_detail": azure_probe_msg if not azure_ok else "ok",
        "local_street_first": os.getenv("LOCAL_STREET_FIRST"),
        "cases": results,
        "all_postcodes_ok": all(r["postcode_ok"] for r in results),
        "note": (
            "Deploy gpt-4o-mini in Azure AI Foundry → Deployments, then re-run with "
            "AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini"
            if not azure_ok
            else None
        ),
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved → {out_path}")
    return summary


if __name__ == "__main__":
    dep = sys.argv[1] if len(sys.argv) > 1 else None
    run_poc(dep)
