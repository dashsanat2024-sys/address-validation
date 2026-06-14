"""Export normalized addresses to client-format CSV ready for DB import."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

CLIENT_EXPORT_COLUMNS = [
    "customer_id",
    "co",
    "street_2",
    "street_3",
    "street_house_number",
    "street_4",
    "street_5",
    "district",
    "other_city",
    "postal_code_city",
    "country",
    "time_zone",
    "transportation_zone",
    "reg_struct_grp",
    "undeliverable",
    "po_box_address",
    "po_box",
    "postal_code",
]

CLIENT_EXPORT_HEADERS = [
    "Customer ID",
    "c/o",
    "Street 2",
    "Street 3",
    "Street/House Number",
    "Street 4",
    "Street 5",
    "District",
    "Other City",
    "Postal Code/City",
    "Country",
    "Time Zone",
    "Transportation Zone",
    "Reg. Struct. Grp.",
    "Undeliverable",
    "PO Box Address",
    "PO Box",
    "Postal Code",
]

# Audit columns appended for staging / traceability (exclude when loading to production table)
AUDIT_COLUMNS = ["processing_status", "vendor_address", "error_message", "validator_used"]
AUDIT_HEADERS = ["Processing Status", "Vendor Address", "Error Message", "Validator Used"]

DB_EXPORT_COLUMNS = CLIENT_EXPORT_COLUMNS + AUDIT_COLUMNS
DB_EXPORT_HEADERS = CLIENT_EXPORT_HEADERS + AUDIT_HEADERS


def result_to_db_row(result: dict[str, Any]) -> dict[str, str]:
    normalized = result.get("normalized_address") or {}
    row = {col: str(normalized.get(col, "")) for col in CLIENT_EXPORT_COLUMNS}
    row["customer_id"] = row["customer_id"] or str(result.get("customer_id", ""))
    row["processing_status"] = "SUCCESS" if result.get("success") else "FAILED"
    row["vendor_address"] = str(result.get("vendor_address", ""))
    errors = result.get("errors") or []
    row["error_message"] = "; ".join(errors) if errors else ""
    row["validator_used"] = str(result.get("validator", ""))
    return row


def results_to_db_rows(results: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    return [result_to_db_row(r) for r in results]


def write_db_csv(results: Iterable[dict[str, Any]], file_obj: io.TextIOBase) -> dict[str, int]:
    rows = results_to_db_rows(results)
    writer = csv.DictWriter(file_obj, fieldnames=DB_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writerow(dict(zip(DB_EXPORT_COLUMNS, DB_EXPORT_HEADERS)))
    writer.writerows(rows)
    success = sum(1 for r in rows if r["processing_status"] == "SUCCESS")
    return {"total": len(rows), "successful": success, "failed": len(rows) - success}


def write_client_csv(results: Iterable[dict[str, Any]], file_obj: io.TextIOBase) -> int:
    """Client columns only — successful rows."""
    rows = [r for r in results_to_db_rows(results) if r["processing_status"] == "SUCCESS"]
    writer = csv.DictWriter(file_obj, fieldnames=CLIENT_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writerow(dict(zip(CLIENT_EXPORT_COLUMNS, CLIENT_EXPORT_HEADERS)))
    writer.writerows(rows)
    return len(rows)


def db_csv_string(results: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    write_db_csv(results, buf)
    return buf.getvalue()


def client_csv_string(results: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    write_client_csv(results, buf)
    return buf.getvalue()
