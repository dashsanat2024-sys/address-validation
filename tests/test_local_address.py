"""Tests for local address index and tiered validation."""

from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.local_address_store import (
    clear_cache,
    is_local_index_available,
    lookup,
    record_count,
)
from address_validation.local_validator import LocalFirstValidator
from address_validation.validator_factory import get_validator


@pytest.fixture()
def tiny_index(tmp_path, monkeypatch):
    path = tmp_path / "uk_addresses.json.gz"
    rows = [
        {"pc": "CV1 2NF", "n": "8", "s": "Gulson Road", "u": "Apartment 7", "b": "Elliot's Yard", "city": "Coventry", "dist": "Coventry", "src": "test"},
        {"pc": "DE24 8HP", "n": "", "s": "Millennium Way", "u": "Unit 3", "b": "Stadium Business Court", "city": "Derby", "dist": "Derby", "src": "test"},
        {"pc": "SW1A 1AA", "city": "Westminster", "dist": "Westminster", "region": "London", "src": "test"},
    ]
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    monkeypatch.setenv("LOCAL_ADDRESS_INDEX", str(path))
    clear_cache()
    yield path
    clear_cache()


def test_index_loads(tiny_index):
    assert is_local_index_available()
    assert record_count() == 3


def test_lookup_high_confidence(tiny_index):
    match = lookup("8 Gulson Road Apartment 7 Elliot's Yard Coventry CV1 2NF", "CV1 2NF")
    assert match is not None
    assert match.address_confident
    assert match.record.street == "Gulson Road"


def test_lookup_unknown_postcode(tiny_index):
    match = lookup("1 High Street Nowhere ZZ99 9ZZ", "ZZ99 9ZZ")
    assert match is not None
    assert match.match_reason == "postcode_not_in_local_index"
    assert not match.postcode_confident


def test_street_first_missing_postcode(tiny_index):
    match = lookup("8 Gulson Road Apartment 7 Elliot's Yard Coventry")
    assert match is not None
    assert match.address_confident
    assert match.record.postcode == "CV1 2NF"
    assert match.match_reason.startswith("street_first")


def test_street_first_wrong_postcode(tiny_index):
    match = lookup("8 Gulson Road Apartment 7 Elliot's Yard Coventry CV1 2AA", "CV1 2AA")
    assert match is not None
    assert match.record.postcode == "CV1 2NF"
    assert match.match_reason == "street_first_over_postcode"


def test_street_first_validator_missing_postcode(tiny_index, monkeypatch):
    monkeypatch.setenv("LOCAL_SKIP_POSTCODES_IO", "1")
    validator = LocalFirstValidator()
    result = validator.cleanse_address(
        "8 Gulson Road Apartment 7 Elliot's Yard Coventry",
        postcode_hint=None,
    )
    assert result.valid
    assert result.postcode == "CV1 2NF"
    assert result.raw_result.get("validation_tier") == "street_first_resolved"


def test_street_first_after_postcodes_reject(tiny_index, monkeypatch):
    monkeypatch.setenv("LOCAL_SKIP_POSTCODES_IO", "0")
    validator = LocalFirstValidator()

    class FakePostcodes:
        def validate_postcode(self, postcode):
            from address_validation.postcodes_io import PostcodeValidation
            return PostcodeValidation(
                valid=False,
                postcode=postcode,
                error="Invalid UK postcode",
            )

    validator._postcodes = FakePostcodes()
    result = validator.cleanse_address(
        "8 Gulson Road Apartment 7 Elliot's Yard Coventry CV1 2AA",
        postcode_hint="CV1 2AA",
    )
    assert result.valid
    assert result.postcode == "CV1 2NF"
    assert result.raw_result.get("validation_tier") in {
        "street_first_after_postcodes_reject",
        "street_first_resolved",
    }


def test_local_validator_skips_postcodes_io_when_confident(tiny_index, monkeypatch):
    monkeypatch.setenv("LOCAL_SKIP_POSTCODES_IO", "1")
    validator = LocalFirstValidator()
    result = validator.cleanse_address(
        "8 Gulson Road Apartment 7 Elliot's Yard Coventry CV1 2NF",
        postcode_hint="CV1 2NF",
    )
    assert result.valid
    assert result.source == "local_index"
    assert result.street_level_validated
    assert result.raw_result.get("postcodes_io_skipped") is True


def test_local_validator_falls_back_to_postcodes_io(tiny_index, monkeypatch):
    monkeypatch.setenv("LOCAL_SKIP_POSTCODES_IO", "0")
    validator = LocalFirstValidator()

    class FakePostcodes:
        def validate_postcode(self, postcode):
            from address_validation.postcodes_io import PostcodeValidation
            return PostcodeValidation(
                valid=True,
                postcode=postcode,
                admin_district="Test District",
                region="Test Region",
                country="England",
                raw_result={"postcode": postcode},
            )

    validator._postcodes = FakePostcodes()
    result = validator.cleanse_address("Random Street ZZ99 9ZZ", postcode_hint="ZZ99 9ZZ")
    assert result.raw_result.get("validation_tier") == "postcodes_io_fallback"


def test_factory_uses_local_when_index_present(tiny_index, monkeypatch):
    monkeypatch.setenv("ADDRESS_VALIDATOR", "postcodes_io")
    monkeypatch.setenv("LOCAL_ADDRESS_AUTO", "1")
    validator = get_validator()
    assert isinstance(validator, LocalFirstValidator)
