#!/usr/bin/env python3
"""Build compressed local UK address index (KB-scale) for offline validation.

Sources (OpenAddressUK / ODI project is defunct; we use open data equivalents):
  - Human corrections (data/review/corrections.csv, data/training/from_corrections.jsonl)
  - Training / synthetic JSONL (street-level examples)
  - Postcodes.io random postcodes (postcode metadata only)
  - Optional OpenAddresses CSV URL via LOCAL_OA_CSV_URL env

Output: data/local/uk_addresses.json.gz (one JSON object per line, gzip compressed)
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from address_validation.schema import format_uk_postcode  # noqa: E402

OUT_PATH = Path(os.getenv("LOCAL_ADDRESS_INDEX", str(ROOT / "data" / "local" / "uk_addresses.json.gz")))
MAX_RECORDS = int(os.getenv("LOCAL_INDEX_MAX_RECORDS", "800"))
POSTCODE_FETCH = int(os.getenv("LOCAL_INDEX_POSTCODE_FETCH", "120"))

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE)


def _compact_row(**kwargs: str) -> dict[str, str]:
    row: dict[str, str] = {}
    key_map = {
        "postcode": "pc",
        "number": "n",
        "street": "s",
        "unit": "u",
        "building": "b",
        "city": "city",
        "district": "dist",
        "region": "region",
        "source": "src",
    }
    for k, short in key_map.items():
        v = (kwargs.get(k) or "").strip()
        if v:
            row[short] = v
    return row


def _dedupe_key(row: dict[str, str]) -> str:
    pc = row.get("pc", "").replace(" ", "").upper()
    return "|".join([pc, row.get("n", ""), row.get("s", "").lower(), row.get("b", "").lower()])


def _extract_postcode(text: str) -> str:
    m = POSTCODE_RE.search(text or "")
    return format_uk_postcode(m.group(1)) if m else ""


def _from_mapped_output(output: dict) -> dict[str, str]:
    return _compact_row(
        postcode=output.get("postal_code") or output.get("postcode") or "",
        number=output.get("street_house_number") or "",
        street=output.get("street_4") or "",
        unit=output.get("street_2") or "",
        building=output.get("street_3") or "",
        city=output.get("other_city") or output.get("district") or "",
        district=output.get("district") or "",
        source="corrections",
    )


def _load_jsonl(path: Path, source: str) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        output = obj.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                continue
        if not isinstance(output, dict):
            continue
        row = _from_mapped_output(output)
        if not row.get("pc"):
            row["pc"] = _extract_postcode(obj.get("input") or "")
        row["src"] = source
        if row.get("pc"):
            rows.append(row)
    return rows


def _load_corrections_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mapped = {k: row.get(k, "") for k in row}
            compact = _from_mapped_output(
                {
                    "postal_code": mapped.get("postal_code") or mapped.get("corrected_postal_code") or "",
                    "street_house_number": mapped.get("street_house_number") or "",
                    "street_4": mapped.get("street_4") or "",
                    "street_2": mapped.get("street_2") or "",
                    "street_3": mapped.get("street_3") or "",
                    "other_city": mapped.get("other_city") or mapped.get("district") or "",
                    "district": mapped.get("district") or "",
                }
            )
            if not compact.get("pc"):
                compact["pc"] = _extract_postcode(
                    mapped.get("vendor_address") or mapped.get("original_address") or ""
                )
            compact["src"] = "corrections_csv"
            if compact.get("pc"):
                rows.append(compact)
    return rows


def _load_postcodes_cache(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pc = format_uk_postcode(item.get("postcode") or "")
        if not pc:
            continue
        rows.append(
            _compact_row(
                postcode=pc,
                city=item.get("admin_district") or "",
                district=item.get("admin_district") or "",
                region=item.get("region") or "",
                source="postcodes_cache",
            )
        )
    return rows


def _fetch_postcodes_io(limit: int) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    base = os.getenv("POSTCODES_IO_BASE", "https://api.postcodes.io").rstrip("/")
    rows: list[dict[str, str]] = []
    try:
        resp = requests.get(f"{base}/random/postcodes", params={"limit": min(limit, 100)}, timeout=15)
        resp.raise_for_status()
        for item in resp.json().get("result") or []:
            pc = format_uk_postcode(item.get("postcode") or "")
            if not pc:
                continue
            rows.append(
                _compact_row(
                    postcode=pc,
                    city=item.get("admin_district") or "",
                    district=item.get("admin_district") or "",
                    region=item.get("region") or "",
                    source="postcodes_io",
                )
            )
    except requests.RequestException as exc:
        print(f"  postcodes.io fetch skipped: {exc}", file=sys.stderr)
    return rows


def _load_openaddresses_csv(url: str, max_rows: int) -> list[dict[str, str]]:
    """Parse OpenAddresses CSV (LON,LAT,NUMBER,STREET,UNIT,CITY,DISTRICT,REGION,POSTCODE,...)."""
    if not url:
        return []
    rows: list[dict[str, str]] = []
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        lines = resp.text.splitlines()
    except requests.RequestException as exc:
        print(f"  OpenAddresses CSV skipped: {exc}", file=sys.stderr)
        return []

    for line in lines[: max_rows + 1]:
        if not line or line.startswith("#") or line.lower().startswith("lon"):
            continue
        parts = line.split(",")
        if len(parts) < 9:
            continue
        pc = format_uk_postcode(parts[8].strip())
        if not pc:
            continue
        rows.append(
            _compact_row(
                postcode=pc,
                number=parts[2].strip(),
                street=parts[3].strip(),
                unit=parts[4].strip(),
                city=parts[5].strip(),
                district=parts[6].strip(),
                region=parts[7].strip(),
                source="openaddresses",
            )
        )
    return rows


def build_index() -> Path:
    seen: set[str] = set()
    records: list[dict[str, str]] = []

    def add_rows(rows: list[dict[str, str]]) -> None:
        nonlocal records
        for row in rows:
            if not row.get("pc"):
                continue
            key = _dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            records.append(row)
            if len(records) >= MAX_RECORDS:
                return

    sources = [
        ("corrections.jsonl", _load_jsonl(ROOT / "data" / "training" / "from_corrections.jsonl", "corrections")),
        ("corrections.csv", _load_corrections_csv(ROOT / "data" / "review" / "corrections.csv")),
        ("synthetic.jsonl", _load_jsonl(ROOT / "data" / "training" / "synthetic.jsonl", "synthetic")),
        ("synthetic_sample.jsonl", _load_jsonl(ROOT / "data" / "training" / "synthetic_sample.jsonl", "synthetic")),
        ("postcodes_cache.json", _load_postcodes_cache(ROOT / "data" / "training" / "postcodes_cache.json")),
    ]

    oa_url = os.getenv("LOCAL_OA_CSV_URL", "").strip()
    if oa_url:
        sources.append(("openaddresses_csv", _load_openaddresses_csv(oa_url, MAX_RECORDS)))

    for name, rows in sources:
        before = len(records)
        add_rows(rows)
        print(f"  {name}: +{len(records) - before} (total {len(records)})")
        if len(records) >= MAX_RECORDS:
            break

    if len(records) < MAX_RECORDS:
        before = len(records)
        add_rows(_fetch_postcodes_io(POSTCODE_FETCH))
        print(f"  postcodes.io random: +{len(records) - before} (total {len(records)})")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_PATH, "wt", encoding="utf-8", compresslevel=9) as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    raw_bytes = sum(len(json.dumps(r, separators=(",", ":"))) + 1 for r in records)
    gz_bytes = OUT_PATH.stat().st_size
    print(f"\nWrote {len(records)} records → {OUT_PATH}")
    print(f"  Uncompressed ~{raw_bytes // 1024} KB → gzip {gz_bytes // 1024} KB ({gz_bytes} bytes)")
    return OUT_PATH


if __name__ == "__main__":
    print("Building local UK address index…")
    build_index()
