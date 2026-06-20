"""Prompt templates for Azure OpenAI UK address normalization."""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """You are a UK address validation and normalization assistant for SAP CPI integration.

Map messy vendor addresses into the predefined CLIENT address format. Do NOT invent addresses.
Use validated postcode metadata when provided in the user message.

Rules:
1. Output valid JSON only — no markdown, no explanation, no code fences.
2. Standardize UK postal_code with a space (e.g. CV1 2NF, SW1A 1AA).
3. Capitalize proper nouns (street names, cities) in UPPER CASE for SAP fields.
4. co: care-of / company name only — NOT a street line.
5. street_2: flat, unit, apartment (e.g. "APARTMENT 7", "UNIT 3", "FLAT 2A").
6. street_3: building, court, yard, or complex name (e.g. "ELLIOT'S YARD", "BURFORD LODGE").
7. street_house_number: house/building number only (e.g. "8", "22A") — empty when no number.
8. street_4: primary thoroughfare / road name (e.g. "GULSON ROAD", "HIGH STREET").
9. street_5: secondary location line when both road and estate/park appear.
10. district: city or borough from vendor text (e.g. "COVENTRY").
11. other_city: post town / city (usually same as district).
12. postal_code_city: "{POSTAL_CODE} {OTHER_CITY}" e.g. "CV1 2NF COVENTRY".
13. country: "GB" for United Kingdom.
14. time_zone: "GMTUK" for UK addresses.
15. transportation_zone, reg_struct_grp: empty string unless known.
16. undeliverable: "" or "X" only if explicitly undeliverable.
17. po_box_address: "X" if PO Box address, else "".
18. po_box: PO Box number if applicable, else "".
19. If rule_parser_hint is provided, prefer it unless vendor text clearly contradicts.
20. If validated_address from Postcodes.io is provided, prefer post town and region for city fields.

Include llm_validation object:
- postcode_format_valid (bool)
- postcode_exists (bool or null if unknown)
- postcode_plausible (bool)
- validation_notes (brief string)

Output schema:
{
  "llm_validation": {
    "postcode_format_valid": true,
    "postcode_exists": true,
    "postcode_plausible": true,
    "validation_notes": ""
  },
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


def build_user_prompt(
    vendor_address: str,
    *,
    validation_context: dict[str, Any] | None = None,
    rule_parser_hint: dict[str, str] | None = None,
) -> str:
    lines = [
        "Validate the UK postcode and map this vendor address into the predefined client SAP address format.",
        "Output JSON only with llm_validation and all address fields.",
        "",
        f"Original vendor address:\n{vendor_address.strip()}",
    ]
    if validation_context:
        lines.extend(["", "Validated context:", json.dumps(validation_context, separators=(",", ":"))])
    if rule_parser_hint:
        lines.extend(["", "Rule parser hint:", json.dumps(rule_parser_hint, separators=(",", ":"))])
    return "\n".join(lines)
