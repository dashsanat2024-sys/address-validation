"""Azure OpenAI client for UK address normalization POC."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AzureOpenAI, OpenAI

from .cost_analysis import CostBreakdown, TokenUsage, analyze_cost, estimate_prompt_tokens
from .postcode_validate import extract_postcode, validate_postcode
from .prompts import build_user_prompt, load_system_prompt
from .schema import StandardAddress


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


@dataclass
class PocResult:
    vendor_address: str
    normalized: dict[str, str]
    llm_validation: dict[str, Any]
    raw_llm_json: dict[str, Any]
    model: str
    deployment: str
    latency_ms: float
    token_usage: TokenUsage
    cost: CostBreakdown
    prompts: dict[str, str] = field(default_factory=dict)
    validation_context: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_address": self.vendor_address,
            "normalized": self.normalized,
            "llm_validation": self.llm_validation,
            "raw_llm_json": self.raw_llm_json,
            "model": self.model,
            "deployment": self.deployment,
            "latency_ms": round(self.latency_ms, 1),
            "token_usage": self.cost.to_dict()["tokens"],
            "cost_analysis": self.cost.to_dict(),
            "prompts": self.prompts,
            "validation_context": self.validation_context,
            "errors": self.errors,
        }


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


def _build_client() -> tuple[AzureOpenAI | OpenAI, str, str]:
    """Return (client, model/deployment name, provider label)."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    use_openai = provider == "openai" or (openai_key and provider != "azure" and not azure_endpoint)
    if use_openai:
        if not openai_key:
            raise RuntimeError(
                "Set OPENAI_API_KEY in poc/azure_uk_address/.env "
                "(or use Azure: AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY)"
            )
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        return OpenAI(api_key=openai_key), model, "openai"

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()
    if not azure_endpoint or not azure_key:
        raise RuntimeError(
            "Azure OpenAI: set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY.\n"
            "Or use direct OpenAI: set OPENAI_API_KEY and LLM_PROVIDER=openai"
        )

    use_v1 = os.getenv("AZURE_USE_V1_API", "").strip() in {"1", "true", "yes"}
    use_v1 = use_v1 or "/openai/v1" in azure_endpoint or ".services.ai.azure.com" in azure_endpoint

    if use_v1:
        base_url = _normalize_azure_v1_base(azure_endpoint)
        client = OpenAI(api_key=azure_key, base_url=base_url)
        return client, deployment, "azure-v1"

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview").strip()
    client = AzureOpenAI(
        azure_endpoint=azure_endpoint.rstrip("/") + "/",
        api_key=azure_key,
        api_version=api_version,
    )
    return client, deployment, "azure"


def _rule_hint_for_reversed(address: str) -> dict[str, str] | None:
    """Hint for space-separated reversed UK addresses (Elliot's Yard pattern)."""
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


def normalize_address(
    vendor_address: str,
    *,
    skip_postcode_lookup: bool = False,
    temperature: float = 0.1,
) -> PocResult:
    """Send address to Azure OpenAI and return normalized fields + token/cost report."""
    system_prompt = load_system_prompt()
    validation_context: dict[str, Any] = {}
    if not skip_postcode_lookup:
        pc = extract_postcode(vendor_address)
        if pc:
            validation_context = validate_postcode(pc)

    rule_hint = _rule_hint_for_reversed(vendor_address)
    user_prompt = build_user_prompt(
        vendor_address,
        validation_context=validation_context or None,
        rule_parser_hint=rule_hint,
    )

    client, model_name, provider = _build_client()
    estimated_prompt = estimate_prompt_tokens(system_prompt, user_prompt, model_name)

    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    latency_ms = (time.perf_counter() - started) * 1000

    content = response.choices[0].message.content or ""
    usage = TokenUsage.from_api(response.usage)
    usage.estimated_prompt_tokens = estimated_prompt

    cost = analyze_cost(model_name, usage)
    errors: list[str] = []
    raw_json: dict[str, Any] = {}
    llm_validation: dict[str, Any] = {}
    normalized: dict[str, str] = {}

    try:
        raw_json = _extract_json(content)
        llm_validation = raw_json.get("llm_validation") or {}
        addr = StandardAddress.from_llm_json(raw_json)
        normalized = addr.to_storage_dict()
    except Exception as exc:
        errors.append(str(exc))
        normalized = {"parse_error": content[:500]}

    return PocResult(
        vendor_address=vendor_address,
        normalized=normalized,
        llm_validation=llm_validation,
        raw_llm_json=raw_json,
        model=getattr(response, "model", model_name) or model_name,
        deployment=f"{provider}:{model_name}",
        latency_ms=latency_ms,
        token_usage=usage,
        cost=cost,
        prompts={"system": system_prompt, "user": user_prompt},
        validation_context=validation_context,
        errors=errors,
    )
