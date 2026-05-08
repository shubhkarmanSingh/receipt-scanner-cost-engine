"""Unit tests for receipt_extractor.py — JSON parsing, validation, and prompt building.

These tests do NOT call the Claude API. They test the JSON extraction,
validation, and dynamic prompt building code.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from receipt_extractor import _validate_receipt, _build_extraction_prompt


# ── _validate_receipt tests ──

class TestValidateReceipt:
    def test_valid_receipt(self):
        data = {
            "merchant": "Restaurant Depot",
            "items": [{"name": "Pork", "quantity": 10, "total_price": 20.0}],
            "total": 20.0,
        }
        _validate_receipt(data)  # Should not raise

    def test_missing_merchant(self):
        data = {
            "items": [{"name": "Pork", "quantity": 10, "total_price": 20.0}],
            "total": 20.0,
        }
        with pytest.raises(ValueError, match="Missing required field: merchant"):
            _validate_receipt(data)

    def test_missing_items(self):
        data = {"merchant": "Store", "total": 10.0}
        with pytest.raises(ValueError, match="Missing required field: items"):
            _validate_receipt(data)

    def test_missing_total(self):
        data = {
            "merchant": "Store",
            "items": [{"name": "X", "quantity": 1, "total_price": 5.0}],
        }
        with pytest.raises(ValueError, match="Missing required field: total"):
            _validate_receipt(data)

    def test_empty_items_list(self):
        data = {"merchant": "Store", "items": [], "total": 0}
        with pytest.raises(ValueError, match="at least one item"):
            _validate_receipt(data)

    def test_item_missing_name(self):
        data = {
            "merchant": "Store",
            "items": [{"quantity": 1, "total_price": 5.0}],
            "total": 5.0,
        }
        with pytest.raises(ValueError, match="Item 0 missing required field: name"):
            _validate_receipt(data)

    def test_item_missing_quantity(self):
        data = {
            "merchant": "Store",
            "items": [{"name": "X", "total_price": 5.0}],
            "total": 5.0,
        }
        with pytest.raises(ValueError, match="Item 0 missing required field: quantity"):
            _validate_receipt(data)

    def test_item_missing_total_price(self):
        data = {
            "merchant": "Store",
            "items": [{"name": "X", "quantity": 1}],
            "total": 5.0,
        }
        with pytest.raises(ValueError, match="Item 0 missing required field: total_price"):
            _validate_receipt(data)


# ── JSON bracket extraction tests ──

class TestJsonBracketExtraction:
    """Test the JSON extraction logic that runs on Claude's response text."""

    def _extract_json(self, response_text: str) -> str:
        """Replicate the bracket-counting logic from receipt_extractor.py."""
        import json

        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
        response_text = response_text.strip()
        if response_text.endswith("```"):
            response_text = response_text.rsplit("```", 1)[0]
        response_text = response_text.strip()

        start = response_text.find("{")
        if start != -1:
            depth = 0
            found_end = False
            for i, ch in enumerate(response_text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        response_text = response_text[start:i + 1]
                        found_end = True
                        break
            if not found_end:
                raise ValueError(f"Unmatched braces (depth={depth})")

        return json.loads(response_text)

    def test_clean_json(self):
        result = self._extract_json('{"merchant": "Store", "items": [], "total": 0}')
        assert result["merchant"] == "Store"

    def test_json_with_markdown_fences(self):
        text = '```json\n{"merchant": "Store", "items": [], "total": 0}\n```'
        result = self._extract_json(text)
        assert result["merchant"] == "Store"

    def test_json_with_text_before(self):
        text = 'Here is the data:\n{"merchant": "Store", "items": [], "total": 0}'
        result = self._extract_json(text)
        assert result["merchant"] == "Store"

    def test_json_with_nested_objects(self):
        text = '{"merchant": "Store", "items": [{"name": "X", "nested": {"a": 1}}], "total": 5}'
        result = self._extract_json(text)
        assert result["items"][0]["nested"]["a"] == 1

    def test_no_json_raises(self):
        with pytest.raises(Exception):
            self._extract_json("No JSON here at all")

    def test_unbalanced_braces_raises(self):
        with pytest.raises(ValueError, match="Unmatched braces"):
            self._extract_json('{"merchant": "Store", "items": [')


# ── Dynamic prompt building tests ──

class TestBuildExtractionPrompt:
    def test_includes_business_name(self):
        config = {
            "business": {"name": "My Bakery", "industry": "bakery"},
            "extraction": {"prompt_context": "", "item_term": "ingredient", "receipt_rules": []},
        }
        prompt = _build_extraction_prompt(config)
        assert "My Bakery" in prompt
        assert "bakery" in prompt

    def test_includes_prompt_context(self):
        config = {
            "business": {"name": "Test", "industry": "retail"},
            "extraction": {
                "prompt_context": "They buy from Costco and Walmart.",
                "item_term": "product",
                "receipt_rules": [],
            },
        }
        prompt = _build_extraction_prompt(config)
        assert "Costco and Walmart" in prompt

    def test_includes_item_term(self):
        config = {
            "business": {"name": "Test", "industry": "service"},
            "extraction": {"prompt_context": "", "item_term": "supply", "receipt_rules": []},
        }
        prompt = _build_extraction_prompt(config)
        assert "supply" in prompt

    def test_includes_custom_rules(self):
        config = {
            "business": {"name": "Test", "industry": "general"},
            "extraction": {
                "prompt_context": "",
                "item_term": "item",
                "receipt_rules": ["Always note the brand name", "Track lot numbers"],
            },
        }
        prompt = _build_extraction_prompt(config)
        assert "Always note the brand name" in prompt
        assert "Track lot numbers" in prompt

    def test_defaults_for_missing_fields(self):
        config = {"business": {}, "extraction": {}}
        prompt = _build_extraction_prompt(config)
        assert "a business" in prompt  # default name
        assert "item" in prompt  # default item_term

    def test_json_format_present(self):
        config = {
            "business": {"name": "X", "industry": "x"},
            "extraction": {"prompt_context": "", "item_term": "item", "receipt_rules": []},
        }
        prompt = _build_extraction_prompt(config)
        assert '"merchant"' in prompt
        assert '"items"' in prompt
        assert '"total"' in prompt
