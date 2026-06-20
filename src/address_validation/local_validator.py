"""Tiered validation: local index first, Postcodes.io when not confident."""

from __future__ import annotations

import os
from typing import Any

from .local_address_store import LocalMatch, is_local_index_available, lookup, lookup_by_street
from .postcodes_io import PostcodesIOClient
from .validation_result import AddressValidation


def _local_to_validation(match: LocalMatch) -> AddressValidation:
    rec = match.record
    lines: dict[str, str] = {}
    if rec.unit:
        lines["line_1"] = rec.unit
    if rec.number or rec.street:
        line2 = f"{rec.number} {rec.street}".strip()
        if line2:
            lines["line_2"] = line2
    if rec.building:
        lines["line_3"] = rec.building
    if rec.city:
        lines["post_town"] = rec.city
    if rec.district:
        lines["county"] = rec.district
    lines["postcode"] = rec.postcode

    street_level = match.address_confident or match.match_reason.startswith("street_first")

    return AddressValidation(
        valid=True,
        source="local_index",
        postcode=rec.postcode,
        admin_district=rec.district or rec.city,
        region=rec.region,
        country="GB",
        street_level_validated=street_level,
        confidence=match.confidence,
        validated_lines=lines,
        raw_result={"local_match": match.to_context_dict()},
    )


class LocalFirstValidator:
    """Local compressed index → Postcodes.io fallback when confidence is low."""

    def __init__(self, base_url: str | None = None):
        self._postcodes = PostcodesIOClient(
            base_url=base_url or os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io")
        )
        self.min_confidence = float(os.getenv("LOCAL_ADDRESS_MIN_CONFIDENCE", "0.55"))

    @property
    def enabled(self) -> bool:
        return is_local_index_available()

    def cleanse_address(
        self,
        vendor_address: str,
        postcode_hint: str | None = None,
        post_town_hint: str | None = None,
    ) -> AddressValidation:
        local_match = lookup(vendor_address, postcode_hint)

        if local_match and local_match.address_confident:
            result = _local_to_validation(local_match)
            tier = "local_high_confidence"
            if local_match.match_reason.startswith("street_first"):
                tier = "street_first_resolved"
            result.raw_result = {
                **(result.raw_result or {}),
                "validation_tier": tier,
                "postcodes_io_skipped": True,
            }
            return result

        if local_match and local_match.postcode_confident and local_match.match_reason != "postcode_not_in_local_index":
            skip_remote = os.getenv("LOCAL_SKIP_POSTCODES_IO", "1").strip().lower() in {"1", "true", "yes"}
            if skip_remote and local_match.confidence >= float(os.getenv("LOCAL_POSTCODE_CONFIDENCE", "0.35")):
                result = _local_to_validation(local_match)
                result.street_level_validated = False
                result.raw_result = {
                    **(result.raw_result or {}),
                    "validation_tier": "local_postcode_confident",
                    "postcodes_io_skipped": True,
                }
                return result

        # Postcodes.io fallback — use resolved postcode from street-first weak match if any
        pc = postcode_hint or ""
        if local_match and local_match.record.postcode and local_match.match_reason.startswith("street_first"):
            pc = local_match.record.postcode
        if not pc and local_match:
            pc = local_match.record.postcode

        if not pc:
            # Last attempt: street-first without postcode hint
            street_only = lookup_by_street(vendor_address)
            if street_only and street_only.address_confident:
                result = _local_to_validation(street_only)
                result.raw_result = {
                    **(result.raw_result or {}),
                    "validation_tier": "street_first_resolved",
                    "postcodes_io_skipped": True,
                }
                return result
            return AddressValidation(
                valid=False,
                source="local_index",
                postcode="",
                error="No UK postcode found in vendor address",
                raw_result={"local_match": local_match.to_context_dict() if local_match else None},
            )

        remote = self._postcodes.validate_postcode(pc)
        if not remote.valid:
            # Postcodes.io rejected — try street-first to recover correct postcode
            street_recovery = lookup_by_street(vendor_address)
            if street_recovery and street_recovery.address_confident:
                recovered = _local_to_validation(street_recovery)
                recovered.raw_result = {
                    **(recovered.raw_result or {}),
                    "validation_tier": "street_first_after_postcodes_reject",
                    "postcodes_io_rejected": pc,
                    "postcodes_io_skipped": True,
                }
                return recovered

            return AddressValidation(
                valid=False,
                source="postcodes_io",
                postcode=pc,
                error=remote.error or "Invalid UK postcode",
                raw_result={
                    "validation_tier": "postcodes_io_rejected",
                    "local_match": local_match.to_context_dict() if local_match else None,
                    "postcodes_io": remote.raw_result,
                },
            )

        result = AddressValidation(
            valid=True,
            source="postcodes_io",
            postcode=remote.postcode or pc,
            admin_district=remote.admin_district,
            region=remote.region,
            country=remote.country,
            parliamentary_constituency=remote.parliamentary_constituency,
            latitude=remote.latitude,
            longitude=remote.longitude,
            street_level_validated=False,
            confidence=local_match.confidence if local_match else None,
            raw_result={
                "validation_tier": "postcodes_io_fallback",
                "local_match": local_match.to_context_dict() if local_match else None,
                "postcodes_io": remote.raw_result,
            },
        )

        if local_match and local_match.record.street:
            lines = result.validated_lines or {}
            rec = local_match.record
            if rec.unit:
                lines.setdefault("line_1", rec.unit)
            if rec.number or rec.street:
                lines.setdefault("line_2", f"{rec.number} {rec.street}".strip())
            if rec.building:
                lines.setdefault("line_3", rec.building)
            if rec.city:
                lines.setdefault("post_town", rec.city)
            lines["postcode"] = remote.postcode
            result.validated_lines = lines
            if local_match.confidence >= self.min_confidence * 0.85:
                result.street_level_validated = True
                result.confidence = local_match.confidence

        return result

    def validate_postcode(self, postcode: str) -> AddressValidation:
        local_match = lookup(postcode, postcode)
        if local_match and local_match.postcode_confident and local_match.match_reason != "postcode_not_in_local_index":
            return _local_to_validation(local_match)
        remote = self._postcodes.validate_postcode(postcode)
        return AddressValidation(
            valid=remote.valid,
            source="postcodes_io",
            postcode=remote.postcode,
            admin_district=remote.admin_district,
            region=remote.region,
            country=remote.country,
            parliamentary_constituency=remote.parliamentary_constituency,
            latitude=remote.latitude,
            longitude=remote.longitude,
            raw_result={"postcodes_io": remote.raw_result},
            error=remote.error,
        )
