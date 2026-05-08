"""
ingredient_mapper.py — Map raw receipt item descriptions to canonical ingredient names.

Uses a fuzzy matching approach against the aliases defined in config/ingredients.json.
When no alias matches, flags the item as "UNMAPPED" for manual review.
"""

import json
import os
import re

# Prefix applied to items that don't match any known ingredient alias
UNMAPPED_PREFIX = "UNMAPPED: "


def load_aliases(config_path: str | None = None) -> dict:
    """Load ingredient alias configuration."""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config", "ingredients.json"
        )
    with open(config_path, "r") as f:
        return json.load(f)


def map_ingredient(raw_description: str, aliases: dict | None = None) -> dict:
    """
    Map a raw receipt item description to a canonical ingredient name.

    Args:
        raw_description: The text as it appears on the receipt (e.g., "GRD PORK 80/20 10LB CS")
        aliases: The aliases dict from config (loaded automatically if None)

    Returns:
        dict with keys:
            - canonical_name: str — the standardized ingredient name, or "UNMAPPED: <raw>"
            - category: str — ingredient category (Protein, Produce, Seasoning, etc.)
            - matched_pattern: str — which alias pattern matched, or None
    """
    if aliases is None:
        aliases = load_aliases()

    alias_map = aliases.get("aliases", {})
    raw_upper = raw_description.upper().strip()

    best_match = None
    best_match_len = 0

    for canonical_name, info in alias_map.items():
        for pattern in info["patterns"]:
            pattern_upper = pattern.upper()
            # Check if the pattern appears in the raw description with word boundaries
            # Uses \b to prevent partial-word matches (e.g. "SALT" matching "BASALT")
            if re.search(r'\b' + re.escape(pattern_upper) + r'\b', raw_upper):
                # Prefer longer matches (more specific)
                if len(pattern_upper) > best_match_len:
                    best_match = {
                        "canonical_name": canonical_name,
                        "category": info["category"],
                        "default_unit": info.get("default_unit", "ea"),
                        "matched_pattern": pattern,
                    }
                    best_match_len = len(pattern_upper)

    if best_match:
        return best_match

    return {
        "canonical_name": f"{UNMAPPED_PREFIX}{raw_description}",
        "category": "Uncategorized",
        "default_unit": "ea",
        "matched_pattern": None,
    }


def map_receipt_items(receipt_data: dict, aliases: dict | None = None) -> dict:
    """
    Map all items in a parsed receipt to canonical ingredient names.

    Adds 'canonical_name' and 'category' fields to each item in the receipt.
    Returns the enriched receipt_data dict.
    """
    if aliases is None:
        aliases = load_aliases()

    unmapped_count = 0
    for item in receipt_data.get("items", []):
        raw = item.get("raw_description", item.get("name", ""))
        mapping = map_ingredient(raw, aliases)

        item["canonical_name"] = mapping["canonical_name"]
        item["category"] = mapping["category"]
        item["matched_pattern"] = mapping["matched_pattern"]

        if mapping["matched_pattern"] is None:
            unmapped_count += 1

    receipt_data["_mapping_stats"] = {
        "total_items": len(receipt_data.get("items", [])),
        "mapped": len(receipt_data.get("items", [])) - unmapped_count,
        "unmapped": unmapped_count,
    }

    return receipt_data


# ---------------------------------------------------------------------------
# Local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Quick test with sample descriptions
    test_descriptions = [
        "GRD PORK 80/20 10LB CS",
        "MINCED CHICKEN BREAST",
        "RAW SHRIMP 16/20 IQF",
        "RICE PAPER WRAPPER 12IN",
        "RICE PAPER WRAPPER 8IN",
        "VERMICELLI RICE NOODLE",
        "FRESH CARROTS WHOLE 25LB",
        "TARO ROOT",
        "GREEN CABBAGE 50LB CS",
        "YELLOW ONION 50LB BAG",
        "GARLIC POWDER 5LB",
        "SALT IODIZED 10LB",
        "SUGAR GRANULATED 25LB",
        "BLACK PEPPER GROUND 5LB",
        "CHICKEN BOUILLON PWD 5LB",
        "MUSHROOM SEASONING 1LB",
        "SOYBEAN OIL 35LB CONT",
        "FOIL TRAY LARGE 50CT",         # Should be UNMAPPED
        "RANDOM UNKNOWN PRODUCT",        # Should be UNMAPPED
    ]

    aliases = load_aliases()
    print(f"{'Receipt Text':<35} {'→':^3} {'Canonical Name':<30} {'Category':<15}")
    print("=" * 90)

    for desc in test_descriptions:
        result = map_ingredient(desc, aliases)
        status = "✓" if result["matched_pattern"] else "✗"
        print(f"{status} {desc:<33} → {result['canonical_name']:<30} {result['category']:<15}")
