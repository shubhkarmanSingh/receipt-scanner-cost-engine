"""
sheets_client.py — Google Sheets integration for the Purchases Database.

Handles:
  - Appending parsed receipt items to the Purchases sheet
  - Reading the latest prices for each item
  - Computing product costs using current prices
  - Checking for duplicate receipts

All sheet tab names and cost categories are driven by the business config.

Requires a Google Cloud service account with Sheets API access.
Set GOOGLE_SHEETS_CREDENTIALS_JSON env var to the path of the service account key file,
or place it at config/service_account.json.
"""

import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ingredient_mapper import UNMAPPED_PREFIX
from logger import get_logger

logger = get_logger(__name__)

# Retry configuration for transient Sheets API errors
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds: 2, 4, 8


def _execute_with_retry(request, description: str = "Sheets API call"):
    """Execute a Google Sheets API request with retry on transient errors."""
    import time
    for attempt in range(_MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning("%s attempt %d/%d failed (HTTP %d), retrying in %ds...",
                               description, attempt + 1, _MAX_RETRIES, e.resp.status, wait)
                time.sleep(wait)
            else:
                raise
        except (ConnectionError, TimeoutError) as e:
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning("%s attempt %d/%d failed (%s), retrying in %ds...",
                               description, attempt + 1, _MAX_RETRIES, e, wait)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Default sheet tab names (overridden by config)
# ---------------------------------------------------------------------------
_DEFAULT_TAB_NAMES = {
    "purchases": "Purchases",
    "latest_prices": "Latest Prices",
    "recipes": "Recipes",
    "margins": "Margins",
    "unmapped": "Unmapped Items",
}


def _get_tab_names(config: dict | None = None) -> dict:
    """Get sheet tab names from config, falling back to defaults."""
    if config is None:
        return dict(_DEFAULT_TAB_NAMES)
    return {**_DEFAULT_TAB_NAMES, **config.get("sheets", {}).get("tab_names", {})}


# Column order for the Purchases sheet
PURCHASES_COLUMNS = [
    "Date", "Supplier", "Raw Description", "Canonical Name", "Category",
    "Quantity", "Unit", "Unit Price", "Total Price", "Source", "Receipt ID"
]


def get_sheets_service(credentials_path: str | None = None):
    """Authenticate and return a Google Sheets API service object."""
    if credentials_path is None:
        credentials_path = os.environ.get(
            "GOOGLE_SHEETS_CREDENTIALS_JSON",
            os.path.join(os.path.dirname(__file__), "config", "service_account.json")
        )

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Google Sheets credentials file not found: {credentials_path}. "
            "Set GOOGLE_SHEETS_CREDENTIALS_JSON env var or place the file at config/service_account.json"
        )

    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


def _get_sheet_id(service, spreadsheet_id: str, sheet_name: str) -> int | None:
    """Get the numeric sheet ID for a given sheet name."""
    sheet_metadata = _execute_with_retry(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id),
        "get sheet metadata"
    )
    for sheet in sheet_metadata.get("sheets", []):
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]
    return None


def _format_sheet_tab(spreadsheet_id: str, sheet_name: str,
                      header_color: dict, service):
    """Apply formatting to a sheet tab (frozen header, borders, bold header row, auto-resize).

    Args:
        header_color: RGB dict, e.g. {"red": 0.2, "green": 0.5, "blue": 0.8}
    """
    try:
        sheet_id = _get_sheet_id(service, spreadsheet_id, sheet_name)
        if sheet_id is None:
            return

        requests = [
            {
                "updateSheetProperties": {
                    "fields": "gridProperties.frozenRowCount",
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1}
                    }
                }
            },
            {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(PURCHASES_COLUMNS)
                    },
                    "top": {"style": "SOLID", "width": 1},
                    "bottom": {"style": "SOLID", "width": 1},
                    "left": {"style": "SOLID", "width": 1},
                    "right": {"style": "SOLID", "width": 1},
                    "innerHorizontal": {"style": "SOLID", "width": 1},
                    "innerVertical": {"style": "SOLID", "width": 1}
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(PURCHASES_COLUMNS)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True,
                                "fontSize": 11,
                                "foregroundColorStyle": {
                                    "rgbColor": {"red": 1, "green": 1, "blue": 1}
                                }
                            },
                            "backgroundColor": header_color,
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment,verticalAlignment)"
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(PURCHASES_COLUMNS)
                    }
                }
            }
        ]

        _execute_with_retry(
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ),
            f"format {sheet_name}"
        )
    except HttpError as e:
        logger.warning("Could not format %s sheet: %s", sheet_name, e)


def _format_purchases_sheet(spreadsheet_id: str, service, config: dict | None = None):
    """Apply formatting to the Purchases sheet."""
    tabs = _get_tab_names(config)
    _format_sheet_tab(spreadsheet_id, tabs["purchases"],
                      {"red": 0.2, "green": 0.5, "blue": 0.8}, service)


def _format_unmapped_sheet(spreadsheet_id: str, service, config: dict | None = None):
    """Apply formatting to the Unmapped Items sheet."""
    tabs = _get_tab_names(config)
    _format_sheet_tab(spreadsheet_id, tabs["unmapped"],
                      {"red": 0.8, "green": 0.4, "blue": 0.2}, service)


def _check_duplicate_receipt(spreadsheet_id: str, receipt_id: str, service,
                             config: dict | None = None) -> bool:
    """Check if a receipt ID already exists in the Purchases sheet."""
    tabs = _get_tab_names(config)
    try:
        result = _execute_with_retry(
            service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{tabs['purchases']}!K:K"  # Receipt ID column
            ),
            "check duplicate receipt"
        )
        existing_ids = [row[0] for row in result.get("values", [])[1:] if row]
        return receipt_id in existing_ids
    except HttpError as e:
        # Only swallow 404 (sheet doesn't exist yet) — all other errors propagate
        if e.resp.status == 404:
            logger.warning("Purchases sheet not found during duplicate check, assuming no duplicates")
            return False
        raise


def append_receipt_to_sheet(spreadsheet_id: str, receipt_data: dict,
                            source: str = "photo", service=None,
                            config: dict | None = None) -> dict:
    """
    Append all items from a parsed+mapped receipt to the Purchases sheet.

    Args:
        spreadsheet_id: The Google Sheets document ID
        receipt_data: Parsed receipt with mapped canonical_name fields
        source: How the receipt was captured ("photo", "email", "csv")
        service: Optional pre-authenticated Sheets service
        config: Business configuration dict

    Returns:
        dict with append results and stats
    """
    if service is None:
        service = get_sheets_service()

    tabs = _get_tab_names(config)

    merchant = receipt_data.get("merchant", "Unknown")
    date = receipt_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    receipt_id = receipt_data.get("receipt_id") or f"{merchant}_{date}_{datetime.now().strftime('%H%M%S')}"

    # Check for duplicate receipt
    if _check_duplicate_receipt(spreadsheet_id, receipt_id, service, config):
        raise ValueError(
            f"Duplicate receipt detected: '{receipt_id}' already exists in the {tabs['purchases']} sheet. "
            "If this is intentional, change the receipt_id before resubmitting."
        )

    rows = []
    unmapped_rows = []

    for item in receipt_data.get("items", []):
        canonical = item.get("canonical_name", item.get("name", "Unknown"))
        category = item.get("category", "Uncategorized")
        is_unmapped = canonical.startswith(UNMAPPED_PREFIX)

        row = [
            date,
            merchant,
            item.get("raw_description", item.get("name", "")),
            canonical[len(UNMAPPED_PREFIX):] if is_unmapped else canonical,
            category,
            item.get("quantity", 0),
            item.get("unit", "ea"),
            item.get("unit_price", 0),
            item.get("total_price", 0),
            source,
            receipt_id,
        ]

        rows.append(row)
        if is_unmapped:
            unmapped_rows.append(row)

    # Append to Purchases sheet
    result = _execute_with_retry(
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{tabs['purchases']}!A:K",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows}
        ),
        "append to Purchases"
    )

    # Format the newly appended rows
    if rows:
        _format_purchases_sheet(spreadsheet_id, service, config)

    # Also log unmapped items to a separate tab for review
    if unmapped_rows:
        try:
            _execute_with_retry(
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=f"{tabs['unmapped']}!A:K",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": unmapped_rows}
                ),
                "append to Unmapped Items"
            )
            _format_unmapped_sheet(spreadsheet_id, service, config)
        except HttpError as e:
            logger.warning("Could not write to Unmapped Items sheet: %s", e, exc_info=True)

    return {
        "rows_appended": len(rows),
        "unmapped_items": len(unmapped_rows),
        "receipt_id": receipt_id,
        "spreadsheet_id": spreadsheet_id,
        "sheets_response": result,
    }


def get_latest_prices(spreadsheet_id: str, service=None,
                      config: dict | None = None) -> dict[str, dict]:
    """
    Read all purchase data and compute the latest unit price for each item.

    Returns a dict like:
        {"Pork": {"unit_price": 2.00, "unit": "lb", "date": "2026-03-04", "supplier": "Restaurant Depot"}, ...}
    """
    if service is None:
        service = get_sheets_service()

    tabs = _get_tab_names(config)

    result = _execute_with_retry(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{tabs['purchases']}!A:K"
        ),
        "read Purchases data"
    )

    rows = result.get("values", [])
    if len(rows) < 2:  # Only header or empty
        return {}

    # Build a dict of most recent price per canonical ingredient
    latest = {}
    for row in rows[1:]:  # Skip header
        if len(row) < 9:
            continue
        date, supplier, raw_desc, canonical, category, qty, unit, unit_price, total = row[:9]

        try:
            unit_price_num = float(unit_price)
            qty_num = float(qty)
        except (ValueError, TypeError):
            continue

        if unit_price_num < 0 or qty_num < 0:
            logger.warning("Skipping %s: negative price (%.2f) or qty (%.2f)",
                           canonical, unit_price_num, qty_num)
            continue

        if category == "Uncategorized":
            continue

        # Keep the most recent entry per ingredient
        if canonical not in latest or date > latest[canonical]["date"]:
            latest[canonical] = {
                "unit_price": unit_price_num,
                "unit": unit,
                "quantity_purchased": qty_num,
                "total_price": float(total) if total else unit_price_num * qty_num,
                "date": date,
                "supplier": supplier,
            }

    return latest


def compute_recipe_costs(spreadsheet_id: str, config: dict | None = None,
                         service=None) -> list[dict]:
    """
    Compute the complete cost breakdown per unit for each product.

    All overhead categories, pricing tiers, and unit names are driven by
    the business config. Works for any industry — not just food production.

    Returns a list of dicts with cost breakdowns and margins per pricing tier.
    """
    if config is None:
        from config_loader import load_business_config
        config = load_business_config()

    tabs = _get_tab_names(config)
    latest_prices = get_latest_prices(spreadsheet_id, service, config)
    recipes = config.get("products", {}).get("recipes", {})
    overhead_config = config.get("overhead", {})
    pricing_tiers = config.get("pricing", {}).get("tiers", {})
    unit_name = config.get("products", {}).get("unit_name", "unit")

    # Compute per-unit overhead costs from monthly totals
    production = overhead_config.get("monthly_production", 1)
    cost_categories = overhead_config.get("cost_categories", [])

    overhead_per_unit = {}
    total_overhead_per_unit = 0
    for cat in cost_categories:
        per_unit = cat["monthly_amount"] / production if production > 0 else 0
        overhead_per_unit[cat["name"]] = round(per_unit, 4)
        total_overhead_per_unit += per_unit

    results = []
    for product_name, recipe in recipes.items():
        batch_size = recipe.get("batch_size", recipe.get("batch_rolls", 1))
        batch_ingredient_cost = 0
        ingredient_costs = []
        missing_prices = []

        # Calculate ingredient costs
        for ingredient, usage in recipe.get("ingredients", {}).items():
            price_info = latest_prices.get(ingredient)
            if price_info is None:
                missing_prices.append(ingredient)
                continue

            ingredient_cost = price_info["unit_price"] * usage["qty"]
            batch_ingredient_cost += ingredient_cost
            ingredient_costs.append({
                "ingredient": ingredient,
                "qty_needed": usage["qty"],
                "unit": usage["unit"],
                "unit_price": price_info["unit_price"],
                "line_cost": round(ingredient_cost, 2),
                "price_date": price_info["date"],
                "supplier": price_info["supplier"],
            })

        ingredient_cost_per_unit = batch_ingredient_cost / batch_size if batch_size > 0 else 0
        total_cost_per_unit = ingredient_cost_per_unit + total_overhead_per_unit

        # Build result entry
        entry = {
            "product": product_name,
            "size": recipe.get("size", ""),
            "batch_size": batch_size,
            "unit_name": unit_name,
            "ingredient_cost_per_unit": round(ingredient_cost_per_unit, 4),
            "overhead_breakdown": dict(overhead_per_unit),
            "total_overhead_per_unit": round(total_overhead_per_unit, 4),
            "total_cost_per_unit": round(total_cost_per_unit, 4),
            "ingredients": ingredient_costs,
            "missing_prices": missing_prices,
            "tiers": {},
        }

        # Compute margins for each pricing tier
        for tier_key, tier_config in pricing_tiers.items():
            tier_prices = tier_config.get("prices", {}).get(product_name, {})
            per_unit = tier_prices.get("per_unit")
            low = tier_prices.get("low")
            high = tier_prices.get("high")

            tier_result = {"label": tier_config.get("label", tier_key)}

            if per_unit is not None:
                margin = (per_unit - total_cost_per_unit) / per_unit if per_unit > 0 else 0
                tier_result.update({
                    "price_per_unit": per_unit,
                    "profit_per_unit": round(per_unit - total_cost_per_unit, 4),
                    "margin_pct": round(margin * 100, 1),
                })
            if low is not None:
                margin_low = (low - total_cost_per_unit) / low if low > 0 else 0
                tier_result.update({
                    "price_low": low,
                    "profit_low": round(low - total_cost_per_unit, 4),
                    "margin_low_pct": round(margin_low * 100, 1),
                })
            if high is not None:
                margin_high = (high - total_cost_per_unit) / high if high > 0 else 0
                tier_result.update({
                    "price_high": high,
                    "profit_high": round(high - total_cost_per_unit, 4),
                    "margin_high_pct": round(margin_high * 100, 1),
                })

            entry["tiers"][tier_key] = tier_result

        # Backward-compatible fields for the first two tiers
        tier_keys = list(pricing_tiers.keys())
        if len(tier_keys) >= 1:
            t = entry["tiers"].get(tier_keys[0], {})
            entry["frozen_price_per_roll"] = t.get("price_per_unit", 0)
            entry["frozen_profit_per_roll"] = t.get("profit_per_unit", 0)
            entry["frozen_margin_pct"] = t.get("margin_pct", 0)
        if len(tier_keys) >= 2:
            t = entry["tiers"].get(tier_keys[1], {})
            entry["cooked_price_low"] = t.get("price_low", 0)
            entry["cooked_price_high"] = t.get("price_high", 0)
            entry["cooked_margin_low_pct"] = t.get("margin_low_pct", 0)
            entry["cooked_margin_high_pct"] = t.get("margin_high_pct", 0)

        results.append(entry)

    # ── Write results to the spreadsheet tabs ──
    if service is None:
        service = get_sheets_service()

    # 1. Latest Prices tab
    price_rows = [["Item", "Unit Price", "Unit", "Qty Purchased", "Total Price", "Date", "Supplier"]]
    for name, info in sorted(latest_prices.items()):
        price_rows.append([
            name, info["unit_price"], info["unit"],
            info.get("quantity_purchased", ""), info.get("total_price", ""),
            info["date"], info["supplier"]
        ])
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tabs['latest_prices']}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": price_rows}
        ),
        "update Latest Prices"
    )

    # 2. Recipes tab — cost breakdown per product (dynamic overhead columns)
    overhead_names = [cat["name"] for cat in cost_categories]
    recipe_header = ["Product", "Size", "Batch", f"Ingredient $/{unit_name.title()}"]
    recipe_header += [f"{name} $/{unit_name.title()}" for name in overhead_names]
    recipe_header += [f"Total $/{unit_name.title()}"]

    # Add first tier price column if available
    if tier_keys:
        first_tier_label = pricing_tiers[tier_keys[0]].get("label", tier_keys[0])
        recipe_header += [f"{first_tier_label} $/{unit_name.title()}", f"{first_tier_label} Margin %"]

    recipe_rows = [recipe_header]
    for r in results:
        row = [r["product"], r["size"], r["batch_size"], r["ingredient_cost_per_unit"]]
        row += [r["overhead_breakdown"].get(name, 0) for name in overhead_names]
        row += [r["total_cost_per_unit"]]
        if tier_keys:
            t = r["tiers"].get(tier_keys[0], {})
            row += [t.get("price_per_unit", ""), f"{t.get('margin_pct', 0)}%"]
        recipe_rows.append(row)

    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tabs['recipes']}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": recipe_rows}
        ),
        "update Recipes"
    )

    # 3. Margins tab — all pricing tiers dynamically
    margin_header = ["Product", f"Total Cost/{unit_name.title()}"]
    for tier_key in tier_keys:
        label = pricing_tiers[tier_key].get("label", tier_key)
        margin_header += [f"{label} Price", f"{label} Margin %", f"{label} Profit"]

    margin_rows = [margin_header]
    for r in results:
        row = [r["product"], r["total_cost_per_unit"]]
        for tier_key in tier_keys:
            t = r["tiers"].get(tier_key, {})
            price = t.get("price_per_unit", t.get("price_low", ""))
            margin = t.get("margin_pct", t.get("margin_low_pct", 0))
            profit = t.get("profit_per_unit", t.get("profit_low", ""))
            row += [price, f"{margin}%", profit]
        margin_rows.append(row)

    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tabs['margins']}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": margin_rows}
        ),
        "update Margins"
    )

    logger.info("Updated tabs: %s, %s, %s", tabs['latest_prices'], tabs['recipes'], tabs['margins'])

    return results


def initialize_spreadsheet(spreadsheet_id: str, service=None,
                           config: dict | None = None) -> None:
    """
    Set up the sheet tabs and headers for a fresh Purchases Database.
    Call this once when first creating the Google Sheet.
    """
    if service is None:
        service = get_sheets_service()

    tabs = _get_tab_names(config)
    tabs_to_create = list(tabs.values())
    purchases_tab = tabs["purchases"]
    unmapped_tab = tabs["unmapped"]

    # Get existing sheet names
    spreadsheet = _execute_with_retry(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id),
        "get spreadsheet metadata"
    )
    existing_tabs = {s["properties"]["title"] for s in spreadsheet["sheets"]}

    requests = []
    for tab in tabs_to_create:
        if tab not in existing_tabs:
            requests.append({
                "addSheet": {"properties": {"title": tab}}
            })

    # Rename default "Sheet1" if it exists and we need Purchases
    if "Sheet1" in existing_tabs and purchases_tab not in existing_tabs:
        sheet1_id = None
        for s in spreadsheet["sheets"]:
            if s["properties"]["title"] == "Sheet1":
                sheet1_id = s["properties"]["sheetId"]
                break
        if sheet1_id is not None:
            requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet1_id, "title": purchases_tab},
                    "fields": "title"
                }
            })
            requests = [r for r in requests
                        if not (r.get("addSheet", {}).get("properties", {}).get("title") == purchases_tab)]

    if requests:
        _execute_with_retry(
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ),
            "create sheet tabs"
        )

    # Set headers for Purchases sheet
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{purchases_tab}!A1:K1",
            valueInputOption="USER_ENTERED",
            body={"values": [PURCHASES_COLUMNS]}
        ),
        "set Purchases headers"
    )

    # Set headers for Unmapped Items
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{unmapped_tab}!A1:K1",
            valueInputOption="USER_ENTERED",
            body={"values": [PURCHASES_COLUMNS]}
        ),
        "set Unmapped Items headers"
    )

    logger.info("Spreadsheet initialized with tabs: %s", tabs_to_create)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python sheets_client.py init <spreadsheet_id>")
        print("  python sheets_client.py prices <spreadsheet_id>")
        print("  python sheets_client.py costs <spreadsheet_id>")
        sys.exit(1)

    command = sys.argv[1]
    sheet_id = sys.argv[2]

    if command == "init":
        initialize_spreadsheet(sheet_id)
        print("Done! Your Purchases Database is ready.")

    elif command == "prices":
        prices = get_latest_prices(sheet_id)
        for name, info in sorted(prices.items()):
            print(f"  {name:<30s} ${info['unit_price']:.2f}/{info['unit']:<6s}  "
                  f"(from {info['supplier']}, {info['date']})")

    elif command == "costs":
        costs = compute_recipe_costs(sheet_id)
        for recipe in costs:
            unit = recipe.get('unit_name', 'unit')
            print(f"\n{recipe['product']} ({recipe['size']}) — batch of {recipe['batch_size']} {unit}s")
            print(f"  Cost breakdown per {unit}:")
            print(f"    Ingredients:  ${recipe['ingredient_cost_per_unit']:.4f}")
            for cat_name, cat_cost in recipe.get('overhead_breakdown', {}).items():
                print(f"    {cat_name + ':':<14s} ${cat_cost:.4f}")
            print(f"    TOTAL:        ${recipe['total_cost_per_unit']:.4f}")
            for tier_key, tier in recipe.get('tiers', {}).items():
                label = tier.get('label', tier_key)
                print(f"  {label}:")
                if 'price_per_unit' in tier:
                    print(f"    Sell price:   ${tier['price_per_unit']:.2f}")
                    print(f"    Profit/{unit}: ${tier['profit_per_unit']:.4f}")
                    print(f"    Margin:       {tier['margin_pct']:.1f}%")
                elif 'price_low' in tier:
                    print(f"    Sell price:   ${tier['price_low']:.2f} - ${tier.get('price_high', 0):.2f}")
                    print(f"    Margin:       {tier.get('margin_low_pct', 0):.1f}% - {tier.get('margin_high_pct', 0):.1f}%")
            if recipe['missing_prices']:
                print(f"  Missing prices for: {', '.join(recipe['missing_prices'])}")
