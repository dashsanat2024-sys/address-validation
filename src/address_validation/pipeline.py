"""End-to-end: vendor address → validation → LLM → standard format."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .normalize import AddressNormalizer, DEFAULT_MODEL
from .preprocess import PreprocessedAddress, preprocess
from .schema import StandardAddress, format_postal_code_city
from .validation_result import AddressValidation
from .validator_factory import get_validator

HOUSE_NUM_RE = re.compile(r"^(\d+[A-Za-z]?)\s*(.*)$")


@dataclass
class PipelineResult:
    success: bool
    vendor_address: str
    customer_id: str
    preprocessed: dict[str, Any]
    postcode_validation: dict[str, Any]
    normalized_address: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    validator: str = "postcodes_io"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AddressPipeline:
    def __init__(
        self,
        model: str | None = None,
        ollama_host: str | None = None,
        skip_llm: bool = False,
        validator: str | None = None,
    ):
        if validator:
            os.environ["ADDRESS_VALIDATOR"] = validator
        self.validator = get_validator()
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self.normalizer = AddressNormalizer(model=self.model, host=ollama_host)
        self.skip_llm = skip_llm
        self._validator_name = (validator or os.getenv("ADDRESS_VALIDATOR") or "postcodes_io").lower()

    def run(self, vendor_address: str, customer_id: str = "") -> PipelineResult:
        warnings: list[str] = []
        errors: list[str] = []

        pre: PreprocessedAddress = preprocess(vendor_address)
        pre_dict = {
            "cleaned": pre.cleaned,
            "extracted_postcode": pre.extracted_postcode,
            "remainder_without_postcode": pre.remainder_without_postcode,
        }

        validation: AddressValidation = self.validator.cleanse_address(
            vendor_address=vendor_address,
            postcode_hint=pre.extracted_postcode,
        )
        val_dict = validation.to_context_dict()
        if validation.raw_result:
            val_dict["lookup"] = _extract_lookup(validation)

        if not pre.extracted_postcode and not validation.valid:
            errors.append("No UK postcode found in vendor address")
            return PipelineResult(
                success=False,
                vendor_address=vendor_address,
                customer_id=customer_id,
                preprocessed=pre_dict,
                postcode_validation=val_dict,
                normalized_address={},
                warnings=warnings,
                errors=errors,
                model=self.model,
                validator=self._validator_name,
            )

        if not validation.valid:
            errors.append(validation.error or "Address validation failed")
            return PipelineResult(
                success=False,
                vendor_address=vendor_address,
                customer_id=customer_id,
                preprocessed=pre_dict,
                postcode_validation=val_dict,
                normalized_address={},
                warnings=warnings,
                errors=errors,
                model=self.model,
                validator=self._validator_name,
            )

        if validation.street_level_validated:
            warnings.append(
                f"Street-level validation via {validation.source} "
                f"(confidence {validation.confidence:.2f})."
            )
        else:
            warnings.append(
                "Postcode area validated only — street-level match not verified. "
                "Set ADDRESS_VALIDATOR=ideal_postcodes with API key for full validation."
            )

        if validation.street_level_validated and validation.confidence and validation.confidence >= 0.9:
            normalized = _map_validated_to_standard(validation, customer_id)
            return PipelineResult(
                success=True,
                vendor_address=vendor_address,
                customer_id=customer_id,
                preprocessed=pre_dict,
                postcode_validation=val_dict,
                normalized_address=normalized.to_storage_dict(),
                warnings=warnings + ["High-confidence match — LLM skipped"],
                errors=errors,
                model=self.model,
                validator=self._validator_name,
            )

        if self.skip_llm:
            if validation.street_level_validated:
                normalized = _map_validated_to_standard(validation, customer_id)
            else:
                normalized = self._rule_based_fallback(pre, validation, customer_id)
            return PipelineResult(
                success=True,
                vendor_address=vendor_address,
                customer_id=customer_id,
                preprocessed=pre_dict,
                postcode_validation=val_dict,
                normalized_address=normalized.to_storage_dict(),
                warnings=warnings + ["LLM skipped — rule-based / validated mapping used"],
                errors=errors,
                model=self.model,
                validator=self._validator_name,
            )

        try:
            normalized = self.normalizer.normalize(
                vendor_address=vendor_address,
                preprocessed_remainder=pre.remainder_without_postcode,
                validation_context=val_dict,
                customer_id=customer_id,
            )
        except Exception as exc:
            errors.append(f"LLM normalization failed: {exc}")
            if validation.street_level_validated:
                fallback = _map_validated_to_standard(validation, customer_id)
            else:
                fallback = self._rule_based_fallback(pre, validation, customer_id)
            return PipelineResult(
                success=False,
                vendor_address=vendor_address,
                customer_id=customer_id,
                preprocessed=pre_dict,
                postcode_validation=val_dict,
                normalized_address=fallback.to_storage_dict(),
                warnings=warnings + ["Fell back to validated/rule-based parsing"],
                errors=errors,
                model=self.model,
                validator=self._validator_name,
            )

        if not normalized.is_complete():
            warnings.append("Normalized address may be incomplete — review recommended")

        return PipelineResult(
            success=True,
            vendor_address=vendor_address,
            customer_id=customer_id,
            preprocessed=pre_dict,
            postcode_validation=val_dict,
            normalized_address=normalized.to_storage_dict(),
            warnings=warnings,
            errors=errors,
            model=self.model,
            validator=self._validator_name,
        )

    @staticmethod
    def _rule_based_fallback(
        pre: PreprocessedAddress,
        validation: AddressValidation,
        customer_id: str,
    ) -> StandardAddress:
        addr = StandardAddress.from_vendor_text(pre.remainder_without_postcode, customer_id)
        addr.postal_code = validation.postcode
        addr.district = (validation.admin_district or addr.district or "").title()
        addr.other_city = (validation.region or addr.other_city or "").title()
        addr.postal_code_city = format_postal_code_city(addr.postal_code, addr.other_city)
        addr.country = "GB"
        addr.time_zone = "GMTUK"
        return addr


def _split_line_to_street(line: str) -> tuple[str, str]:
    line = (line or "").strip()
    match = HOUSE_NUM_RE.match(line)
    if match:
        return match.group(1), (match.group(2) or "").title()
    return "", line.title()


def _map_validated_to_standard(validation: AddressValidation, customer_id: str) -> StandardAddress:
    lines = validation.validated_lines
    line1 = lines.get("line_1", "")
    line2 = lines.get("line_2", "")
    line3 = lines.get("line_3", "")

    house_num, street_name = _split_line_to_street(line2 or line1)
    if not house_num and line1:
        house_num, street_from_1 = _split_line_to_street(line1)
        if street_from_1 and not street_name:
            street_name = street_from_1

    other_city = lines.get("post_town") or validation.region or ""
    postal_code = lines.get("postcode") or validation.postcode

    return StandardAddress(
        customer_id=customer_id,
        street_2=line1 if line1 and not house_num else (line1 if "flat" in line1.lower() else ""),
        street_3=line3,
        street_house_number=house_num,
        street_4=street_name or line2,
        street_5="",
        district=lines.get("county") or validation.admin_district or "",
        other_city=other_city,
        postal_code=postal_code,
        postal_code_city=format_postal_code_city(postal_code, other_city),
        country="GB",
        time_zone="GMTUK",
    )


def _extract_lookup(validation: AddressValidation) -> dict[str, Any]:
    raw = validation.raw_result or {}
    if validation.source == "postcodes_io":
        result = raw.get("result") or raw
        return {
            k: result.get(k)
            for k in ("parliamentary_constituency", "admin_ward", "nuts")
            if isinstance(result, dict) and result.get(k)
        }
    match = (raw.get("result") or {}).get("match") or {}
    return {k: match.get(k) for k in ("confidence", "post_town_match", "thoroughfare_match") if match.get(k) is not None}
