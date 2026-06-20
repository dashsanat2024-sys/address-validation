"""Client address schema for database / SAP storage."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, field_validator

UK_POSTCODE_RE = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})$",
    re.IGNORECASE,
)

PO_BOX_RE = re.compile(r"\bP\.?\s*O\.?\s*Box\b", re.IGNORECASE)

# JSON keys → display labels (client predefined format)
CLIENT_FIELD_LABELS: dict[str, str] = {
    "customer_id": "Customer ID",
    "co": "c/o",
    "street_2": "Street 2",
    "street_3": "Street 3",
    "street_house_number": "Street/House Number",
    "street_4": "Street 4",
    "street_5": "Street 5",
    "district": "District",
    "other_city": "Other City",
    "postal_code_city": "Postal Code/City",
    "country": "Country",
    "time_zone": "Time Zone",
    "transportation_zone": "Transportation Zone",
    "reg_struct_grp": "Reg. Struct. Grp.",
    "undeliverable": "Undeliverable",
    "po_box_address": "PO Box Address",
    "po_box": "PO Box",
    "postal_code": "Postal Code",
}


def format_uk_postcode(raw: str) -> str:
    """Normalize postcode to 'OUTCODE INCODE' (e.g. SW1A 1AA)."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip()).upper()
    if len(cleaned) < 5:
        return (raw or "").strip().upper()
    outcode = cleaned[:-3]
    incode = cleaned[-3:]
    return f"{outcode} {incode}"


def is_valid_uk_postcode_format(postcode: str) -> bool:
    """Check UK postcode structure (format only — not whether it exists)."""
    if not postcode:
        return False
    return bool(UK_POSTCODE_RE.match(format_uk_postcode(postcode)))


def format_postal_code_city(postal_code: str, city: str) -> str:
    pc = format_uk_postcode(postal_code)
    city_part = (city or "").strip()
    if pc and city_part:
        return f"{pc} {city_part.upper()}"
    return pc or city_part.upper()


class StandardAddress(BaseModel):
    customer_id: str = ""
    co: str = ""
    street_2: str = ""
    street_3: str = ""
    street_house_number: str = ""
    street_4: str = ""
    street_5: str = ""
    district: str = ""
    other_city: str = ""
    postal_code_city: str = ""
    country: str = "GB"
    time_zone: str = "GMTUK"
    transportation_zone: str = ""
    reg_struct_grp: str = ""
    undeliverable: str = ""
    po_box_address: str = ""
    po_box: str = ""
    postal_code: str = ""

    @field_validator("postal_code")
    @classmethod
    def normalize_postal_code(cls, value: str) -> str:
        if not value:
            return ""
        return format_uk_postcode(value)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        v = (value or "GB").strip().upper()
        if v in {"UK", "GBR", "UNITED KINGDOM", "GREAT BRITAIN"}:
            return "GB"
        return v or "GB"

    @field_validator("undeliverable", "po_box_address")
    @classmethod
    def normalize_flag(cls, value: str) -> str:
        v = (value or "").strip().upper()
        return "X" if v in {"X", "TRUE", "1", "YES", "Y"} else ""

    def model_post_init(self, __context: Any) -> None:
        if self.postal_code and self.other_city and not self.postal_code_city:
            self.postal_code_city = format_postal_code_city(self.postal_code, self.other_city)

    def is_complete(self) -> bool:
        has_street = bool(
            self.street_house_number.strip()
            or self.street_4.strip()
            or self.street_2.strip()
            or self.po_box.strip()
        )
        return bool(has_street and self.other_city.strip() and self.postal_code.strip())

    def to_storage_dict(self) -> dict[str, str]:
        data = self.model_dump()
        if not data.get("postal_code_city") and data.get("postal_code") and data.get("other_city"):
            data["postal_code_city"] = format_postal_code_city(
                data["postal_code"], data["other_city"]
            )
        return data

    @classmethod
    def from_llm_json(cls, payload: str | dict[str, Any], customer_id: str = "") -> "StandardAddress":
        data = payload if isinstance(payload, dict) else json.loads(payload)
        data["customer_id"] = customer_id or data.get("customer_id", "")
        # Accept legacy field names from older training data
        data = _migrate_legacy_fields(data)
        return cls.model_validate(data)

    @classmethod
    def from_vendor_text(cls, text: str, customer_id: str = "") -> "StandardAddress":
        """Light rule-based mapping for fallback paths."""
        is_po_box = bool(PO_BOX_RE.search(text or ""))
        parts = [p.strip() for p in (text or "").split(",") if p.strip()]
        addr = cls(customer_id=customer_id, country="GB", time_zone="GMTUK")
        if is_po_box:
            addr.po_box_address = "X"
            addr.po_box = parts[0] if parts else text.strip()
            return addr
        if not parts:
            return addr

        from .address_parse import parse_business_comma_address, parse_space_separated

        business = parse_business_comma_address(text, customer_id=customer_id)
        if business is not None:
            return business

        if len(parts) == 1:
            space_parsed = parse_space_separated(parts[0], customer_id=customer_id)
            if space_parsed is not None:
                return space_parsed
            addr.street_house_number = _extract_house_number(parts[0])
            addr.street_4 = _extract_street_name(parts[0])
            return addr

        addr.other_city = parts[-1]
        address_lines = parts[:-1]

        # Prefer the last line with a house number as the thoroughfare (e.g. "5 Montpellier Parade").
        street_idx = None
        for i in range(len(address_lines) - 1, -1, -1):
            if _extract_house_number(address_lines[i]):
                street_idx = i
                break

        supplement: list[str]
        if street_idx is not None:
            line = address_lines[street_idx]
            addr.street_house_number = _extract_house_number(line)
            addr.street_4 = _extract_street_name(line)
            supplement = [address_lines[i] for i in range(len(address_lines)) if i != street_idx]
        else:
            supplement = list(address_lines)
            if supplement:
                last = supplement.pop()
                addr.street_house_number = _extract_house_number(last)
                addr.street_4 = _extract_street_name(last)

        if len(supplement) >= 1:
            addr.street_2 = supplement[0]
        if len(supplement) >= 2:
            addr.street_3 = supplement[1]
        if len(supplement) >= 3:
            addr.street_5 = supplement[2]
        return addr


def _extract_house_number(part: str) -> str:
    match = re.match(r"^(\d+[A-Za-z]?)\b", (part or "").strip())
    return match.group(1) if match else ""


def _extract_street_name(part: str) -> str:
    part = (part or "").strip()
    match = re.match(r"^\d+[A-Za-z]?\s+(.+)$", part)
    return match.group(1).title() if match else part.title()


def _migrate_legacy_fields(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("address_line_1") and not data.get("street_2"):
        data["street_2"] = data["address_line_1"]
    if data.get("address_line_2") and not data.get("street_4"):
        data["street_house_number"] = _extract_house_number(data["address_line_2"])
        data["street_4"] = _extract_street_name(data["address_line_2"])
    if data.get("city") and not data.get("other_city"):
        data["other_city"] = data["city"]
    if data.get("county") and not data.get("district"):
        data["district"] = data["county"]
    if data.get("postcode") and not data.get("postal_code"):
        data["postal_code"] = data["postcode"]
    # Some LLM outputs incorrectly emit postal_code_city as an object:
    # {"postal_code": "...", "city": "..."}.
    if isinstance(data.get("postal_code_city"), dict):
        pcc = data["postal_code_city"]
        pc = pcc.get("postal_code") or data.get("postal_code") or data.get("postcode") or ""
        city = pcc.get("city") or data.get("other_city") or data.get("city") or ""
        data["postal_code_city"] = format_postal_code_city(str(pc), str(city))
        if pc and not data.get("postal_code"):
            data["postal_code"] = str(pc)
        if city and not data.get("other_city"):
            data["other_city"] = str(city)
    return data
