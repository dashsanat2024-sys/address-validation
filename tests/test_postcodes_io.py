import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.postcodes_io import PostcodesIOClient


def test_valid_postcode_lookup():
    client = PostcodesIOClient()
    result = client.validate_postcode("SW1A1AA")
    assert result.valid is True
    assert result.postcode == "SW1A 1AA"
    assert result.region == "London"


def test_invalid_postcode():
    client = PostcodesIOClient()
    result = client.validate_postcode("NOTAPC")
    assert result.valid is False
