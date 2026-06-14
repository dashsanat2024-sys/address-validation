import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.preprocess import extract_postcode, preprocess


def test_extract_postcode_lowercase():
    assert extract_postcode("10 high st london sw1a1aa") == "SW1A 1AA"


def test_preprocess_removes_postcode():
    result = preprocess("Flat 2, 10 high street, london, sw1a1aa")
    assert result.extracted_postcode == "SW1A 1AA"
    assert "sw1a" not in result.remainder_without_postcode.lower()
