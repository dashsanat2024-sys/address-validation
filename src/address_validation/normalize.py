"""LLM-based address normalization via local Ollama."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import ollama

from .schema import StandardAddress, format_postal_code_city

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

SYSTEM_PROMPT = """You are a UK address normalization assistant.

Map messy vendor addresses into the predefined CLIENT address format (SAP-style).
You do NOT invent addresses. Use validated postcode metadata when provided.

Rules:
1. Output valid JSON only — no markdown, no explanation.
2. Standardize UK postal_code with a space (e.g. SW1A 1AA).
3. Capitalize proper nouns (street names, cities).
4. co: care-of / attention name only (empty if none).
5. street_2: flat, unit, apartment, building name.
6. street_3: organization or supplementary line.
7. street_house_number: house/building number only (e.g. 10, 22A).
8. street_4: street/thoroughfare name (e.g. High Street).
9. street_5: extra location (industrial estate, park name, etc.).
10. district: borough, admin district, or county from validation when available.
11. other_city: post town / city.
12. postal_code: UK postcode.
13. postal_code_city: "{postal_code} {OTHER_CITY}" e.g. "SW1A 1AA LONDON".
14. country: "GB" for United Kingdom.
15. time_zone: "GMTUK" for UK addresses.
16. transportation_zone, reg_struct_grp: empty string unless known.
17. undeliverable: "" or "X" only if explicitly undeliverable.
18. po_box_address: "X" if PO Box address, else "".
19. po_box: PO Box number if applicable, else "".
20. If validated_address is provided (Ideal Postcodes), prefer those values.

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
    return (
        "Convert this UK vendor address into the predefined client address format.\n\n"
        f"Original vendor address:\n{vendor_address}\n\n"
        f"Address text without postcode:\n{preprocessed_remainder}\n\n"
        f"Postcode validation (trusted source):\n"
        f"{json.dumps(validation_context, indent=2)}\n"
    )


def _apply_validation_defaults(address: StandardAddress, ctx: dict[str, Any]) -> StandardAddress:
    validated_pc = ctx.get("validated_postcode", "")
    if validated_pc and ctx.get("valid"):
        address.postal_code = validated_pc

    if not address.district and ctx.get("admin_district"):
        address.district = str(ctx["admin_district"])

    if not address.other_city and ctx.get("region"):
        address.other_city = str(ctx["region"])

    if address.postal_code and address.other_city:
        address.postal_code_city = format_postal_code_city(
            address.postal_code, address.other_city
        )

    if not address.country:
        address.country = "GB"
    if not address.time_zone:
        address.time_zone = "GMTUK"

    return address


class AddressNormalizer:
    def __init__(self, model: str = DEFAULT_MODEL, host: str | None = None):
        self.model = model
        if host:
            os.environ["OLLAMA_HOST"] = host

    def normalize(
        self,
        vendor_address: str,
        preprocessed_remainder: str,
        validation_context: dict[str, Any],
        customer_id: str = "",
    ) -> StandardAddress:
        user_content = build_user_prompt(
            vendor_address, preprocessed_remainder, validation_context
        )

        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": 0.1},
        )

        content = response["message"]["content"]
        parsed = _extract_json(content)
        address = StandardAddress.from_llm_json(parsed, customer_id=customer_id)
        return _apply_validation_defaults(address, validation_context)
