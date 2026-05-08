"""
sheets_client.py — Google Sheets integration for the Purchases Database.

Handles:
  - Appending parsed receipt items to the Purchases sheet
  - Reading the latest prices for each ingredient
  - Computing recipe costs using current prices
  - Checking for duplicate receipts

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
# Sheet tab names (constants)
# ---------------------------------------------------------------------------
PURCHASES_SHEET = "Purchases"
LATEST_PRICES_SHEET = "Latest Prices"
RECIPES_SHEET = "Recipes"
MARGINS_SHEET = "Margins"
UNMAPPED_SHEET = "Unmapped Items"

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


def _format_purchases_sheet(spreadsheet_id: str, service):
    """Apply formatting to the Purchases sheet."""
    _format_sheet_tab(spreadsheet_id, PURCHASES_SHEET,
                      {"red": 0.2, "green": 0.5, "blue": 0.8}, service)


def _format_unmapped_sheet(spreadsheet_id: str, service):
    """Apply formatting to the Unmapped Items sheet."""
    _format_sheet_tab(spreadsheet_id, UNMAPPED_SHEET,
                      {"red": 0.8, "green": 0.4, "blue": 0.2}, service)


def _check_duplicate_receipt(spreadsheet_id: str, receipt_id: str, service) -> bool:
    """Check if a receipt ID already exists in the Purchases sheet."""
    try:
        result = _execute_with_retry(
            service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{PURCHASES_SHEET}!K:K"  # Receipt ID column
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
                            source: str = "photo", service=None) -> dict:
    """
    Append all items from a parsed+mapped receipt to the Purchases sheet.

    Args:
        spreadsheet_id: The Google Sheets document ID
        receipt_data: Parsed receipt with mapped canonical_name fields
        source: How the receipt was captured ("photo", "email", "csv")
        service: Optional pre-authenticated Sheets service

    Returns:
        dict with append results and stats
    """
    if service is None:
        service = get_sheets_service()

    merchant = receipt_data.get("merchant", "Unknown")
    date = receipt_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    receipt_id = receipt_data.get("receipt_id") or f"{merchant}_{date}_{datetime.now().strftime('%H%M%S')}"

    # Check for duplicate receipt
    if _check_duplicate_receipt(spreadsheet_id, receipt_id, service):
        raise ValueError(
            f"Duplicate receipt detected: '{receipt_id}' already exists in the Purchases sheet. "
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
            range=f"{PURCHASES_SHEET}!A:K",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows}
        ),
        "append to Purchases"
    )

    # Format the newly appended rows
    if rows:
        _format_purchases_sheet(spreadsheet_id, service)

    # Also log unmapped items to a separate tab for review
    if unmapped_rows:
        try:
            _execute_with_retry(
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=f"{UNMAPPED_SHEET}!A:K",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": unmapped_rows}
                ),
                "append to Unmapped Items"
            )
            _format_unmapped_sheet(spreadsheet_id, service)
        except HttpError as e:
            logger.warning("Could not write to Unmapped Items sheet: %s", e, exc_info=True)

    return {
        "rows_appended": len(rows),
        "unmapped_items": len(unmapped_rows),
        "receipt_id": receipt_id,
        "spreadsheet_id": spreadsheet_id,
        "sheets_response": result,
    }


def get_latest_prices(spreadsheet_id: str, service=None) -> dict[str, dict]:
    """
    Read all purchase data and compute the latest unit price for each ingredient.

    Returns a dict like:
        {"Pork": {"unit_price": 2.00, "unit": "lb", "date": "2026-03-04", "supplier": "Restaurant Depot"}, ...}
    """
    if service is None:
        service = get_sheets_service()

    result = _execute_with_retry(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{PURCHASES_SHEET}!A:K"
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


def compute_recipe_costs(spreadsheet_id: str, config_path: str | None = None,
                         service=None) -> list[dict]:
    """
    Compute the complete cost breakdown per roll for each product.
    
    Includes:
    - Ingredient costs based on latest purchasing prices
    - Labor cost per roll
    - Overhead & supplies cost per roll
    - Insurance cost per roll
    - Total cost per roll
    
    Returns margins for both frozen and cooked selling prices.
    """
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__), "config", "ingredients.json"
        )

    with open(config_path) as f:
        config = json.load(f)

    latest_prices = get_latest_prices(spreadsheet_id, service)
    recipes = config.get("product_recipes", {})
    overhead_config = config.get("overhead", {})
    
    # Compute overhead costs per roll from monthly totals (or fall back to precomputed)
    production = overhead_config.get("monthly_production_rolls", 200000)
    cost_per_roll_config = overhead_config.get("cost_per_roll", {})

    if production > 0:
        labor_per_roll = overhead_config.get("monthly_labor", 35700.50) / production
        overhead_per_roll = overhead_config.get("monthly_fixed_overhead", 6167.66) / production
        insurance_per_roll = overhead_config.get("monthly_insurance", 3550.00) / production
        supplies_per_roll = overhead_config.get("monthly_supplies", 978.86) / production
    else:
        labor_per_roll = cost_per_roll_config.get("labor", 0.1785)
        overhead_per_roll = cost_per_roll_config.get("overhead", 0.0308)
        insurance_per_roll = cost_per_roll_config.get("insurance", 0.0178)
        supplies_per_roll = cost_per_roll_config.get("supplies", 0.0049)
    
    results = []
    for product_name, recipe in recipes.items():
        batch_rolls = recipe["batch_rolls"]
        batch_ingredient_cost = 0
        ingredient_costs = []
        missing_prices = []

        # Calculate ingredient costs
        for ingredient, usage in recipe["ingredients"].items():
            price_info = latest_prices.get(ingredient)
            if price_info is None:
                missing_prices.append(ingredient)
                continue

            # Calculate cost for this ingredient in this recipe batch
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

        ingredient_cost_per_roll = batch_ingredient_cost / batch_rolls if batch_rolls > 0 else 0
        
        # Compute total cost per roll
        total_cost_per_roll = (
            ingredient_cost_per_roll + 
            labor_per_roll + 
            overhead_per_roll + 
            insurance_per_roll + 
            supplies_per_roll
        )
        
        # Get selling prices
        wholesale_price = recipe.get("wholesale_price_per_roll", 0)
        cooked_price_low = recipe.get("cooked_price_low", 0)
        cooked_price_high = recipe.get("cooked_price_high", 0)
        
        # Compute margins
        frozen_margin = (wholesale_price - total_cost_per_roll) / wholesale_price if wholesale_price > 0 else 0
        cooked_margin_low = (cooked_price_low - total_cost_per_roll) / cooked_price_low if cooked_price_low > 0 else 0
        cooked_margin_high = (cooked_price_high - total_cost_per_roll) / cooked_price_high if cooked_price_high > 0 else 0

        results.append({
            "product": product_name,
            "size": recipe.get("size", ""),
            "batch_rolls": batch_rolls,
            
            # Cost breakdown per roll
            "ingredient_cost_per_roll": round(ingredient_cost_per_roll, 4),
            "labor_cost_per_roll": round(labor_per_roll, 4),
            "overhead_cost_per_roll": round(overhead_per_roll, 4),
            "insurance_cost_per_roll": round(insurance_per_roll, 4),
            "supplies_cost_per_roll": round(supplies_per_roll, 4),
            "total_cost_per_roll": round(total_cost_per_roll, 4),
            
            # Frozen (wholesale) pricing
            "frozen_price_per_roll": wholesale_price,
            "frozen_profit_per_roll": round(wholesale_price - total_cost_per_roll, 4),
            "frozen_margin_pct": round(frozen_margin * 100, 1),
            
            # Cooked pricing
            "cooked_price_low": cooked_price_low,
            "cooked_price_high": cooked_price_high,
            "cooked_profit_low": round(cooked_price_low - total_cost_per_roll, 4),
            "cooked_profit_high": round(cooked_price_high - total_cost_per_roll, 4),
            "cooked_margin_low_pct": round(cooked_margin_low * 100, 1),
            "cooked_margin_high_pct": round(cooked_margin_high * 100, 1),
            
            # Ingredient details
            "ingredients": ingredient_costs,
            "missing_prices": missing_prices,
        })

    # ── Write results to the spreadsheet tabs ──
    if service is None:
        service = get_sheets_service()

    # 1. Latest Prices tab
    price_rows = [["Ingredient", "Unit Price", "Unit", "Qty Purchased", "Total Price", "Date", "Supplier"]]
    for name, info in sorted(latest_prices.items()):
        price_rows.append([
            name, info["unit_price"], info["unit"],
            info.get("quantity_purchased", ""), info.get("total_price", ""),
            info["date"], info["supplier"]
        ])
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{LATEST_PRICES_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": price_rows}
        ),
        "update Latest Prices"
    )

    # 2. Recipes tab — cost breakdown per product
    recipe_rows = [["Product", "Size", "Batch", "Ingredient $/Roll", "Labor $/Roll",
                    "Overhead $/Roll", "Insurance $/Roll", "Supplies $/Roll",
                    "Total $/Roll", "Wholesale $/Roll", "Frozen Margin %"]]
    for r in results:
        recipe_rows.append([
            r["product"], r["size"], r["batch_rolls"],
            r["ingredient_cost_per_roll"], r["labor_cost_per_roll"],
            r["overhead_cost_per_roll"], r["insurance_cost_per_roll"],
            r["supplies_cost_per_roll"], r["total_cost_per_roll"],
            r["frozen_price_per_roll"], f"{r['frozen_margin_pct']}%"
        ])
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{RECIPES_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": recipe_rows}
        ),
        "update Recipes"
    )

    # 3. Margins tab — selling prices and margins
    margin_rows = [["Product", "Total Cost/Roll", "Frozen Wholesale", "Frozen Margin %",
                    "Frozen Profit/Roll", "Cooked Low", "Cooked High",
                    "Cooked Margin Low %", "Cooked Margin High %"]]
    for r in results:
        margin_rows.append([
            r["product"], r["total_cost_per_roll"],
            r["frozen_price_per_roll"], f"{r['frozen_margin_pct']}%",
            r["frozen_profit_per_roll"],
            r["cooked_price_low"], r["cooked_price_high"],
            f"{r['cooked_margin_low_pct']}%", f"{r['cooked_margin_high_pct']}%"
        ])
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{MARGINS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": margin_rows}
        ),
        "update Margins"
    )

    logger.info("Updated tabs: %s, %s, %s", LATEST_PRICES_SHEET, RECIPES_SHEET, MARGINS_SHEET)

    return results


def initialize_spreadsheet(spreadsheet_id: str, service=None) -> None:
    """
    Set up the sheet tabs and headers for a fresh Purchases Database.
    Call this once when first creating the Google Sheet.
    """
    if service is None:
        service = get_sheets_service()

    # Create tabs
    tabs_to_create = [PURCHASES_SHEET, LATEST_PRICES_SHEET, RECIPES_SHEET,
                      MARGINS_SHEET, UNMAPPED_SHEET]

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
    if "Sheet1" in existing_tabs and PURCHASES_SHEET not in existing_tabs:
        sheet1_id = None
        for s in spreadsheet["sheets"]:
            if s["properties"]["title"] == "Sheet1":
                sheet1_id = s["properties"]["sheetId"]
                break
        if sheet1_id is not None:
            requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet1_id, "title": PURCHASES_SHEET},
                    "fields": "title"
                }
            })
            # Remove from creation list
            requests = [r for r in requests
                        if not (r.get("addSheet", {}).get("properties", {}).get("title") == PURCHASES_SHEET)]

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
            range=f"{PURCHASES_SHEET}!A1:K1",
            valueInputOption="USER_ENTERED",
            body={"values": [PURCHASES_COLUMNS]}
        ),
        "set Purchases headers"
    )

    # Set headers for Unmapped Items
    _execute_with_retry(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{UNMAPPED_SHEET}!A1:K1",
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
            print(f"\n{recipe['product']} ({recipe['size']}) — batch of {recipe['batch_rolls']} rolls")
            print(f"  Cost breakdown per roll:")
            print(f"    Ingredients:  ${recipe['ingredient_cost_per_roll']:.4f}")
            print(f"    Labor:        ${recipe['labor_cost_per_roll']:.4f}")
            print(f"    Overhead:     ${recipe['overhead_cost_per_roll']:.4f}")
            print(f"    Insurance:    ${recipe['insurance_cost_per_roll']:.4f}")
            print(f"    Supplies:     ${recipe['supplies_cost_per_roll']:.4f}")
            print(f"    TOTAL:        ${recipe['total_cost_per_roll']:.4f}")
            print(f"  Frozen pricing:")
            print(f"    Sell price:   ${recipe['frozen_price_per_roll']:.2f}")
            print(f"    Profit/roll:  ${recipe['frozen_profit_per_roll']:.4f}")
            print(f"    Margin:       {recipe['frozen_margin_pct']:.1f}%")
            print(f"  Cooked pricing:")
            print(f"    Sell price:   ${recipe['cooked_price_low']:.2f} - ${recipe['cooked_price_high']:.2f}")
            print(f"    Profit/roll:  ${recipe['cooked_profit_low']:.4f} - ${recipe['cooked_profit_high']:.4f}")
            print(f"    Margin:       {recipe['cooked_margin_low_pct']:.1f}% - {recipe['cooked_margin_high_pct']:.1f}%")
            if recipe['missing_prices']:
                print(f"  ⚠ Missing prices for: {', '.join(recipe['missing_prices'])}")
