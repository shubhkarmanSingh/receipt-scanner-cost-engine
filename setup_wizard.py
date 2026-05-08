#!/usr/bin/env python3
"""
setup_wizard.py — Interactive setup for configuring the Receipt Scanner.

Guides a non-technical user through creating a business_config.json in ~15 minutes.

Usage:
    python setup_wizard.py              # Full setup wizard
    python setup_wizard.py --add-item   # Add a new item alias to existing config
"""

import json
import os
import sys

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "business_config.json")
TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")


def _input(prompt: str, default: str = "") -> str:
    """Get input with an optional default."""
    if default:
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw if raw else default
    return input(f"{prompt}: ").strip()


def _input_number(prompt: str, default: float = 0) -> float:
    """Get numeric input with validation."""
    while True:
        raw = _input(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def _input_choice(prompt: str, choices: list[str]) -> str:
    """Present numbered choices and return the selected value."""
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    while True:
        raw = input(f"{prompt} (1-{len(choices)}): ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(choices)}.")


def _load_template(name: str) -> dict:
    """Load an industry template."""
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    with open(path) as f:
        return json.load(f)


def _list_templates() -> list[str]:
    """List available template names."""
    templates = []
    if os.path.isdir(TEMPLATES_DIR):
        for f in sorted(os.listdir(TEMPLATES_DIR)):
            if f.endswith(".json"):
                templates.append(f.replace(".json", ""))
    return templates


def run_wizard() -> dict:
    """Run the full interactive setup wizard."""
    print("=" * 60)
    print("  Receipt Scanner — Business Setup Wizard")
    print("=" * 60)
    print()
    print("This wizard will help you configure the receipt scanner")
    print("for your business. It takes about 10-15 minutes.")
    print()

    # ── Step 1: Choose template or start blank ──
    templates = _list_templates()
    config = {}

    if templates:
        print("Step 1: Choose a starting template")
        print()
        choices = [f"{t.title()} template" for t in templates] + ["Start blank"]
        choice = _input_choice("Select", choices)
        if choice != "Start blank":
            template_name = templates[choices.index(choice)]
            config = _load_template(template_name)
            print(f"\n  Loaded {template_name} template.\n")
        else:
            print("\n  Starting with blank config.\n")

    # ── Step 2: Business info ──
    print("Step 2: Business Information")
    print()
    business = config.get("business", {})
    business["name"] = _input("Business name", business.get("name", ""))
    business["industry"] = _input("Industry", business.get("industry", "general"))
    business["currency"] = _input("Currency", business.get("currency", "USD"))
    business["description"] = _input("Brief description", business.get("description", ""))

    print()
    print("  Common suppliers (comma-separated, or press Enter to skip):")
    suppliers_str = _input("Suppliers", ", ".join(business.get("typical_suppliers", [])))
    business["typical_suppliers"] = [s.strip() for s in suppliers_str.split(",") if s.strip()]
    config["business"] = business
    print()

    # ── Step 3: Item categories ──
    print("Step 3: Item Categories")
    print()
    items = config.get("items", {"aliases": {}, "categories": []})
    current_cats = items.get("categories", [])
    if current_cats:
        print(f"  Current categories: {', '.join(current_cats)}")
    cats_str = _input("Categories (comma-separated)", ", ".join(current_cats))
    items["categories"] = [c.strip() for c in cats_str.split(",") if c.strip()]
    items.setdefault("aliases", {})
    config["items"] = items
    print()

    # ── Step 4: Products ──
    print("Step 4: Products")
    print()
    products = config.get("products", {"unit_name": "unit", "recipes": {}})
    products["unit_name"] = _input("What do you produce? (unit name, e.g. roll, serving, unit, job)",
                                    products.get("unit_name", "unit"))

    print()
    print("  You can add products/recipes now, or later by editing")
    print("  config/business_config.json directly.")
    print()

    existing_recipes = products.get("recipes", {})
    if existing_recipes:
        print(f"  Existing products: {', '.join(existing_recipes.keys())}")

    while True:
        add = _input("Add a product? (y/n)", "n")
        if add.lower() != "y":
            break

        name = _input("  Product name")
        batch_size = int(_input_number("  Batch size (how many units per batch)", 100))
        size = _input("  Size/variant label (optional)", "")

        print("  Add ingredients (type 'done' when finished):")
        ingredients = {}
        while True:
            ing_name = _input("    Ingredient name (or 'done')")
            if ing_name.lower() == "done":
                break
            qty = _input_number("    Quantity needed per batch", 1)
            unit = _input("    Unit (lb, ea, pkg, etc.)", "ea")
            ingredients[ing_name] = {"qty": qty, "unit": unit}

        recipe = {"batch_size": batch_size, "ingredients": ingredients}
        if size:
            recipe["size"] = size
        existing_recipes[name] = recipe

    products["recipes"] = existing_recipes
    config["products"] = products
    print()

    # ── Step 5: Overhead costs ──
    print("Step 5: Monthly Overhead Costs")
    print()
    overhead = config.get("overhead", {})
    overhead["monthly_production"] = int(_input_number(
        f"Monthly production ({products['unit_name']}s per month)",
        overhead.get("monthly_production", 1000)))

    existing_cats = overhead.get("cost_categories", [])
    if existing_cats:
        print(f"\n  Current cost categories:")
        for cat in existing_cats:
            print(f"    {cat['name']}: ${cat['monthly_amount']:,.2f}/month")
        update = _input("\n  Update these amounts? (y/n)", "y")
        if update.lower() == "y":
            for cat in existing_cats:
                cat["monthly_amount"] = _input_number(
                    f"  Monthly {cat['name']} cost ($)", cat["monthly_amount"])
    else:
        print("  Add monthly cost categories (type 'done' when finished):")
        cats = []
        for default_name in ["Labor", "Rent", "Utilities", "Insurance"]:
            amount = _input_number(f"  Monthly {default_name} cost ($)", 0)
            if amount > 0:
                cats.append({"name": default_name, "monthly_amount": amount})
        while True:
            name = _input("  Add another cost category (or 'done')")
            if name.lower() == "done":
                break
            amount = _input_number(f"  Monthly {name} cost ($)", 0)
            cats.append({"name": name, "monthly_amount": amount})
        existing_cats = cats

    overhead["cost_categories"] = existing_cats
    config["overhead"] = overhead
    print()

    # ── Step 6: Pricing tiers ──
    print("Step 6: Pricing Tiers")
    print()
    pricing = config.get("pricing", {"tiers": {}})
    existing_tiers = pricing.get("tiers", {})

    if existing_tiers:
        print(f"  Current tiers: {', '.join(t.get('label', k) for k, t in existing_tiers.items())}")
        print("  (Product prices can be set later in the config file)")
    else:
        print("  Define how you sell your products (e.g., wholesale, retail, dine-in):")
        while True:
            tier_name = _input("  Tier name (or 'done')", "done" if existing_tiers else "")
            if tier_name.lower() == "done":
                break
            tier_key = tier_name.lower().replace(" ", "_").replace("-", "_")
            existing_tiers[tier_key] = {"label": tier_name, "prices": {}}

    pricing["tiers"] = existing_tiers
    config["pricing"] = pricing
    print()

    # ── Step 7: Extraction settings ──
    extraction = config.get("extraction", {})
    suppliers = business.get("typical_suppliers", [])
    if suppliers and not extraction.get("prompt_context"):
        extraction["prompt_context"] = (
            f"They purchase from suppliers like {', '.join(suppliers)}."
        )
    extraction.setdefault("item_term", "item")
    extraction.setdefault("receipt_rules", [])
    config["extraction"] = extraction

    # ── Step 8: Sheet settings (use defaults) ──
    config.setdefault("sheets", {
        "tab_names": {
            "purchases": "Purchases",
            "latest_prices": "Latest Prices",
            "recipes": "Recipes",
            "margins": "Margins",
            "unmapped": "Unmapped Items",
        }
    })

    return config


def run_add_item() -> None:
    """Add a new item alias to an existing config."""
    if not os.path.exists(CONFIG_PATH):
        print(f"No config found at {CONFIG_PATH}. Run the full wizard first.")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    aliases = config.get("items", {}).get("aliases", {})
    categories = config.get("items", {}).get("categories", [])

    print("Add a New Item Alias")
    print("=" * 40)
    print()

    canonical = _input("Canonical name (e.g. 'Chicken Breast')")

    print("  Enter receipt patterns that should map to this item.")
    print("  These are text fragments that appear on receipts.")
    print("  (type 'done' when finished)")
    patterns = []
    while True:
        p = _input("  Pattern (or 'done')")
        if p.lower() == "done":
            break
        patterns.append(p.upper())

    if not patterns:
        print("No patterns entered. Aborting.")
        return

    if categories:
        print(f"\n  Available categories: {', '.join(categories)}")
    category = _input("Category", categories[0] if categories else "General")
    default_unit = _input("Default unit (lb, ea, pkg, etc.)", "ea")

    aliases[canonical] = {
        "patterns": patterns,
        "category": category,
        "default_unit": default_unit,
    }

    config["items"]["aliases"] = aliases

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nAdded '{canonical}' with {len(patterns)} patterns to {CONFIG_PATH}")


def main():
    if "--add-item" in sys.argv:
        run_add_item()
        return

    config = run_wizard()

    # ── Save config ──
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print(f"  Business: {config['business']['name']}")
    print(f"  Industry: {config['business']['industry']}")
    print(f"  Products: {len(config.get('products', {}).get('recipes', {}))} defined")
    print(f"  Aliases:  {len(config.get('items', {}).get('aliases', {}))} defined")
    print()

    save = _input(f"Save to {CONFIG_PATH}? (y/n)", "y")
    if save.lower() == "y":
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\nConfig saved to {CONFIG_PATH}")
        print()
        print("Next steps:")
        print("  1. Review and edit config/business_config.json as needed")
        print("  2. Add item aliases: python setup_wizard.py --add-item")
        print("  3. Set up .env with your API keys (see .env.example)")
        print("  4. Initialize your Google Sheet: python sheets_client.py init <spreadsheet_id>")
        print("  5. Test: python serve_local.py")
    else:
        print("\nConfig not saved. You can re-run the wizard anytime.")


if __name__ == "__main__":
    main()
