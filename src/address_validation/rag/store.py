"""Load RAG knowledge base from human corrections and training pairs."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORRECTIONS = _ROOT / "data" / "review" / "corrections.csv"
DEFAULT_JSONL = _ROOT / "data" / "training" / "from_corrections.jsonl"


@dataclass(frozen=True)
class RagExample:
    vendor_address: str
    mapped: dict[str, str]
    source: str
    weight: float = 1.0


def _parse_json_field(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _sap_fields(data: dict) -> dict[str, str]:
    keys = (
        "co", "street_2", "street_3", "street_house_number", "street_4", "street_5",
        "district", "other_city", "postal_code", "postal_code_city", "country", "time_zone",
    )
    return {k: str(data.get(k, "") or "").strip() for k in keys if data.get(k)}


def load_examples() -> list[RagExample]:
    examples: list[RagExample] = []
    seen: set[str] = set()

    corrections_path = Path(os.getenv("RAG_CORRECTIONS_PATH", str(DEFAULT_CORRECTIONS)))
    if corrections_path.is_file():
        with corrections_path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                vendor = (row.get("vendor_address") or "").strip()
                mapped = _sap_fields(_parse_json_field(row.get("human_corrected") or ""))
                if not vendor or not mapped:
                    continue
                key = vendor.lower()
                if key in seen:
                    continue
                seen.add(key)
                examples.append(RagExample(vendor, mapped, source="human_correction", weight=2.0))

    jsonl_path = Path(os.getenv("RAG_JSONL_PATH", str(DEFAULT_JSONL)))
    if jsonl_path.is_file():
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                vendor = (row.get("input") or "").strip()
                output = _parse_json_field(row.get("output") or "")
                mapped = _sap_fields(output)
                if not vendor or not mapped:
                    continue
                key = vendor.lower()
                if key in seen:
                    continue
                seen.add(key)
                examples.append(RagExample(vendor, mapped, source="training_pair", weight=1.0))

    max_rows = int(os.getenv("RAG_MAX_EXAMPLES", "200"))
    return examples[:max_rows] if max_rows > 0 else examples
