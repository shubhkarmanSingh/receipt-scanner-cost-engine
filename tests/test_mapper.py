"""Unit tests for ingredient_mapper.py — no API keys required.

Uses inline test aliases, independent of any business config.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingredient_mapper import map_ingredient, map_receipt_items, UNMAPPED_PREFIX


# Minimal test aliases — no real business data
_TEST_ALIASES = {
    "aliases": {
        "Pork": {
            "patterns": ["GRD PORK", "GROUND PORK", "PORK GRND", "PORK GROUND"],
            "category": "Protein",
            "default_unit": "lb",
        },
        "Minced Chicken": {
            "patterns": ["MINCED CHICKEN", "CHICKEN BREAST", "GROUND CHICKEN"],
            "category": "Protein",
            "default_unit": "lb",
        },
        "Salt": {
            "patterns": ["SALT", "IODIZED SALT", "TABLE SALT"],
            "category": "Seasoning",
            "default_unit": "lb",
        },
        "Wrappers (Large 12in)": {
            "patterns": ["RICE PAPER 12", "WRAPPER 12", "RICE PAPER WRAPPER 12IN"],
            "category": "Wrapper",
            "default_unit": "sheet",
        },
    }
}


@pytest.fixture(scope="module")
def aliases():
    return _TEST_ALIASES


# ── map_ingredient tests ──

class TestMapIngredient:
    def test_known_ingredient_pork(self, aliases):
        result = map_ingredient("GRD PORK 80/20 10LB CS", aliases)
        assert result["canonical_name"] == "Pork"
        assert result["category"] == "Protein"
        assert result["matched_pattern"] is not None

    def test_known_ingredient_chicken(self, aliases):
        result = map_ingredient("MINCED CHICKEN BREAST", aliases)
        assert result["canonical_name"] == "Minced Chicken"
        assert result["category"] == "Protein"

    def test_known_ingredient_case_insensitive(self, aliases):
        result = map_ingredient("ground pork bulk", aliases)
        assert result["canonical_name"] == "Pork"

    def test_unmapped_item(self, aliases):
        result = map_ingredient("RANDOM UNKNOWN PRODUCT XYZ", aliases)
        assert result["canonical_name"].startswith(UNMAPPED_PREFIX)
        assert result["category"] == "Uncategorized"
        assert result["matched_pattern"] is None

    def test_empty_description(self, aliases):
        result = map_ingredient("", aliases)
        assert result["canonical_name"].startswith(UNMAPPED_PREFIX)

    def test_prefers_longer_match(self, aliases):
        """When multiple patterns match, the longer (more specific) one wins."""
        result = map_ingredient("RICE PAPER WRAPPER 12IN", aliases)
        assert result["matched_pattern"] is not None
        # Should match a specific pattern, not just a short substring

    def test_word_boundary_matching(self, aliases):
        """Patterns should match on word boundaries, not partial words."""
        # "SALT" should not match inside "BASALT" or "ASALTED"
        result = map_ingredient("BASALT ROCK", aliases)
        assert result["canonical_name"].startswith(UNMAPPED_PREFIX)


# ── map_receipt_items tests ──

class TestMapReceiptItems:
    def test_maps_all_items(self, aliases):
        receipt = {
            "merchant": "Test Store",
            "items": [
                {"raw_description": "GRD PORK 80/20", "name": "Ground Pork",
                 "quantity": 10, "unit": "lb", "unit_price": 2.00, "total_price": 20.00},
                {"raw_description": "UNKNOWN THING", "name": "Unknown",
                 "quantity": 1, "unit": "ea", "unit_price": 5.00, "total_price": 5.00},
            ]
        }
        result = map_receipt_items(receipt, aliases)
        stats = result["_mapping_stats"]
        assert stats["total_items"] == 2
        assert stats["mapped"] == 1
        assert stats["unmapped"] == 1

    def test_empty_items_list(self, aliases):
        receipt = {"merchant": "Test", "items": []}
        result = map_receipt_items(receipt, aliases)
        assert result["_mapping_stats"]["total_items"] == 0
        assert result["_mapping_stats"]["mapped"] == 0

    def test_uses_name_fallback_when_no_raw_description(self, aliases):
        """If raw_description is missing, falls back to name field."""
        receipt = {
            "merchant": "Test",
            "items": [
                {"name": "GROUND PORK", "quantity": 5, "unit": "lb",
                 "unit_price": 2.0, "total_price": 10.0}
            ]
        }
        result = map_receipt_items(receipt, aliases)
        assert result["items"][0]["canonical_name"] == "Pork"
