"""UK address schema for Azure AI POC (aligned with main app StandardAddress)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, field_validator

UK_POSTCODE_RE = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})$",
    re.IGNORECASE,
)


def format_uk_postcode(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip()).upper()
    if len(cleaned) < 5:
        return (raw or "").strip().upper()
    return f"{cleaned[:-3]} {cleaned[-3:]}"


def is_valid_uk_postcode_format(postcode: str) -> bool:
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
        return format_uk_postcode(value) if value else ""

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        v = (value or "GB").strip().upper()
        if v in {"UK", "GBR", "UNITED KINGDOM", "GREAT BRITAIN", "ENGLAND"}:
            return "GB"
        return v or "GB"

    @field_validator("time_zone")
    @classmethod
    def normalize_time_zone(cls, value: str) -> str:
        v = (value or "GMTUK").strip().upper()
        return "GMTUK" if v in {"GMTUK", "GMT UK", "GMT"} else v

    def model_post_init(self, __context: Any) -> None:
        if self.postal_code and self.other_city and not self.postal_code_city:
            self.postal_code_city = format_postal_code_city(self.postal_code, self.other_city)

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
        data = migrate_legacy_fields(data)
        llm_validation = data.pop("llm_validation", None)
        addr = cls.model_validate(data)
        return addr


def migrate_legacy_fields(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("postal_code_city"), dict):
        pcc = data["postal_code_city"]
        pc = pcc.get("postal_code") or data.get("postal_code") or ""
        city = pcc.get("city") or data.get("other_city") or ""
        data["postal_code_city"] = format_postal_code_city(str(pc), str(city))
        if pc and not data.get("postal_code"):
            data["postal_code"] = str(pc)
        if city and not data.get("other_city"):
            data["other_city"] = str(city)
    if data.get("postcode") and not data.get("postal_code"):
        data["postal_code"] = data["postcode"]
    if data.get("city") and not data.get("other_city"):
        data["other_city"] = data["city"]
    return data
