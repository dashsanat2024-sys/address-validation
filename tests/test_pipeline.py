"""Tests for optional validation bypass and LLM-only context."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from address_validation.llm_validation import build_llm_only_context, extract_llm_validation_meta
from address_validation.pipeline import AddressPipeline
from address_validation.preprocess import preprocess
from address_validation.schema import is_valid_uk_postcode_format


class TestPostcodeFormat(unittest.TestCase):
    def test_valid_postcodes(self):
        self.assertTrue(is_valid_uk_postcode_format("SW1A 1AA"))
        self.assertTrue(is_valid_uk_postcode_format("sw1a1aa"))

    def test_invalid_postcodes(self):
        self.assertFalse(is_valid_uk_postcode_format(""))
        self.assertFalse(is_valid_uk_postcode_format("NOT A POSTCODE"))


class TestLlmOnlyContext(unittest.TestCase):
    def test_build_context_with_postcode(self):
        pre = preprocess("10 High Street, London SW1A 1AA")
        ctx = build_llm_only_context(pre)
        self.assertTrue(ctx["external_validation_skipped"])
        self.assertEqual(ctx["source"], "llm_only")
        self.assertEqual(ctx["extracted_postcode_hint"], "SW1A 1AA")
        self.assertTrue(ctx["postcode_format_ok"])

    def test_extract_llm_meta(self):
        payload = {
            "llm_validation": {"postcode_format_valid": True, "postcode_plausible": False},
            "postal_code": "SW1A 1AA",
            "other_city": "London",
        }
        meta = extract_llm_validation_meta(payload)
        self.assertEqual(meta["postcode_plausible"], False)
        self.assertNotIn("llm_validation", payload)


class TestPipelineSkipValidation(unittest.TestCase):
    @patch.object(AddressPipeline, "__init__", lambda self, **kwargs: None)
    def test_skip_validation_rule_based(self):
        pipe = AddressPipeline.__new__(AddressPipeline)
        pipe.skip_llm = True
        pipe.skip_validation = True
        pipe.model = "qwen3:8b"
        pipe._validator_name = "llm_only"
        pipe.validator = MagicMock()
        pipe.normalizer = MagicMock()

        result = AddressPipeline.run(
            pipe,
            "10 Downing Street, London SW1A 2AA",
            customer_id="C1",
        )
        self.assertTrue(result.skip_validation)
        self.assertTrue(result.success)
        self.assertEqual(result.normalized_address.get("postal_code"), "SW1A 2AA")
        self.assertIn("External validation bypassed", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()
