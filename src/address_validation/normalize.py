"""LLM-based address normalization via Ollama."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import ollama

from .llm_validation import extract_llm_validation_meta
from .rag import enrich_user_prompt
from . import ollama_client
from .schema import StandardAddress, format_postal_code_city, is_valid_uk_postcode_format

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
DEFAULT_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))


def _is_qwen3(model: str) -> bool:
    return "qwen3" in (model or "").lower()


def _ollama_chat_kwargs(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Build Ollama chat kwargs tuned for short JSON responses."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    }
    # Qwen3 "thinking" adds 1–3+ min per call on 16GB Mac — disable for address JSON.
    if _is_qwen3(model):
        kwargs["think"] = False
    return kwargs

SYSTEM_PROMPT = """You are a UK address normalization assistant.

Map messy vendor addresses into the predefined CLIENT address format (SAP-style).
You do NOT invent addresses. Use validated postcode metadata when provided.

Rules:
1. Output valid JSON only — no markdown, no explanation.
2. Standardize UK postal_code with a space (e.g. SW1A 1AA).
3. Capitalize proper nouns (street names, cities).
4. co: care-of / company / attention name (e.g. "COMEX 2000") — NOT a street line.
5. street_2: flat, unit, apartment (e.g. "UNIT 3", "Flat 14").
6. street_3: building, court, or complex name (e.g. "STADIUM BUSINESS COURT", "Burford Lodge").
7. street_house_number: house/building number only (e.g. 10, 22A) — empty for business parks with no number.
8. street_4: thoroughfare OR business park name (e.g. "MILLENNIUM WAY", "PRIDE PARK").
9. street_5: extra location line when both a road and park/estate appear (e.g. road in street_5 if park took street_4).
10. district: city or borough from vendor text (e.g. "DERBY") — prefer vendor city over county when explicit.
11. other_city: post town / city (usually same as district for business addresses).
12. postal_code: UK postcode.
13. postal_code_city: "{postal_code} {OTHER_CITY}" e.g. "DE24 8HP DERBY".
14. country: "GB" for United Kingdom.
15. time_zone: "GMTUK" for UK addresses.

Business address example:
Input: "COMEX 2000 UNIT 3 STADIUM BUSINESS COURT, MILLENNIUM WAY, PRIDE PARK, DERBY, DE24 8HP"
→ co="COMEX 2000", street_2="UNIT 3", street_3="STADIUM BUSINESS COURT", street_4="PRIDE PARK",
  street_5="MILLENNIUM WAY", district="DERBY", other_city="DERBY", postal_code="DE24 8HP"

20. transportation_zone, reg_struct_grp: empty string unless known.
21. undeliverable: "" or "X" only if explicitly undeliverable.
22. po_box_address: "X" if PO Box address, else "".
23. po_box: PO Box number if applicable, else "".
24. If validated_address is provided (Ideal Postcodes), prefer those values.
25. If rule_parser_hint is provided in context, prefer it unless vendor text clearly contradicts.

Output schema:
{
  "co": "",
  "street_2": "",
  "street_3": "",
  "street_house_number": "",
  "street_4": "",
  "street_5": "",
  "district": "",
  "other_city": "",
  "postal_code_city": "",
  "country": "GB",
  "time_zone": "GMTUK",
  "transportation_zone": "",
  "reg_struct_grp": "",
  "undeliverable": "",
  "po_box_address": "",
  "po_box": "",
  "postal_code": ""
}"""

LLM_ONLY_SYSTEM_PROMPT = """You are a UK address validation and normalization assistant.

External postcode APIs are DISABLED. Validate UK postcode FORMAT, assess plausibility vs city,
and map to the client SAP-style JSON schema. Output JSON only.

Include llm_validation: postcode_format_valid, postcode_plausible, validation_notes (brief).
UK postal_code must have a space before the last 3 chars (e.g. SW1A 1AA). country=GB, time_zone=GMTUK.

Schema keys: llm_validation, co, street_2, street_3, street_house_number, street_4, street_5,
district, other_city, postal_code, postal_code_city, country, time_zone, transportation_zone,
reg_struct_grp, undeliverable, po_box_address, po_box."""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in LLM response: {text[:200]}")

    return json.loads(text[start : end + 1])


def build_user_prompt(
    vendor_address: str,
    preprocessed_remainder: str,
    validation_context: dict[str, Any],
) -> str:
    if validation_context.get("external_validation_skipped"):
        return (
            "Validate postcode format and normalize this UK vendor address into the client format.\n"
            "No external validator was used — your llm_validation assessment is required.\n\n"
            f"Original vendor address:\n{vendor_address}\n\n"
            f"Address text without postcode:\n{preprocessed_remainder}\n\n"
            f"Preprocessing hints:\n{json.dumps(validation_context, indent=2)}\n"
        )

    return (
        "Convert this UK vendor address into the predefined client address format.\n\n"
        f"Original vendor address:\n{vendor_address}\n\n"
        f"Address text without postcode:\n{preprocessed_remainder}\n\n"
        f"Postcode validation (trusted source):\n"
        f"{json.dumps(validation_context, indent=2)}\n"
    )


def _apply_validation_defaults(address: StandardAddress, ctx: dict[str, Any]) -> StandardAddress:
    if ctx.get("external_validation_skipped"):
        if not address.country:
            address.country = "GB"
        if not address.time_zone:
            address.time_zone = "GMTUK"
        if address.postal_code and address.other_city:
            address.postal_code_city = format_postal_code_city(
                address.postal_code, address.other_city
            )
        return address

    validated_pc = ctx.get("validated_postcode", "")
    if validated_pc and ctx.get("valid"):
        address.postal_code = validated_pc

    if not address.district and ctx.get("admin_district"):
        address.district = str(ctx["admin_district"])

    if not address.other_city and ctx.get("region"):
        address.other_city = str(ctx["region"])

    hint = ctx.get("rule_parser_hint") or {}
    if hint.get("co"):
        for key in (
            "co", "street_2", "street_3", "street_house_number",
            "street_4", "street_5", "district", "other_city",
        ):
            if hint.get(key):
                setattr(address, key, hint[key])
    elif hint:
        for key in (
            "co", "street_2", "street_3", "street_house_number",
            "street_4", "street_5", "district", "other_city",
        ):
            if hint.get(key) and not getattr(address, key, ""):
                setattr(address, key, hint[key])

    if address.postal_code and address.other_city:
        address.postal_code_city = format_postal_code_city(
            address.postal_code, address.other_city
        )

    if not address.country:
        address.country = "GB"
    if not address.time_zone:
        address.time_zone = "GMTUK"

    return address


@dataclass
class NormalizeResult:
    address: StandardAddress
    llm_validation: dict[str, Any]
    rag_metadata: dict[str, Any] | None = None


class AddressNormalizer:
    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None):
        self.model = model
        if host:
            os.environ["OLLAMA_HOST"] = host
            ollama_client._client = None  # reset client for new host

    def normalize(
        self,
        vendor_address: str,
        preprocessed_remainder: str,
        validation_context: dict[str, Any],
        customer_id: str = "",
        use_rag: bool | None = None,
    ) -> NormalizeResult:
        llm_only = bool(validation_context.get("external_validation_skipped"))
        system_prompt = LLM_ONLY_SYSTEM_PROMPT if llm_only else SYSTEM_PROMPT
        user_content = build_user_prompt(
            vendor_address, preprocessed_remainder, validation_context
        )
        user_content, rag_meta = enrich_user_prompt(
            user_content,
            vendor_address,
            enabled=use_rag,
            validation_context=validation_context,
            postcode_hint=validation_context.get("validated_postcode"),
        )

        kwargs = _ollama_chat_kwargs(self.model, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ])
        response = ollama_client.chat(**kwargs)

        content = response["message"]["content"]
        parsed = _extract_json(content)
        llm_meta = extract_llm_validation_meta(parsed)
        address = StandardAddress.from_llm_json(parsed, customer_id=customer_id)
        address = _apply_validation_defaults(address, validation_context)

        if llm_only and address.postal_code:
            regex_ok = is_valid_uk_postcode_format(address.postal_code)
            if llm_meta.get("postcode_format_valid") is None:
                llm_meta["postcode_format_valid"] = regex_ok
            elif llm_meta.get("postcode_format_valid") and not regex_ok:
                llm_meta["validation_notes"] = (
                    (llm_meta.get("validation_notes") or "")
                    + " Postcode failed UK format regex check."
                ).strip()

        return NormalizeResult(address=address, llm_validation=llm_meta, rag_metadata=rag_meta)
