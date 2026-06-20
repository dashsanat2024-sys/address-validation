"""JSONL export format for address fine-tuning."""

from __future__ import annotations

import json
from typing import Any

from ..schema import format_postal_code_city, format_uk_postcode, is_valid_uk_postcode_format

DEFAULT_INSTRUCTION = (
    "Validate the UK postcode and map the vendor address into the predefined "
    "client SAP address format. Output JSON only with llm_validation and all address fields."
)

TRAINING_OUTPUT_FIELDS = (
    "co",
    "street_2",
    "street_3",
    "street_house_number",
    "street_4",
    "street_5",
    "district",
    "other_city",
    "postal_code_city",
    "country",
    "time_zone",
    "transportation_zone",
    "reg_struct_grp",
    "undeliverable",
    "po_box_address",
    "po_box",
    "postal_code",
)


def build_llm_validation_block(
    *,
    postcode_format_valid: bool,
    postcode_exists: bool,
    postcode_plausible: bool = True,
    validation_notes: str = "",
) -> dict[str, Any]:
    return {
        "postcode_format_valid": postcode_format_valid,
        "postcode_exists": postcode_exists,
        "postcode_plausible": postcode_plausible,
        "validation_notes": validation_notes,
    }


def build_training_output(
    address_fields: dict[str, Any],
    *,
    postcode_format_valid: bool | None = None,
    postcode_exists: bool | None = None,
    postcode_plausible: bool | None = None,
    validation_notes: str = "",
) -> dict[str, Any]:
    """Merge client fields with llm_validation block for training labels."""
    out: dict[str, Any] = {}
    for key in TRAINING_OUTPUT_FIELDS:
        out[key] = str(address_fields.get(key) or "").strip()

    pc = out.get("postal_code", "")
    city = out.get("other_city", "")
    if pc and city and not out.get("postal_code_city"):
        out["postal_code_city"] = format_postal_code_city(pc, city)
    if not out.get("country"):
        out["country"] = "GB"
    if not out.get("time_zone"):
        out["time_zone"] = "GMTUK"

    fmt_ok = postcode_format_valid if postcode_format_valid is not None else is_valid_uk_postcode_format(pc)
    exists = postcode_exists if postcode_exists is not None else fmt_ok
    plausible = postcode_plausible if postcode_plausible is not None else exists

    out["llm_validation"] = build_llm_validation_block(
        postcode_format_valid=fmt_ok,
        postcode_exists=exists,
        postcode_plausible=plausible,
        validation_notes=validation_notes,
    )
    return out


def instruction_record(
    vendor_address: str,
    output: dict[str, Any],
    instruction: str = DEFAULT_INSTRUCTION,
) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "input": vendor_address,
        "output": json.dumps(output, ensure_ascii=False),
    }


def parse_training_output(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def normalize_field_for_compare(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if field == "postal_code":
        return format_uk_postcode(text) if text else ""
    if field in {"other_city", "district", "street_4", "street_3", "street_2"}:
        return text.upper()
    return text.upper()
