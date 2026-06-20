"""Helpers for LLM-only validation mode (no Postcodes.io / Ideal Postcodes)."""

from __future__ import annotations

from typing import Any

from .preprocess import PreprocessedAddress
from .schema import is_valid_uk_postcode_format


def build_llm_only_context(pre: PreprocessedAddress) -> dict[str, Any]:
    """Context passed to Ollama when external validators are bypassed."""
    hint = pre.extracted_postcode or ""
    return {
        "external_validation_skipped": True,
        "source": "llm_only",
        "valid": None,
        "street_level_validated": False,
        "extracted_postcode_hint": hint,
        "postcode_format_ok": is_valid_uk_postcode_format(hint) if hint else False,
        "remainder_without_postcode": pre.remainder_without_postcode,
        "admin_district": "",
        "region": "",
        "country": "GB",
    }


def extract_llm_validation_meta(parsed: dict[str, Any]) -> dict[str, Any]:
    """Pull validation metadata from LLM JSON before schema mapping."""
    nested = parsed.pop("llm_validation", None)
    meta: dict[str, Any] = {}
    if isinstance(nested, dict):
        meta.update(nested)

    for key in ("postcode_format_valid", "postcode_plausible", "validation_notes"):
        if key in parsed:
            meta[key] = parsed.pop(key)

    return meta


def merge_llm_validation_into_context(
    ctx: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    out = dict(ctx)
    out["llm_validation"] = meta
    if meta.get("postcode_format_valid") is not None:
        out["postcode_format_ok"] = bool(meta["postcode_format_valid"])
    if meta.get("postcode_plausible") is not None:
        out["postcode_plausible"] = bool(meta["postcode_plausible"])
    if meta.get("validation_notes"):
        out["validation_notes"] = str(meta["validation_notes"])
    return out
