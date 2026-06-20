"""Synthetic UK vendor addresses for fine-tuning."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterator

from .export import build_training_output, instruction_record
from .postcode_fetch import DEFAULT_CACHE, fetch_random_postcodes, mutate_invalid_postcode

FLAT_PREFIXES = ("Flat", "Apartment", "Unit", "Suite", "Room")
STREET_SUFFIXES = ("Road", "Street", "Lane", "Avenue", "Drive", "Close", "Parade", "Way")
BUILDING_NAMES = (
    "Elliot's Yard",
    "Burford Lodge",
    "Oak House",
    "The Old Mill",
    "Riverside Court",
    "Kingfisher House",
    "Victoria Mews",
    "Grosvenor House",
    "Park View",
    "The Granary",
)
STREET_NAMES = (
    "Gulson",
    "High",
    "Church",
    "Station",
    "Victoria",
    "King",
    "Queen",
    "Market",
    "Park",
    "London",
    "Mill",
    "Green",
)


@dataclass
class AddressComponents:
    flat_label: str = ""
    flat_number: str = ""
    building: str = ""
    house_number: str = ""
    street_name: str = ""
    street_suffix: str = "Road"
    city: str = ""
    district: str = ""
    postcode: str = ""
    valid: bool = True
    postcode_exists: bool = True
    validation_notes: str = ""

    @property
    def flat_display(self) -> str:
        if self.flat_label and self.flat_number:
            return f"{self.flat_label} {self.flat_number}"
        return ""

    @property
    def street_line(self) -> str:
        return f"{self.house_number} {self.street_name} {self.street_suffix}".strip()

    def to_address_fields(self) -> dict[str, str]:
        return {
            "co": "",
            "street_2": self.flat_display,
            "street_3": self.building,
            "street_house_number": self.house_number,
            "street_4": f"{self.street_name} {self.street_suffix}".strip(),
            "street_5": "",
            "district": self.district or self.city,
            "other_city": self.city,
            "postal_code": self.postcode if self.valid else self.postcode,
            "country": "GB",
            "time_zone": "GMTUK",
            "transportation_zone": "",
            "reg_struct_grp": "",
            "undeliverable": "X" if not self.postcode_exists and self.valid else "",
            "po_box_address": "",
            "po_box": "",
        }


def _segments(comp: AddressComponents) -> list[str]:
    segs: list[str] = []
    if comp.flat_display:
        segs.append(comp.flat_display)
    if comp.building:
        segs.append(comp.building)
    if comp.street_line:
        segs.append(comp.street_line)
    if comp.city:
        segs.append(comp.city)
    if comp.postcode:
        segs.append(comp.postcode.replace(" ", "") if random.random() < 0.3 else comp.postcode)
    return segs


def _permute_vendor_text(comp: AddressComponents, rng: random.Random) -> str:
    segs = _segments(comp)
    if len(segs) < 2:
        return ", ".join(segs)

    order = list(segs)
    rng.shuffle(order)
    fmt = rng.choice(["comma", "space", "mixed"])
    if fmt == "comma":
        return ", ".join(order)
    if fmt == "space":
        return " ".join(order)
    # mixed: commas between logical groups, sometimes run together
    return ", ".join(order[:3]) + " " + " ".join(order[3:])


def _house_only_vendor(comp: AddressComponents, rng: random.Random) -> str:
    parts = [comp.street_line, comp.city, comp.postcode]
    rng.shuffle(parts)
    return rng.choice([", ".join(parts), " ".join(parts)])


def _invalid_format_postcode(rng: random.Random) -> str:
    return rng.choice(["INVALID", "12345", "AB1", "ZZZZ 999"])


@dataclass
class SyntheticGenerator:
    seed: int = 42
    invalid_ratio: float = 0.15
    permutations_per_base: int = 4

    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def _base_from_postcode(self, meta: dict[str, Any]) -> AddressComponents:
        city = meta.get("admin_district") or meta.get("region") or "London"
        street = self._rng.choice(STREET_NAMES)
        suffix = self._rng.choice(STREET_SUFFIXES)
        pattern = self._rng.choice(["flat_building", "house_only", "flat_building", "named_building"])

        comp = AddressComponents(
            house_number=str(self._rng.randint(1, 200)),
            street_name=street,
            street_suffix=suffix,
            city=city.title(),
            district=(meta.get("admin_district") or city).title(),
            postcode=meta["postcode"],
            valid=True,
            postcode_exists=True,
        )

        if pattern == "flat_building":
            comp.flat_label = self._rng.choice(FLAT_PREFIXES)
            comp.flat_number = str(self._rng.randint(1, 50))
            comp.building = self._rng.choice(BUILDING_NAMES)
        elif pattern == "named_building":
            comp.building = self._rng.choice(BUILDING_NAMES)
        return comp

    def _invalid_variant(self, base: AddressComponents) -> AddressComponents:
        kind = self._rng.choice(["not_exists", "bad_format", "typo_exists"])
        comp = replace(base)
        if kind == "bad_format":
            comp.postcode = _invalid_format_postcode(self._rng)
            comp.valid = False
            comp.postcode_exists = False
            comp.validation_notes = "Postcode format invalid"
        elif kind == "not_exists":
            comp.postcode = mutate_invalid_postcode(base.postcode)
            comp.valid = True
            comp.postcode_exists = False
            comp.validation_notes = "Postcode format valid but not found in Postcodes.io"
        else:
            comp.postcode = mutate_invalid_postcode(base.postcode)
            comp.valid = True
            comp.postcode_exists = False
            comp.validation_notes = "Likely typo — postcode not found"
        return comp

    def generate(
        self,
        target_count: int = 2000,
        postcode_count: int = 400,
        *,
        cache_path: str | Path | None = None,
        postcodes: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        from pathlib import Path

        if postcodes is None:
            path = Path(cache_path) if cache_path else DEFAULT_CACHE
            postcodes = fetch_random_postcodes(postcode_count, cache_path=path)
        records: list[dict[str, Any]] = []
        seen_inputs: set[str] = set()

        for meta in postcodes:
            base = self._base_from_postcode(meta)
            variants = [base]

            if self._rng.random() < self.invalid_ratio:
                variants.append(self._invalid_variant(base))

            for comp in variants:
                texts = [
                    _permute_vendor_text(comp, self._rng)
                    for _ in range(self.permutations_per_base)
                ]
                if not comp.flat_display:
                    texts.append(_house_only_vendor(comp, self._rng))

                for vendor_text in texts:
                    vendor_text = re.sub(r"\s+", " ", vendor_text).strip()
                    key = vendor_text.upper()
                    if key in seen_inputs:
                        continue
                    seen_inputs.add(key)

                    fields = comp.to_address_fields()
                    output = build_training_output(
                        fields,
                        postcode_format_valid=comp.valid and bool(comp.postcode),
                        postcode_exists=comp.postcode_exists,
                        postcode_plausible=comp.postcode_exists,
                        validation_notes=comp.validation_notes,
                    )
                    records.append(instruction_record(vendor_text, output))

                    if len(records) >= target_count:
                        return records

        return records

    def iter_records(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        for row in self.generate(**kwargs):
            yield row
