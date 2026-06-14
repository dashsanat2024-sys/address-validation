import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.schema import StandardAddress, format_postal_code_city


def test_client_format_fields():
    addr = StandardAddress(
        customer_id="C1",
        street_2="Flat 2",
        street_house_number="10",
        street_4="High Street",
        district="Westminster",
        other_city="London",
        postal_code="SW1A 1AA",
    )
    data = addr.to_storage_dict()
    assert data["street_2"] == "Flat 2"
    assert data["postal_code"] == "SW1A 1AA"
    assert data["postal_code_city"] == "SW1A 1AA LONDON"
    assert data["country"] == "GB"
    assert data["time_zone"] == "GMTUK"


def test_legacy_field_migration():
    addr = StandardAddress.from_llm_json(
        {
            "address_line_1": "Flat 2",
            "address_line_2": "10 High Street",
            "city": "London",
            "county": "Westminster",
            "postcode": "SW1A 1AA",
        }
    )
    assert addr.street_2 == "Flat 2"
    assert addr.street_house_number == "10"
    assert addr.street_4 == "High Street"
    assert addr.other_city == "London"
    assert addr.district == "Westminster"


def test_postal_code_city_helper():
    assert format_postal_code_city("sw1a1aa", "london") == "SW1A 1AA LONDON"
