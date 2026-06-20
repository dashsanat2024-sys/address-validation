"""Optional Postcodes.io validation (same source as main app)."""

from __future__ import annotations

import os
import re
from typing import Any

import requests

POSTCODE_IN_TEXT_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)


def extract_postcode(text: str) -> str:
    match = POSTCODE_IN_TEXT_RE.search(text or "")
    return match.group(1).upper().replace("  ", " ") if match else ""


def validate_postcode(postcode: str) -> dict[str, Any]:
    """Lookup postcode via Postcodes.io; returns context for the LLM prompt."""
    base = os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io").rstrip("/")
    pc = (postcode or "").strip().upper()
    if not pc:
        return {"postcode": "", "found": False, "error": "no_postcode_in_input"}

    try:
        resp = requests.get(f"{base}/postcodes/{pc.replace(' ', '')}", timeout=10)
        if resp.status_code == 404:
            return {
                "postcode": pc,
                "found": False,
                "postcode_format_valid": True,
                "validated_address": None,
                "validation_notes": "Postcode format valid but not found in Postcodes.io",
            }
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        return {
            "postcode": result.get("postcode", pc),
            "found": True,
            "postcode_format_valid": True,
            "validated_address": {
                "post_town": result.get("post_town", ""),
                "admin_district": result.get("admin_district", ""),
                "admin_county": result.get("admin_county", ""),
                "region": result.get("region", ""),
                "country": result.get("country", ""),
                "parliamentary_constituency": result.get("parliamentary_constituency", ""),
            },
            "validation_notes": "Postcode verified via Postcodes.io",
        }
    except requests.RequestException as exc:
        return {
            "postcode": pc,
            "found": False,
            "error": str(exc),
            "validation_notes": "Postcodes.io lookup failed",
        }
