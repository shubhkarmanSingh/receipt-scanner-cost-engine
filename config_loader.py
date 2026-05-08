"""
config_loader.py — Load and validate the business configuration.

The business config drives all business-specific behavior: extraction prompts,
item mapping, cost calculations, sheet layout, and more.
"""

import json
import os

_cached_config: dict | None = None
_cached_path: str | None = None

_REQUIRED_SECTIONS = ["business", "items", "products", "overhead"]


def load_business_config(config_path: str | None = None) -> dict:
    """Load the business configuration from JSON.

    Args:
        config_path: Path to business_config.json. Defaults to
            BUSINESS_CONFIG_PATH env var, then config/business_config.json.

    Returns:
        The parsed configuration dict.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        ValueError: If required sections are missing.
    """
    global _cached_config, _cached_path

    if config_path is None:
        config_path = os.environ.get(
            "BUSINESS_CONFIG_PATH",
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "config", "business_config.json"),
        )

    if _cached_config is not None and _cached_path == config_path:
        return _cached_config

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Business config not found: {config_path}. "
            "Run 'python setup_wizard.py' to create one, or set BUSINESS_CONFIG_PATH."
        )

    with open(config_path) as f:
        config = json.load(f)

    _validate_config(config, config_path)

    _cached_config = config
    _cached_path = config_path
    return config


def _validate_config(config: dict, path: str) -> None:
    """Validate that the config has all required sections and fields."""
    for section in _REQUIRED_SECTIONS:
        if section not in config:
            raise ValueError(
                f"Business config at {path} is missing required section: '{section}'"
            )

    business = config["business"]
    if not business.get("name"):
        raise ValueError("business.name is required in config")

    items = config["items"]
    if "aliases" not in items:
        raise ValueError("items.aliases is required in config (can be empty dict for new businesses)")

    products = config["products"]
    if not products.get("unit_name"):
        raise ValueError("products.unit_name is required in config (e.g. 'roll', 'unit', 'item')")


def clear_cache() -> None:
    """Clear the cached config. Useful for testing."""
    global _cached_config, _cached_path
    _cached_config = None
    _cached_path = None
