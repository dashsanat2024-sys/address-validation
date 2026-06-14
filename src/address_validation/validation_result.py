"""Shared validation result used by all address validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AddressValidation:
    valid: bool
    source: str
    postcode: str
    admin_district: str | None = None
    region: str | None = None
    country: str | None = None
    parliamentary_constituency: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    street_level_validated: bool = False
    confidence: float | None = None
    uprn: str | None = None
    validated_lines: dict[str, str] = field(default_factory=dict)
    raw_result: dict[str, Any] | None = None
    error: str | None = None

    def to_context_dict(self) -> dict[str, Any]:
        ctx: dict[str, Any] = {
            "validated_postcode": self.postcode,
            "valid": self.valid,
            "source": self.source,
            "street_level_validated": self.street_level_validated,
            "admin_district": self.admin_district or "",
            "region": self.region or "",
            "country": self.country or "",
        }
        if self.confidence is not None:
            ctx["confidence"] = self.confidence
        if self.uprn:
            ctx["uprn"] = self.uprn
        if self.validated_lines:
            ctx["validated_address"] = self.validated_lines
        return ctx
