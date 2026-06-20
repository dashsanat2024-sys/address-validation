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


def test_multi_line_flat_building_street():
    """Flat + building + numbered street + city (common UK vendor format)."""
    addr = StandardAddress.from_vendor_text(
        "FLAT 3, BURFORD LODGE, 5 MONTPELLIER PARADE, CHELTENHAM"
    )
    assert addr.street_2 == "FLAT 3"
    assert addr.street_3 == "BURFORD LODGE"
    assert addr.street_house_number == "5"
    assert addr.street_4 == "Montpellier Parade"
    assert addr.other_city == "CHELTENHAM"


def test_space_separated_apartment_building_street():
    addr = StandardAddress.from_vendor_text(
        "Apartment 7 Elliot's Yard 8 Gulson Road Coventry"
    )
    assert addr.street_2 == "Apartment 7"
    assert addr.street_3 == "Elliot's Yard"
    assert addr.street_house_number == "8"
    assert addr.street_4 == "Gulson Road"
    assert addr.other_city == "Coventry"


def test_space_separated_reversed_street_number_unit():
    addr = StandardAddress.from_vendor_text(
        "Gulson Road 8 Apartment 7 Elliot's Yard Coventry"
    )
    assert addr.street_2 == "Apartment 7"
    assert addr.street_3 == "Elliot's Yard"
    assert addr.street_house_number == "8"
    assert addr.street_4 == "Gulson Road"
    assert addr.other_city == "Coventry"


def test_postal_code_city_helper():
    assert format_postal_code_city("sw1a1aa", "london") == "SW1A 1AA LONDON"


def test_business_comma_org_unit_address():
    """Industrial estate: company co, unit, court, way, park, city."""
    addr = StandardAddress.from_vendor_text(
        "COMEX 2000 UNIT 3 STADIUM BUSINESS COURT, MILLENNIUM WAY,PRIDE PARK,DERBY"
    )
    assert addr.co == "COMEX 2000"
    assert addr.street_2 == "UNIT 3"
    assert addr.street_3 == "Stadium Business Court"
    assert addr.street_4 == "Pride Park"
    assert addr.street_5 == "Millennium Way"
    assert addr.district == "DERBY"
    assert addr.other_city == "DERBY"


def test_postal_code_city_object_from_llm():
    addr = StandardAddress.from_llm_json(
        {
            "street_house_number": "8",
            "street_4": "Gulson Road",
            "other_city": "coventry",
            "postal_code": "CV1 2nf",
            "postal_code_city": {"postal_code": "CV1 2nf", "city": "coventry"},
        }
    )
    assert addr.postal_code == "CV1 2NF"
    assert addr.postal_code_city == "CV1 2NF COVENTRY"
    assert addr.other_city == "coventry"
