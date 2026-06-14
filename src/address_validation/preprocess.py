"""Extract and clean postcodes from messy vendor address strings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import format_uk_postcode

# UK postcode pattern embedded in free text
POSTCODE_IN_TEXT_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)

# Common vendor noise
NOISE_RE = re.compile(r"[\r\n\t]+|[,;]{2,}")
MULTI_SPACE_RE = re.compile(r"\s{2,}")


@dataclass
class PreprocessedAddress:
    raw: str
    cleaned: str
    extracted_postcode: str | None
    remainder_without_postcode: str


def clean_vendor_text(raw: str) -> str:
    text = (raw or "").strip()
    text = NOISE_RE.sub(" ", text)
    text = text.replace("\n", ", ").replace(";", ",")
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip(" ,")


def extract_postcode(text: str) -> str | None:
    match = POSTCODE_IN_TEXT_RE.search(text or "")
    if not match:
        return None
    return format_uk_postcode(match.group(1))


def remove_postcode_from_text(text: str, postcode: str | None) -> str:
    if not postcode:
        return text
    compact = re.sub(r"\s+", "", postcode, flags=re.IGNORECASE)
    pattern = re.compile(re.escape(compact), re.IGNORECASE)
    without = pattern.sub("", text)
    # Also try spaced form
    spaced = re.escape(postcode)
    without = re.sub(spaced, "", without, flags=re.IGNORECASE)
    return clean_vendor_text(without)


def preprocess(raw_address: str) -> PreprocessedAddress:
    cleaned = clean_vendor_text(raw_address)
    postcode = extract_postcode(cleaned)
    remainder = remove_postcode_from_text(cleaned, postcode)
    return PreprocessedAddress(
        raw=raw_address,
        cleaned=cleaned,
        extracted_postcode=postcode,
        remainder_without_postcode=remainder,
    )
