"""End-to-end: vendor address → validation → LLM → standard format."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .llm_validation import build_llm_only_context, merge_llm_validation_into_context
from .normalize import AddressNormalizer, DEFAULT_MODEL
from .ollama_client import OllamaTimeoutError
from .preprocess import PreprocessedAddress, preprocess
from .rag import attach_local_lookup
from .schema import StandardAddress, format_postal_code_city, is_valid_uk_postcode_format
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
    skip_validation: bool = False
    rag_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AddressPipeline:
    def __init__(
        self,
        model: str | None = None,
        ollama_host: str | None = None,
        skip_llm: bool = False,
        skip_validation: bool = False,
        validator: str | None = None,
    ):
        if validator:
            os.environ["ADDRESS_VALIDATOR"] = validator
        self.validator = get_validator()
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        host = ollama_host or os.getenv("OLLAMA_HOST")
        self.normalizer = AddressNormalizer(model=self.model, host=host)
        self.skip_llm = skip_llm
        self.skip_validation = skip_validation
        self._validator_name = (validator or os.getenv("ADDRESS_VALIDATOR") or "postcodes_io").lower()
        if self._validator_name == "postcodes_io" and os.getenv("LOCAL_ADDRESS_AUTO", "1") == "1":
            from .local_address_store import is_local_index_available
            if is_local_index_available():
                self._validator_name = "local_first"
        if skip_validation:
            self._validator_name = "llm_only"

    def run(self, vendor_address: str, customer_id: str = "", *, use_rag: bool | None = None) -> PipelineResult:
        warnings: list[str] = []
        errors: list[str] = []

        pre: PreprocessedAddress = preprocess(vendor_address)
        pre_dict = {
            "cleaned": pre.cleaned,
            "extracted_postcode": pre.extracted_postcode,
            "remainder_without_postcode": pre.remainder_without_postcode,
        }

        if self.skip_validation:
            val_dict = build_llm_only_context(pre)
            validation = None
            warnings.append(
                "External validation bypassed — Ollama assesses postcode format and maps fields. "
                "Enable Postcodes.io / Ideal Postcodes when ground-truth validation is required."
            )
            if not pre.extracted_postcode:
                warnings.append("No postcode detected in vendor text — LLM will attempt extraction.")
            elif not val_dict.get("postcode_format_ok"):
                warnings.append(
                    f"Extracted postcode '{pre.extracted_postcode}' may be malformed — LLM will review."
                )
        else:
            validation = self.validator.cleanse_address(
                vendor_address=vendor_address,
                postcode_hint=pre.extracted_postcode,
            )
            val_dict = validation.to_context_dict()
            if validation.raw_result:
                val_dict["lookup"] = _extract_lookup(validation)
            val_dict = attach_local_lookup(val_dict, vendor_address, pre.extracted_postcode)

            if validation.source == "local_index":
                tier = (validation.raw_result or {}).get("validation_tier", "local")
                if tier.startswith("street_first"):
                    conf = validation.confidence if validation.confidence is not None else 0.0
                    warnings.append(
                        f"Street-first local lookup resolved postcode {validation.postcode} "
                        f"(confidence {conf:.2f}, tier={tier})."
                    )
                elif validation.street_level_validated:
                    conf = validation.confidence if validation.confidence is not None else 0.0
                    warnings.append(f"Local address index match (confidence {conf:.2f}) — Postcodes.io skipped.")
                else:
                    warnings.append(f"Local postcode validated ({tier}) — street match not confirmed.")
            elif (validation.raw_result or {}).get("validation_tier") == "postcodes_io_fallback":
                warnings.append("Postcodes.io fallback used — local index was not confident.")

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
                    skip_validation=False,
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
                    skip_validation=False,
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
                    skip_validation=False,
                )

        if self.skip_llm:
            if self.skip_validation:
                normalized = self._rule_based_fallback(pre, _empty_validation(pre), customer_id)
                if pre.extracted_postcode:
                    normalized.postal_code = pre.extracted_postcode
                warnings.append(
                    "LLM skipped in validation-bypass mode — rule-based mapping only; "
                    "enable Ollama for postcode assessment."
                )
            elif validation and validation.street_level_validated:
                normalized = _map_validated_to_standard(validation, customer_id)
            else:
                normalized = self._rule_based_fallback(pre, validation or _empty_validation(pre), customer_id)
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
                skip_validation=self.skip_validation,
            )

        try:
            rule_hint = StandardAddress.from_vendor_text(
                pre.remainder_without_postcode, customer_id
            )
            if rule_hint.co or rule_hint.street_2 or rule_hint.street_3:
                val_dict = dict(val_dict)
                val_dict["rule_parser_hint"] = rule_hint.to_storage_dict()

            norm_result = self.normalizer.normalize(
                vendor_address=vendor_address,
                preprocessed_remainder=pre.remainder_without_postcode,
                validation_context=val_dict,
                customer_id=customer_id,
                use_rag=use_rag,
            )
            normalized = norm_result.address
            if self.skip_validation and norm_result.llm_validation:
                val_dict = merge_llm_validation_into_context(val_dict, norm_result.llm_validation)
                if norm_result.llm_validation.get("postcode_format_valid") is False:
                    warnings.append("LLM: postcode format invalid or missing.")
                if norm_result.llm_validation.get("postcode_plausible") is False:
                    warnings.append("LLM: postcode may not match city/area — manual review recommended.")
                notes = norm_result.llm_validation.get("validation_notes")
                if notes:
                    warnings.append(f"LLM validation: {notes}")
        except OllamaTimeoutError as exc:
            errors.append(str(exc))
            warnings.append("Ollama warm-up in progress - no fallback mapping returned.")
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
                skip_validation=self.skip_validation,
            )
        except Exception as exc:
            errors.append(f"LLM normalization failed: {exc}")
            if not self.skip_validation and validation and validation.street_level_validated:
                fallback = _map_validated_to_standard(validation, customer_id)
            else:
                fallback = self._rule_based_fallback(pre, validation or _empty_validation(pre), customer_id)
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
                skip_validation=self.skip_validation,
            )

        rag_meta = norm_result.rag_metadata or {} if not self.skip_llm else {}

        if self.skip_validation and normalized.postal_code:
            if not is_valid_uk_postcode_format(normalized.postal_code):
                warnings.append(
                    f"Output postcode '{normalized.postal_code}' failed UK format check — review required."
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
            skip_validation=self.skip_validation,
            rag_metadata=rag_meta,
        )

    @staticmethod
    def _rule_based_fallback(
        pre: PreprocessedAddress,
        validation: AddressValidation,
        customer_id: str,
    ) -> StandardAddress:
        addr = StandardAddress.from_vendor_text(pre.remainder_without_postcode, customer_id)
        addr.postal_code = validation.postcode or pre.extracted_postcode or ""
        if not addr.district:
            addr.district = (validation.admin_district or "").title()
        if not addr.other_city:
            addr.other_city = (
                validation.admin_district or validation.region or ""
            ).title()
        addr.postal_code_city = format_postal_code_city(addr.postal_code, addr.other_city)
        addr.country = "GB"
        addr.time_zone = "GMTUK"
        return addr


def _empty_validation(pre: PreprocessedAddress) -> AddressValidation:
    return AddressValidation(
        valid=False,
        source="llm_only",
        postcode=pre.extracted_postcode or "",
    )


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
