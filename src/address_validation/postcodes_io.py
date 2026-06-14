"""Postcodes.io client — free UK postcode validation and metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from .schema import format_uk_postcode

DEFAULT_BASE = os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io")


@dataclass
class PostcodeValidation:
    valid: bool
    postcode: str
    admin_district: str | None = None
    region: str | None = None
    country: str | None = None
    parliamentary_constituency: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw_result: dict[str, Any] | None = None
    error: str | None = None

    def to_context_dict(self) -> dict[str, Any]:
        """Fields useful for LLM normalization."""
        return {
            "validated_postcode": self.postcode,
            "valid": self.valid,
            "admin_district": self.admin_district or "",
            "region": self.region or "",
            "country": self.country or "",
        }


class PostcodesIOClient:
    def __init__(self, base_url: str = DEFAULT_BASE, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def validate_postcode(self, postcode: str) -> PostcodeValidation:
        normalized = format_uk_postcode(postcode)
        compact = normalized.replace(" ", "")

        # Quick boolean check
        try:
            resp = self.session.get(
                f"{self.base_url}/postcodes/{compact}/validate",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            is_valid = bool(resp.json().get("result"))
        except requests.RequestException as exc:
            return PostcodeValidation(
                valid=False,
                postcode=normalized,
                error=str(exc),
            )

        if not is_valid:
            return PostcodeValidation(
                valid=False,
                postcode=normalized,
                error="Invalid UK postcode",
            )

        return self.lookup_postcode(normalized)

    def lookup_postcode(self, postcode: str) -> PostcodeValidation:
        normalized = format_uk_postcode(postcode)
        compact = normalized.replace(" ", "")

        try:
            resp = self.session.get(
                f"{self.base_url}/postcodes/{compact}",
                timeout=self.timeout,
            )
            data = resp.json()
        except requests.RequestException as exc:
            return PostcodeValidation(
                valid=False,
                postcode=normalized,
                error=str(exc),
            )

        if data.get("status") != 200 or not data.get("result"):
            return PostcodeValidation(
                valid=False,
                postcode=normalized,
                error=data.get("error", "Postcode lookup failed"),
            )

        result = data["result"]
        return PostcodeValidation(
            valid=True,
            postcode=result.get("postcode", normalized),
            admin_district=result.get("admin_district"),
            region=result.get("region"),
            country=result.get("country"),
            parliamentary_constituency=result.get("parliamentary_constituency"),
            latitude=result.get("latitude"),
            longitude=result.get("longitude"),
            raw_result=result,
        )

    def bulk_validate(self, postcodes: list[str]) -> list[PostcodeValidation]:
        """Validate up to 100 postcodes per request."""
        if not postcodes:
            return []

        payload = [p.replace(" ", "") for p in postcodes]
        try:
            resp = self.session.post(
                f"{self.base_url}/postcodes",
                json={"postcodes": payload},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            rows = resp.json().get("result", [])
        except requests.RequestException as exc:
            return [
                PostcodeValidation(valid=False, postcode=p, error=str(exc))
                for p in postcodes
            ]

        out: list[PostcodeValidation] = []
        for row in rows:
            query = format_uk_postcode(row.get("query", ""))
            result = row.get("result")
            if not result:
                out.append(
                    PostcodeValidation(
                        valid=False,
                        postcode=query,
                        error="Invalid UK postcode",
                    )
                )
                continue
            out.append(
                PostcodeValidation(
                    valid=True,
                    postcode=result.get("postcode", query),
                    admin_district=result.get("admin_district"),
                    region=result.get("region"),
                    country=result.get("country"),
                    parliamentary_constituency=result.get("parliamentary_constituency"),
                    latitude=result.get("latitude"),
                    longitude=result.get("longitude"),
                    raw_result=result,
                )
            )
        return out
