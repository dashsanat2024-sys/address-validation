"""Compressed local UK address index for fast validation before Postcodes.io."""

from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schema import format_uk_postcode

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INDEX = _ROOT / "data" / "local" / "uk_addresses.json.gz"

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")
# Noise tokens stripped for street-first matching
_STOPWORDS = frozenset(
    {
        "uk", "gb", "england", "united", "kingdom", "flat", "unit", "suite",
        "apartment", "apt", "floor", "flr", "the", "and", "ltd", "limited",
    }
)


@dataclass
class LocalAddressRecord:
    postcode: str
    number: str = ""
    street: str = ""
    unit: str = ""
    building: str = ""
    city: str = ""
    district: str = ""
    region: str = ""
    source: str = "local"

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> LocalAddressRecord:
        return cls(
            postcode=format_uk_postcode(row.get("pc") or row.get("postcode") or ""),
            number=str(row.get("n") or row.get("number") or "").strip(),
            street=str(row.get("s") or row.get("street") or "").strip(),
            unit=str(row.get("u") or row.get("unit") or "").strip(),
            building=str(row.get("b") or row.get("building") or "").strip(),
            city=str(row.get("city") or "").strip(),
            district=str(row.get("dist") or row.get("district") or "").strip(),
            region=str(row.get("region") or "").strip(),
            source=str(row.get("src") or row.get("source") or "local"),
        )

    def to_search_text(self) -> str:
        parts = [self.number, self.street, self.unit, self.building, self.city, self.district]
        return " ".join(p for p in parts if p).lower()

    def to_dict(self) -> dict[str, str]:
        return {
            "postcode": self.postcode,
            "number": self.number,
            "street": self.street,
            "unit": self.unit,
            "building": self.building,
            "city": self.city,
            "district": self.district,
            "region": self.region,
            "source": self.source,
        }


@dataclass
class LocalMatch:
    record: LocalAddressRecord
    confidence: float
    postcode_confident: bool
    address_confident: bool
    match_reason: str = ""

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "confidence": round(self.confidence, 3),
            "postcode_confident": self.postcode_confident,
            "address_confident": self.address_confident,
            "match_reason": self.match_reason,
            "matched_address": self.record.to_dict(),
        }


def index_path() -> Path:
    return Path(os.getenv("LOCAL_ADDRESS_INDEX", str(_DEFAULT_INDEX)))


def is_local_index_available() -> bool:
    path = index_path()
    return path.is_file() and path.stat().st_size > 0


def street_first_enabled() -> bool:
    return os.getenv("LOCAL_STREET_FIRST", "1").strip().lower() in {"1", "true", "yes"}


def _tokens(text: str, *, strip_postcode: bool = False) -> set[str]:
    cleaned = text or ""
    if strip_postcode:
        cleaned = POSTCODE_RE.sub(" ", cleaned)
    toks = set(TOKEN_RE.findall(cleaned.lower()))
    return {t for t in toks if t not in _STOPWORDS and len(t) > 1}


def _extract_postcode(text: str) -> str:
    m = POSTCODE_RE.search(text or "")
    if not m:
        return ""
    return format_uk_postcode(m.group(1))


def _compact_postcode(postcode: str) -> str:
    return format_uk_postcode(postcode).replace(" ", "").upper()


def _min_confidence() -> float:
    return float(os.getenv("LOCAL_ADDRESS_MIN_CONFIDENCE", "0.55"))


def _postcode_only_confidence() -> float:
    return float(os.getenv("LOCAL_POSTCODE_CONFIDENCE", "0.35"))


@lru_cache(maxsize=1)
def _load_records() -> tuple[LocalAddressRecord, ...]:
    path = index_path()
    if not path.is_file():
        return ()
    records: list[LocalAddressRecord] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = LocalAddressRecord.from_dict(row)
            if rec.postcode:
                records.append(rec)
    return tuple(records)


@lru_cache(maxsize=1)
def _postcode_index() -> dict[str, list[LocalAddressRecord]]:
    idx: dict[str, list[LocalAddressRecord]] = {}
    for rec in _load_records():
        key = _compact_postcode(rec.postcode)
        idx.setdefault(key, []).append(rec)
    return idx


def record_count() -> int:
    return len(_load_records())


def _score_match(vendor_address: str, rec: LocalAddressRecord) -> float:
    vendor_tokens = _tokens(vendor_address, strip_postcode=True)
    rec_tokens = _tokens(rec.to_search_text())
    if not vendor_tokens or not rec_tokens:
        return 0.0
    overlap = len(vendor_tokens & rec_tokens) / len(vendor_tokens | rec_tokens)
    score = overlap
    lower = vendor_address.lower()
    if rec.number and rec.number.lower() in lower:
        score += 0.2
    if rec.street and rec.street.lower() in lower:
        score += 0.25
    if rec.building and rec.building.lower() in lower:
        score += 0.15
    if rec.unit and rec.unit.lower() in lower:
        score += 0.1
    if rec.city and rec.city.lower() in lower:
        score += 0.1
    return score


def _build_match(
    rec: LocalAddressRecord,
    score: float,
    *,
    reason: str,
    min_conf: float,
    pc_conf: float,
    candidate_count: int = 1,
) -> LocalMatch:
    address_confident = score >= min_conf
    postcode_confident = address_confident or score >= pc_conf or candidate_count == 1
    return LocalMatch(
        record=rec,
        confidence=score,
        postcode_confident=postcode_confident,
        address_confident=address_confident,
        match_reason=reason,
    )


def _lookup_by_postcode(
    vendor_address: str,
    postcode: str,
    *,
    min_conf: float,
    pc_conf: float,
) -> LocalMatch | None:
    candidates = _postcode_index().get(_compact_postcode(postcode), [])
    if not candidates:
        return LocalMatch(
            record=LocalAddressRecord(postcode=postcode, source="vendor_extract"),
            confidence=pc_conf,
            postcode_confident=False,
            address_confident=False,
            match_reason="postcode_not_in_local_index",
        )

    best: LocalAddressRecord | None = None
    best_score = 0.0
    for rec in candidates:
        score = _score_match(vendor_address, rec)
        if score > best_score:
            best_score = score
            best = rec

    if not best:
        return None

    reason = "street_level_match" if best_score >= min_conf else "postcode_area_match"
    if best_score <= pc_conf and len(candidates) > 1:
        reason = "postcode_ambiguous"

    return _build_match(
        best, best_score, reason=reason, min_conf=min_conf, pc_conf=pc_conf,
        candidate_count=len(candidates),
    )


def lookup_by_street(
    vendor_address: str,
    *,
    min_confidence: float | None = None,
) -> LocalMatch | None:
    """Scan full index by street/number/building tokens (ignores vendor postcode)."""
    if not is_local_index_available():
        return None

    min_conf = min_confidence if min_confidence is not None else _min_confidence()
    pc_conf = _postcode_only_confidence()
    records = _load_records()
    if not records:
        return None

    best: LocalAddressRecord | None = None
    best_score = 0.0
    for rec in records:
        if not rec.street and not rec.building:
            continue
        score = _score_match(vendor_address, rec)
        if score > best_score:
            best_score = score
            best = rec

    if not best or best_score < pc_conf:
        return None

    reason = "street_first_match" if best_score >= min_conf else "street_first_weak"
    return _build_match(
        best, best_score, reason=reason, min_conf=min_conf, pc_conf=pc_conf,
    )


def lookup(
    vendor_address: str,
    postcode_hint: str | None = None,
    *,
    min_confidence: float | None = None,
    postcode_only_confidence: float | None = None,
    prefer_street_first: bool | None = None,
) -> LocalMatch | None:
    """Postcode-first lookup with optional street-first fallback."""
    if not is_local_index_available():
        return None

    min_conf = min_confidence if min_confidence is not None else _min_confidence()
    pc_conf = postcode_only_confidence if postcode_only_confidence is not None else _postcode_only_confidence()
    use_street = prefer_street_first if prefer_street_first is not None else street_first_enabled()

    extracted_pc = format_uk_postcode(postcode_hint or _extract_postcode(vendor_address))
    pc_match: LocalMatch | None = None

    if extracted_pc:
        pc_match = _lookup_by_postcode(vendor_address, extracted_pc, min_conf=min_conf, pc_conf=pc_conf)

    if not use_street:
        return pc_match

    street_match = lookup_by_street(vendor_address, min_confidence=min_conf)

    # No postcode in vendor text — street-first only path
    if not extracted_pc:
        return street_match

    if pc_match is None:
        return street_match

    # Postcode bucket empty / wrong — prefer confident street match
    if pc_match.match_reason == "postcode_not_in_local_index" and street_match:
        if street_match.address_confident or (
            street_match.confidence > pc_match.confidence
        ):
            street_match.match_reason = "street_first_over_postcode"
            street_match.postcode_confident = street_match.address_confident
            return street_match
        return pc_match

    # Low confidence under vendor postcode — street-first may correct wrong PC
    if street_match and street_match.address_confident:
        if not pc_match.address_confident or street_match.confidence > pc_match.confidence + 0.05:
            street_match.match_reason = "street_first_over_postcode"
            return street_match

    return pc_match


def clear_cache() -> None:
    _load_records.cache_clear()
    _postcode_index.cache_clear()
