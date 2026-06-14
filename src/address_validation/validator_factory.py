"""Select address validator from environment."""

from __future__ import annotations

import os
from typing import Protocol

from .ideal_postcodes import IdealPostcodesClient
from .postcodes_io import PostcodesIOClient
from .validation_result import AddressValidation


class AddressValidator(Protocol):
    def validate_postcode(self, postcode: str) -> AddressValidation: ...


class CompositeValidator:
    """Ideal Postcodes for street-level cleanse; Postcodes.io as postcode fallback."""

    def __init__(self):
        self.ideal = IdealPostcodesClient()
        self.postcodes_io = PostcodesIOClient(
            base_url=os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io")
        )
        self.min_confidence = self.ideal.min_confidence

    def cleanse_address(
        self,
        vendor_address: str,
        postcode_hint: str | None = None,
        post_town_hint: str | None = None,
    ) -> AddressValidation:
        if self.ideal.configured:
            result = self.ideal.cleanse_address(
                vendor_address,
                postcode_hint=postcode_hint,
                post_town_hint=post_town_hint,
            )
            if result.valid:
                return result
            # Fall through to postcode-only if cleanse fails
            if postcode_hint:
                fallback = self.postcodes_io.validate_postcode(postcode_hint)
                if fallback.valid:
                    fallback.error = result.error
                    return fallback
            return result

        if postcode_hint:
            return self.postcodes_io.validate_postcode(postcode_hint)
        return AddressValidation(
            valid=False,
            source="postcodes_io",
            postcode="",
            error="No postcode to validate",
        )

    def validate_postcode(self, postcode: str) -> AddressValidation:
        if self.ideal.configured:
            result = self.ideal.validate_postcode(postcode)
            if result.valid:
                return result
        return self.postcodes_io.validate_postcode(postcode)


def _postcodes_to_validation(result) -> AddressValidation:
    return AddressValidation(
        valid=result.valid,
        source="postcodes_io",
        postcode=result.postcode,
        admin_district=result.admin_district,
        region=result.region,
        country=result.country,
        parliamentary_constituency=result.parliamentary_constituency,
        latitude=result.latitude,
        longitude=result.longitude,
        street_level_validated=False,
        raw_result=result.raw_result,
        error=result.error,
    )


class PostcodesIOValidator:
    def __init__(self, base_url: str | None = None):
        self._client = PostcodesIOClient(
            base_url=base_url or os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io")
        )

    def cleanse_address(
        self,
        vendor_address: str,
        postcode_hint: str | None = None,
        post_town_hint: str | None = None,
    ) -> AddressValidation:
        if not postcode_hint:
            return AddressValidation(
                valid=False,
                source="postcodes_io",
                postcode="",
                error="No UK postcode found in vendor address",
            )
        return _postcodes_to_validation(self._client.validate_postcode(postcode_hint))

    def validate_postcode(self, postcode: str) -> AddressValidation:
        return _postcodes_to_validation(self._client.validate_postcode(postcode))


def get_validator() -> CompositeValidator | PostcodesIOValidator:
    mode = (os.getenv("ADDRESS_VALIDATOR") or "postcodes_io").strip().lower()
    if mode in {"ideal_postcodes", "ideal", "composite"}:
        return CompositeValidator()
    return PostcodesIOValidator()
