"""Ideal Postcodes client — street-level UK address validation (paid/trial)."""

from __future__ import annotations

import os
from typing import Any

import requests

from .schema import format_uk_postcode
from .validation_result import AddressValidation

DEFAULT_BASE = "https://api.ideal-postcodes.co.uk/v1"
DEFAULT_MIN_CONFIDENCE = 0.75


class IdealPostcodesClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE,
        min_confidence: float | None = None,
        timeout: int = 15,
    ):
        self.api_key = api_key or os.getenv("IDEAL_POSTCODES_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.min_confidence = min_confidence or float(
            os.getenv("IDEAL_POSTCODES_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE))
        )
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def cleanse_address(
        self,
        query: str,
        postcode_hint: str | None = None,
        post_town_hint: str | None = None,
    ) -> AddressValidation:
        if not self.configured:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=format_uk_postcode(postcode_hint or ""),
                error="IDEAL_POSTCODES_API_KEY not set",
            )

        body: dict[str, str] = {"query": query}
        if postcode_hint:
            body["postcode"] = format_uk_postcode(postcode_hint)
        if post_town_hint:
            body["post_town"] = post_town_hint

        try:
            resp = self.session.post(
                f"{self.base_url}/cleanse/addresses",
                params={"api_key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            data = resp.json()
        except requests.RequestException as exc:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=format_uk_postcode(postcode_hint or ""),
                error=str(exc),
            )

        if resp.status_code == 401:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode="",
                error="Ideal Postcodes API key unauthorized",
            )

        result = data.get("result") or {}
        match = result.get("match") or {}
        if not match:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=format_uk_postcode(postcode_hint or ""),
                error="No address match returned",
                raw_result=data,
            )

        confidence = float(match.get("confidence", 0))
        address = result.get("address") or {}
        postcode = format_uk_postcode(address.get("postcode") or postcode_hint or "")

        validated_lines = {
            k: str(address.get(k) or "")
            for k in ("line_1", "line_2", "line_3", "post_town", "county", "postcode")
            if address.get(k)
        }

        is_valid = confidence >= self.min_confidence and bool(postcode)
        return AddressValidation(
            valid=is_valid,
            source="ideal_postcodes",
            postcode=postcode,
            admin_district=address.get("district") or address.get("county"),
            region=address.get("post_town"),
            country=address.get("country") or "England",
            latitude=_to_float(address.get("latitude")),
            longitude=_to_float(address.get("longitude")),
            street_level_validated=True,
            confidence=confidence,
            uprn=str(address.get("uprn") or "") or None,
            validated_lines=validated_lines,
            raw_result=data,
            error=None if is_valid else f"Confidence {confidence:.2f} below threshold {self.min_confidence}",
        )

    def validate_postcode(self, postcode: str) -> AddressValidation:
        """Lookup postcode metadata via Ideal Postcodes."""
        normalized = format_uk_postcode(postcode)
        if not self.configured:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=normalized,
                error="IDEAL_POSTCODES_API_KEY not set",
            )

        compact = normalized.replace(" ", "")
        try:
            resp = self.session.get(
                f"{self.base_url}/postcodes/{compact}",
                params={"api_key": self.api_key},
                timeout=self.timeout,
            )
            data = resp.json()
        except requests.RequestException as exc:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=normalized,
                error=str(exc),
            )

        if resp.status_code != 200:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=normalized,
                error=data.get("message", "Postcode lookup failed"),
                raw_result=data,
            )

        result = data.get("result") or {}
        if not result:
            return AddressValidation(
                valid=False,
                source="ideal_postcodes",
                postcode=normalized,
                error="Invalid UK postcode",
                raw_result=data,
            )

        first = result[0] if isinstance(result, list) else result
        return AddressValidation(
            valid=True,
            source="ideal_postcodes",
            postcode=first.get("postcode", normalized),
            admin_district=first.get("district") or first.get("county"),
            region=first.get("post_town"),
            country=first.get("country"),
            latitude=_to_float(first.get("latitude")),
            longitude=_to_float(first.get("longitude")),
            street_level_validated=False,
            raw_result=data,
        )


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
