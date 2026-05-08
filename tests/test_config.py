"""Unit tests for config_loader.py — no API keys required."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_loader import load_business_config, clear_cache, _validate_config


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the config cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestLoadBusinessConfig:
    def test_loads_default_config(self):
        config = load_business_config()
        assert "business" in config
        assert "items" in config
        assert "products" in config
        assert "overhead" in config

    def test_business_name_present(self):
        config = load_business_config()
        assert config["business"]["name"]

    def test_aliases_key_present(self):
        config = load_business_config()
        assert "aliases" in config["items"]

    def test_products_have_unit_name(self):
        config = load_business_config()
        assert config["products"]["unit_name"]

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError, match="Business config not found"):
            load_business_config("/nonexistent/path.json")

    def test_caching(self):
        config1 = load_business_config()
        config2 = load_business_config()
        assert config1 is config2

    def test_custom_path(self, tmp_path):
        custom = tmp_path / "test_config.json"
        custom.write_text(json.dumps({
            "business": {"name": "Test Biz"},
            "items": {"aliases": {}},
            "products": {"unit_name": "widget"},
            "overhead": {},
        }))
        config = load_business_config(str(custom))
        assert config["business"]["name"] == "Test Biz"


class TestValidateConfig:
    def test_valid_config(self):
        config = {
            "business": {"name": "Test"},
            "items": {"aliases": {}},
            "products": {"unit_name": "unit"},
            "overhead": {},
        }
        _validate_config(config, "test.json")  # Should not raise

    def test_missing_business(self):
        config = {"items": {"aliases": {}}, "products": {"unit_name": "x"}, "overhead": {}}
        with pytest.raises(ValueError, match="missing required section: 'business'"):
            _validate_config(config, "test.json")

    def test_missing_items(self):
        config = {"business": {"name": "X"}, "products": {"unit_name": "x"}, "overhead": {}}
        with pytest.raises(ValueError, match="missing required section: 'items'"):
            _validate_config(config, "test.json")

    def test_missing_business_name(self):
        config = {
            "business": {},
            "items": {"aliases": {}},
            "products": {"unit_name": "x"},
            "overhead": {},
        }
        with pytest.raises(ValueError, match="business.name is required"):
            _validate_config(config, "test.json")

    def test_missing_unit_name(self):
        config = {
            "business": {"name": "X"},
            "items": {"aliases": {}},
            "products": {},
            "overhead": {},
        }
        with pytest.raises(ValueError, match="products.unit_name is required"):
            _validate_config(config, "test.json")

    def test_missing_aliases_key(self):
        config = {
            "business": {"name": "X"},
            "items": {"categories": []},
            "products": {"unit_name": "x"},
            "overhead": {},
        }
        with pytest.raises(ValueError, match="items.aliases is required"):
            _validate_config(config, "test.json")


class TestTemplates:
    def test_restaurant_template_valid(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "config", "templates", "restaurant.json")
        with open(path) as f:
            config = json.load(f)
        assert config["business"]["industry"] == "restaurant"
        assert "categories" in config["items"]

    def test_retail_template_valid(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "config", "templates", "retail.json")
        with open(path) as f:
            config = json.load(f)
        assert config["business"]["industry"] == "retail"

    def test_service_template_valid(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "config", "templates", "service.json")
        with open(path) as f:
            config = json.load(f)
        assert config["business"]["industry"] == "service"
