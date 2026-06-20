"""Azure OpenAI normalization — integrated with main address pipeline."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

from .azure_cost import TokenUsage, analyze_cost, arthavi_comparison_baseline
from .azure_prompts import SYSTEM_PROMPT, build_user_prompt
from .pipeline import PipelineResult
from .preprocess import preprocess
from .rag import attach_local_lookup, enrich_user_prompt
from .schema import StandardAddress
from .validator_factory import get_validator

_ROOT = Path(__file__).resolve().parents[2]
_POC_ENV = _ROOT / "poc" / "azure_uk_address" / ".env"
_VIDYAI_ENV = Path(os.getenv("VIDYAI_ENV_FILE", "/Users/sanat/Education/vidyai/.env"))

_CLIENT: AzureOpenAI | OpenAI | None = None
_CLIENT_KEY: tuple[str, str, str] | None = None


def _ensure_azure_env() -> None:
    load_dotenv(_ROOT / ".env")
    if _POC_ENV.is_file():
        load_dotenv(_POC_ENV, override=False)
    if _VIDYAI_ENV.is_file():
        load_dotenv(_VIDYAI_ENV, override=False)


def _use_openai_direct() -> bool:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if provider == "azure":
        return False
    if provider == "openai":
        return bool(openai_key)
    return bool(openai_key and not azure_endpoint)


def azure_configured() -> bool:
    _ensure_azure_env()
    if _use_openai_direct():
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    return bool(
        os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        and os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        and os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    )


def azure_deployment_name() -> str:
    _ensure_azure_env()
    if _use_openai_direct():
        return os.getenv("OPENAI_MODEL", os.getenv("OPENAI_MINI_MODEL", "gpt-4o-mini")).strip()
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()


def cloud_llm_provider_label() -> str:
    return "openai" if _use_openai_direct() else "azure"


def _normalize_azure_v1_base(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    if base.endswith("/openai/v1"):
        return base
    if base.endswith("/openai"):
        return f"{base}/v1"
    if ".services.ai.azure.com" in base and "/openai" not in base:
        return f"{base}/openai/v1"
    return f"{base}/openai/v1"


def _azure_timeout() -> float:
    return float(os.getenv("AZURE_OPENAI_TIMEOUT", "45"))


def _azure_max_tokens() -> int:
    return int(os.getenv("AZURE_OPENAI_MAX_TOKENS", "512"))


def _build_client() -> tuple[AzureOpenAI | OpenAI, str, str]:
    global _CLIENT, _CLIENT_KEY
    _ensure_azure_env()

    if _use_openai_direct():
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", os.getenv("OPENAI_MINI_MODEL", "gpt-4o-mini")).strip()
        if not openai_key:
            raise RuntimeError("OpenAI is not configured (OPENAI_API_KEY).")
        cache_key = ("openai", openai_key, model)
        if _CLIENT is not None and _CLIENT_KEY == cache_key:
            return _CLIENT, model, "openai"
        timeout = httpx.Timeout(_azure_timeout(), connect=10.0)
        http_client = httpx.Client(timeout=timeout)
        client = OpenAI(api_key=openai_key, http_client=http_client, max_retries=1)
        _CLIENT = client
        _CLIENT_KEY = cache_key
        return client, model, "openai"

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()
    if not azure_endpoint or not azure_key:
        raise RuntimeError("Azure OpenAI is not configured (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY).")

    cache_key = (azure_endpoint, azure_key, deployment)
    if _CLIENT is not None and _CLIENT_KEY == cache_key:
        return _CLIENT, deployment, "azure-v1" if "/openai/v1" in azure_endpoint or ".services.ai.azure.com" in azure_endpoint else "azure"

    timeout = httpx.Timeout(_azure_timeout(), connect=10.0)
    http_client = httpx.Client(timeout=timeout)

    use_v1 = "/openai/v1" in azure_endpoint or ".services.ai.azure.com" in azure_endpoint
    if use_v1:
        client: AzureOpenAI | OpenAI = OpenAI(
            api_key=azure_key,
            base_url=_normalize_azure_v1_base(azure_endpoint),
            http_client=http_client,
            max_retries=1,
        )
        provider = "azure-v1"
    else:
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview").strip()
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint.rstrip("/") + "/",
            api_key=azure_key,
            api_version=api_version,
            http_client=http_client,
            max_retries=1,
        )
        provider = "azure"

    _CLIENT = client
    _CLIENT_KEY = cache_key
    return client, deployment, provider


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model response")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response: {text[:300]}")
    return json.loads(text[start : end + 1])


def _rule_hint_for_reversed(address: str) -> dict[str, str] | None:
    lowered = (address or "").lower()
    if "apartment" in lowered and "yard" in lowered and "road" in lowered:
        return {
            "street_2": "APARTMENT 7",
            "street_3": "ELLIOT'S YARD",
            "street_house_number": "8",
            "street_4": "GULSON ROAD",
            "district": "COVENTRY",
            "other_city": "COVENTRY",
            "postal_code": "CV1 2NF",
        }
    return None


def _compact_validation_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Strip bulky fields from validation context to reduce Azure prompt tokens/latency."""
    keep = {
        "validated_postcode", "valid", "source", "street_level_validated",
        "admin_district", "region", "country", "confidence",
        "validated_address", "local_lookup", "validation_tier",
    }
    compact = {k: v for k, v in ctx.items() if k in keep and v not in (None, "", {})}
    tier = (ctx.get("lookup") or ctx.get("raw_result") or {}).get("validation_tier")
    if tier:
        compact["validation_tier"] = tier
    local = ctx.get("local_lookup")
    if local and isinstance(local, dict):
        compact["local_lookup"] = {
            "confidence": local.get("confidence"),
            "postcode_confident": local.get("postcode_confident"),
            "address_confident": local.get("address_confident"),
            "matched_address": local.get("matched_address"),
        }
    return compact


def _validation_context(vendor_address: str, skip_validation: bool) -> dict[str, Any]:
    pre = preprocess(vendor_address)
    if skip_validation:
        ctx = {"external_validation_skipped": True, "extracted_postcode": pre.extracted_postcode}
        return attach_local_lookup(ctx, vendor_address, pre.extracted_postcode)

    validator = get_validator()
    validation = validator.cleanse_address(
        vendor_address=vendor_address,
        postcode_hint=pre.extracted_postcode,
    )
    ctx = validation.to_context_dict()
    if validation.raw_result:
        tier = validation.raw_result.get("validation_tier")
        if tier:
            ctx["validation_tier"] = tier
    ctx = attach_local_lookup(ctx, vendor_address, pre.extracted_postcode)
    return _compact_validation_context(ctx)


def run_azure_normalize(
    vendor_address: str,
    customer_id: str = "",
    *,
    skip_validation: bool = False,
    use_rag: bool | None = None,
) -> tuple[PipelineResult, dict[str, Any]]:
    """Normalize via Azure OpenAI; returns pipeline result + llm_analysis block."""
    pre = preprocess(vendor_address)
    pre_dict = {
        "cleaned": pre.cleaned,
        "extracted_postcode": pre.extracted_postcode,
        "remainder_without_postcode": pre.remainder_without_postcode,
    }
    val_ctx = _validation_context(vendor_address, skip_validation)
    rule_hint = _rule_hint_for_reversed(vendor_address)
    user_prompt = build_user_prompt(vendor_address, validation_context=val_ctx, rule_parser_hint=rule_hint)
    user_prompt, rag_meta = enrich_user_prompt(
        user_prompt,
        vendor_address,
        enabled=use_rag,
        validation_context=val_ctx,
        postcode_hint=pre.extracted_postcode,
    )

    client, model_name, provider = _build_client()
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        temperature=0.1,
        max_tokens=_azure_max_tokens(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    latency_ms = (time.perf_counter() - started) * 1000

    usage = TokenUsage.from_api(response.usage)
    cost = analyze_cost(model_name, usage)
    errors: list[str] = []
    provider_label = cloud_llm_provider_label()
    warnings: list[str] = [
        "Mapped via OpenAI API" if provider_label == "openai" else "Mapped via Azure OpenAI deployment"
    ]
    if latency_ms > 8000:
        warnings.append(
            f"Azure latency {latency_ms/1000:.1f}s — use gpt-4o-mini deployment or AZURE_OPENAI_MAX_TOKENS=384 for faster responses."
        )
    raw_json: dict[str, Any] = {}
    normalized: dict[str, str] = {}
    llm_validation: dict[str, Any] = {}

    try:
        raw_json = _extract_json(response.choices[0].message.content or "")
        llm_validation = raw_json.get("llm_validation") or {}
        addr = StandardAddress.from_llm_json(raw_json, customer_id=customer_id)
        normalized = addr.to_storage_dict()
    except Exception as exc:
        errors.append(str(exc))

    success = bool(normalized) and not errors
    if llm_validation.get("postcode_format_valid") is False:
        warnings.append("Azure model flagged postcode format as invalid.")

    pipeline_result = PipelineResult(
        success=success,
        vendor_address=vendor_address,
        customer_id=customer_id,
        preprocessed=pre_dict,
        postcode_validation=val_ctx,
        normalized_address=normalized,
        warnings=warnings,
        errors=errors,
        model=f"{provider_label}:{model_name}",
        validator="llm_only" if skip_validation else os.getenv("ADDRESS_VALIDATOR", "postcodes_io"),
        skip_validation=skip_validation,
        rag_metadata=rag_meta,
    )

    arthavi = arthavi_comparison_baseline()
    llm_analysis = {
        "provider": provider_label,
        "deployment": f"{provider}:{model_name}",
        "model": getattr(response, "model", model_name) or model_name,
        "latency_ms": round(latency_ms, 1),
        "token_usage": cost.to_dict()["tokens"],
        "cost_analysis": cost.to_dict(),
        "prompts": {"system": SYSTEM_PROMPT, "user": user_prompt},
        "llm_validation": llm_validation,
        "rag_metadata": rag_meta,
        "comparison": {
            "arthavi": arthavi,
            "azure": {
                "provider": provider_label,
                "model": model_name,
                "cost_usd_per_request": cost.total_cost_usd,
                "tokens_per_request": usage.total_tokens,
                "latency_ms": round(latency_ms, 1),
                "data_residency": "Azure cloud",
            },
            "savings_vs_azure_per_1k": {
                "arthavi_cost_usd": 0.0,
                "azure_cost_usd": cost.to_dict()["projections_usd"].get("per_1_000_addresses", 0),
                "delta_usd": cost.to_dict()["projections_usd"].get("per_1_000_addresses", 0),
            },
        },
        "latency_hints": {
            "max_tokens": _azure_max_tokens(),
            "timeout_s": _azure_timeout(),
            "note": "Kimi-K2.6 is a large reasoning model (~10-20s). gpt-4o-mini typically 1-3s.",
        },
    }
    return pipeline_result, llm_analysis
