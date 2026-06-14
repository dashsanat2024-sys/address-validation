import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.vendor_import import detect_mapping, parse_csv_rows

SINGLE = "input_address,customer_id\n\"10 high st london sw1a1aa\",C1\n"
MULTI = "customer_id,addr_line1,addr_line2,town,post_code\nV1,Flat 2,10 High St,London,SW1A1AA\n"

# Mimics address_validation_set1.CSV — blank first row, headers on row 2
SET1 = """\
,,,,,,
Customer ID,Address,,,,,
1,"Avalon Cottage, 25C High Street,Pershore,WR10 1AA",,,,,
2,"Flat 14 Flat 3, 51-53 Musters Road, West Bridgford, NG2 7QH, GB",,,,,
"""


def test_detect_single_line():
    fmt, mapping = detect_mapping(["input_address", "customer_id"])
    assert fmt == "single_line"
    assert mapping["address"] == "input_address"


def test_detect_multi_column():
    fmt, mapping = detect_mapping(["addr_line1", "addr_line2", "town", "post_code", "customer_id"])
    assert fmt == "multi_column"
    assert mapping["line_1"] == "addr_line1"
    assert mapping["postcode"] == "post_code"


def test_parse_single_line_csv():
    preview = parse_csv_rows(io.StringIO(SINGLE))
    assert preview.total_rows == 1
    assert preview.sample_rows[0].vendor_address == "10 high st london sw1a1aa"


def test_parse_multi_column_csv():
    preview = parse_csv_rows(io.StringIO(MULTI))
    assert preview.format_detected == "multi_column"
    assert "Flat 2" in preview.sample_rows[0].vendor_address
    assert "SW1A1AA" in preview.sample_rows[0].vendor_address


def test_parse_blank_header_row_csv():
    preview = parse_csv_rows(io.StringIO(SET1))
    assert preview.format_detected == "single_line"
    assert preview.column_mapping["address"] == "Address"
    assert preview.column_mapping["customer_id"] == "Customer ID"
    assert preview.total_rows == 2
    assert len(preview.sample_rows) == 2
    assert preview.sample_rows[0].customer_id == "1"
    assert "Avalon Cottage" in preview.sample_rows[0].vendor_address
    assert preview.sample_rows[1].customer_id == "2"
    assert "Musters Road" in preview.sample_rows[1].vendor_address


def test_parse_real_set1_file():
    path = "/Users/sanat/Downloads/address_validation_set1.CSV"
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8-sig") as fh:
        preview = parse_csv_rows(fh)
    assert preview.format_detected == "single_line"
    assert preview.total_rows == 10
    assert len(preview.sample_rows) == 10
    assert preview.sample_rows[0].customer_id == "1"
