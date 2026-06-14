import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.export import write_db_csv, write_client_csv


def test_export_db_csv_includes_audit_columns():
    results = [
        {
            "success": True,
            "customer_id": "1",
            "vendor_address": "10 High St, London, SW1A 1AA",
            "validator": "postcodes_io",
            "normalized_address": {
                "street_house_number": "10",
                "street_4": "High Street",
                "other_city": "London",
                "postal_code": "SW1A 1AA",
                "postal_code_city": "SW1A 1AA LONDON",
                "country": "GB",
                "time_zone": "GMTUK",
            },
        },
        {
            "success": False,
            "customer_id": "2",
            "vendor_address": "invalid",
            "validator": "postcodes_io",
            "errors": ["No UK postcode found"],
            "normalized_address": {},
        },
    ]
    buf = io.StringIO()
    stats = write_db_csv(results, buf)
    text = buf.getvalue()
    assert stats["total"] == 2
    assert stats["successful"] == 1
    assert stats["failed"] == 1
    assert "Processing Status" in text
    assert "Vendor Address" in text
    assert "SUCCESS" in text
    assert "FAILED" in text


def test_export_client_csv_success_only():
    results = [
        {
            "success": True,
            "customer_id": "1",
            "normalized_address": {
                "street_4": "High Street",
                "postal_code": "SW1A 1AA",
                "country": "GB",
            },
        },
        {"success": False, "customer_id": "2", "normalized_address": {}},
    ]
    buf = io.StringIO()
    count = write_client_csv(results, buf)
    assert count == 1
    assert "High Street" in buf.getvalue()
