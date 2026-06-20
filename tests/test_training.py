"""Tests for training dataset generation (offline)."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.review_store import export_correction_output
from address_validation.training.export import build_training_output, parse_training_output
from address_validation.training.synthetic import SyntheticGenerator


SAMPLE_POSTCODES = [
    {
        "postcode": "CV1 2NF",
        "admin_district": "Coventry",
        "region": "West Midlands",
        "country": "England",
    },
    {
        "postcode": "SW1A 1AA",
        "admin_district": "Westminster",
        "region": "London",
        "country": "England",
    },
    {
        "postcode": "GL50 1UA",
        "admin_district": "Cheltenham",
        "region": "South West",
        "country": "England",
    },
]


def test_build_training_output_has_validation_block():
    out = build_training_output(
        {
            "street_2": "Apartment 7",
            "street_house_number": "8",
            "street_4": "Gulson Road",
            "other_city": "Coventry",
            "postal_code": "CV1 2NF",
        },
        postcode_exists=True,
    )
    assert "llm_validation" in out
    assert out["llm_validation"]["postcode_exists"] is True
    assert out["postal_code_city"] == "CV1 2NF COVENTRY"


def test_export_correction_adds_llm_validation():
    corrected = {
        "street_2": "Flat 2",
        "street_house_number": "10",
        "street_4": "High Street",
        "other_city": "London",
        "postal_code": "SW1A 1AA",
    }
    out = export_correction_output(corrected)
    assert out["llm_validation"]["validation_notes"] == "human_corrected"


def test_synthetic_generator_offline():
    gen = SyntheticGenerator(seed=1, invalid_ratio=0.2, permutations_per_base=5)
    rows = gen.generate(target_count=50, postcode_count=3, postcodes=SAMPLE_POSTCODES)
    assert len(rows) >= 10
    sample = parse_training_output(rows[0]["output"])
    assert "llm_validation" in sample
    assert "street_4" in sample


def test_synthetic_covers_flat_building_street_pattern():
    gen = SyntheticGenerator(seed=99, permutations_per_base=6)
    rows = gen.generate(target_count=200, postcode_count=3, postcodes=SAMPLE_POSTCODES)
    inputs = [r["input"].upper() for r in rows]
    assert any(
        kw in i
        for i in inputs
        for kw in ("APARTMENT", "FLAT", "SUITE", "UNIT", "ROOM", "HOUSE", "LODGE", "YARD")
    )
