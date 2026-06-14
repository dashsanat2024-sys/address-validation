"""Import vendor addresses from CSV with flexible column mapping."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[2] / "config" / "vendor_mapping.json"

# Common header aliases vendors use
ADDRESS_ALIASES = (
    "input_address",
    "address",
    "full_address",
    "customer_address",
    "delivery_address",
    "ship_to_address",
    "billing_address",
)
CUSTOMER_ID_ALIASES = ("customer_id", "cust_id", "account_id", "client_id", "id")
LINE1_ALIASES = ("address_line_1", "addr_line1", "addr_line_1", "line1", "addr1", "building", "flat")
LINE2_ALIASES = ("address_line_2", "addr_line2", "addr_line_2", "line2", "addr2", "street", "road")
CITY_ALIASES = ("city", "town", "post_town", "locality")
POSTCODE_ALIASES = ("postcode", "post_code", "zip", "postal_code")
COUNTY_ALIASES = ("county", "state", "region")


@dataclass
class VendorRow:
    customer_id: str
    vendor_address: str
    source_columns: dict[str, str] = field(default_factory=dict)


@dataclass
class ImportPreview:
    format_detected: str
    column_mapping: dict[str, str | list[str]]
    sample_rows: list[VendorRow]
    total_rows: int
    header_row: int = 1


def _norm_header(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_")


def _is_blank_row(values: list[str]) -> bool:
    return not any((v or "").strip() for v in values)


def _score_header_row(values: list[str]) -> int:
    normalized = [_norm_header(v) for v in values if (v or "").strip()]
    score = 0
    if any(n in ADDRESS_ALIASES for n in normalized):
        score += 10
    if any(n in CUSTOMER_ID_ALIASES for n in normalized):
        score += 5
    if len(normalized) >= 2:
        score += 2
    # Penalize rows that look like data (starts with digit in first cell)
    if values and (values[0] or "").strip().isdigit():
        score -= 8
    return score


def _normalize_fieldnames(raw_headers: list[str]) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(raw_headers):
        name = (raw or "").strip()
        if not name:
            name = f"_col_{i}"
        base = name
        if base in seen:
            seen[base] += 1
            name = f"{base}_{seen[base]}"
        else:
            seen[base] = 0
        names.append(name)
    return names


def _read_data_rows(file_obj: TextIO) -> tuple[list[str], list[dict[str, str]], int]:
    """
    Skip leading blank rows and detect the real header row.
    Handles files like address_validation_set1.CSV with an empty first line.
    """
    content = file_obj.read()
    if content.startswith("\ufeff"):
        content = content.lstrip("\ufeff")

    all_rows = list(csv.reader(io.StringIO(content)))
    while all_rows and _is_blank_row(all_rows[0]):
        all_rows.pop(0)

    if not all_rows:
        raise ValueError("CSV is empty")

    header_idx = 0
    best_score = -999
    for i in range(min(8, len(all_rows))):
        if _is_blank_row(all_rows[i]):
            continue
        score = _score_header_row(all_rows[i])
        if score > best_score:
            best_score = score
            header_idx = i

    # If no header keywords found, treat first non-blank row as header when followed by data
    if best_score < 5 and header_idx + 1 < len(all_rows):
        first, second = all_rows[header_idx], all_rows[header_idx + 1]
        if not _is_blank_row(second) and (second[0] or "").strip().isdigit():
            pass  # first row is header, second is numeric id — keep header_idx

    fieldnames = _normalize_fieldnames(all_rows[header_idx])
    data_rows: list[dict[str, str]] = []

    for raw in all_rows[header_idx + 1 :]:
        if _is_blank_row(raw):
            continue
        padded = raw + [""] * max(0, len(fieldnames) - len(raw))
        data_rows.append(dict(zip(fieldnames, padded[: len(fieldnames)])))

    return fieldnames, data_rows, header_idx + 1


def _pick(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_norm_header(h): h for h in headers if (h or "").strip()}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def detect_mapping(headers: list[str]) -> tuple[str, dict[str, str | list[str]]]:
    usable = [h for h in headers if (h or "").strip() and not h.startswith("_col_")]
    single = _pick(headers, ADDRESS_ALIASES)
    if single:
        mapping: dict[str, str | list[str]] = {"address": single}
        cid = _pick(headers, CUSTOMER_ID_ALIASES)
        if cid:
            mapping["customer_id"] = cid
        return "single_line", mapping

    line1 = _pick(headers, LINE1_ALIASES)
    line2 = _pick(headers, LINE2_ALIASES)
    city = _pick(headers, CITY_ALIASES)
    postcode = _pick(headers, POSTCODE_ALIASES)

    if line1 or line2 or city or postcode:
        mapping = {}
        if line1:
            mapping["line_1"] = line1
        if line2:
            mapping["line_2"] = line2
        if city:
            mapping["city"] = city
        if postcode:
            mapping["postcode"] = postcode
        cid = _pick(headers, CUSTOMER_ID_ALIASES)
        if cid:
            mapping["customer_id"] = cid
        county = _pick(headers, COUNTY_ALIASES)
        if county:
            mapping["county"] = county
        return "multi_column", mapping

    cid = _pick(headers, CUSTOMER_ID_ALIASES)
    others = [h for h in headers if h != cid and (h or "").strip() and not h.startswith("_col_")]
    if others:
        mapping = {"parts": others}
        if cid:
            mapping["customer_id"] = cid
        return "joined_columns", mapping

    # Last resort: first two named columns as id + address
    if len(usable) >= 2:
        return "single_line", {"customer_id": usable[0], "address": usable[1]}

    raise ValueError(f"Could not detect address columns in headers: {headers}")


def _compose_address(row: dict[str, str], mapping: dict[str, Any], fmt: str) -> str:
    if fmt == "single_line":
        return (row.get(mapping["address"]) or "").strip()

    if fmt == "multi_column":
        parts = []
        for key in ("line_1", "line_2", "city", "county", "postcode"):
            col = mapping.get(key)
            if col and row.get(col, "").strip():
                parts.append(row[col].strip())
        return ", ".join(parts)

    if fmt == "joined_columns":
        parts = [row.get(c, "").strip() for c in mapping.get("parts", [])]
        return ", ".join(p for p in parts if p)

    raise ValueError(f"Unknown format: {fmt}")


def load_mapping_config(path: Path = DEFAULT_MAPPING_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_csv_rows(
    file_obj: TextIO,
    mapping_override: dict[str, Any] | None = None,
    limit: int | None = None,
) -> ImportPreview:
    headers, data_rows, header_row_num = _read_data_rows(file_obj)
    fmt, auto_mapping = detect_mapping(headers)
    mapping = dict(auto_mapping)
    if mapping_override:
        mapping.update(mapping_override)

    rows: list[VendorRow] = []
    total = len(data_rows)
    for row in data_rows:
        if limit and len(rows) >= limit:
            break

        customer_id = ""
        cid_col = mapping.get("customer_id")
        if cid_col and isinstance(cid_col, str):
            customer_id = (row.get(cid_col) or "").strip()

        vendor_address = _compose_address(row, mapping, fmt)
        if not vendor_address:
            continue

        source_cols = {
            k: (row.get(v) or "")
            for k, v in mapping.items()
            if isinstance(v, str)
        }
        rows.append(
            VendorRow(
                customer_id=customer_id,
                vendor_address=vendor_address,
                source_columns=source_cols,
            )
        )

    return ImportPreview(
        format_detected=fmt,
        column_mapping=mapping,
        sample_rows=rows,
        total_rows=total,
        header_row=header_row_num,
    )
