"""
main.py — Google Cloud Function entry point for the SpringRoll House Receipt Scanner.

Deployment:
    gcloud functions deploy scan-receipt \
        --runtime python312 \
        --trigger-http \
        --no-allow-unauthenticated \
        --entry-point scan_receipt \
        --set-env-vars ANTHROPIC_API_KEY=sk-...,SPREADSHEET_ID=1abc...,SCANNER_API_KEY=your-secret \
        --memory 512MB \
        --timeout 60s

Usage:
    1. HTTP POST with base64 image:
        curl -X POST https://REGION-PROJECT.cloudfunctions.net/scan-receipt \
            -H "Content-Type: application/json" \
            -d '{"image_base64": "...", "media_type": "image/png", "source": "photo"}'

    2. HTTP POST with image URL:
        curl -X POST https://REGION-PROJECT.cloudfunctions.net/scan-receipt \
            -H "Content-Type: application/json" \
            -d '{"image_url": "https://...", "source": "photo"}'

Response:
    {
        "status": "success",
        "receipt_id": "Restaurant Depot_2026-03-04_092345",
        "merchant": "Restaurant Depot",
        "items_extracted": 17,
        "items_mapped": 15,
        "items_unmapped": 2,
        "total": 905.10,
        "rows_appended": 17,
        "recipe_costs": [ ... ]
    }
"""

import functions_framework
import json
import os
import base64
import traceback
from datetime import datetime

from receipt_extractor import extract_receipt
from ingredient_mapper import map_receipt_items, load_aliases, UNMAPPED_PREFIX
from sheets_client import (
    append_receipt_to_sheet,
    compute_recipe_costs,
    get_sheets_service,
)


# Environment variables
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # Used by anthropic SDK
API_KEY = os.environ.get("SCANNER_API_KEY")  # Optional: set to require auth on requests


@functions_framework.http
def scan_receipt(request):
    """
    Cloud Function entry point. Accepts an HTTP POST with a receipt image,
    extracts data using Claude Vision, maps ingredients, writes to Sheets,
    and returns updated recipe costs.
    """
    # ── CORS headers for browser requests ──
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # ── API key authentication (if SCANNER_API_KEY is configured) ──
    if API_KEY:
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != API_KEY:
            return (json.dumps({
                "status": "error",
                "message": "Invalid or missing API key. Set X-API-Key header."
            }), 401, headers)

    try:
        # ── Parse request ──
        request_json = request.get_json(silent=True) or {}
        image_base64 = request_json.get("image_base64")
        image_url = request_json.get("image_url")
        media_type = request_json.get("media_type", "image/png")
        source = request_json.get("source", "photo")

        if not image_base64 and not image_url:
            return (json.dumps({
                "status": "error",
                "message": "Provide 'image_base64' or 'image_url' in request body"
            }), 400, headers)

        if not SPREADSHEET_ID:
            return (json.dumps({
                "status": "error",
                "message": "SPREADSHEET_ID environment variable not set"
            }), 500, headers)

        # If URL provided, fetch the image
        if image_url and not image_base64:
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            if parsed.scheme not in ("https",):
                return (json.dumps({
                    "status": "error",
                    "message": "Only https:// image URLs are allowed"
                }), 400, headers)
            # Block requests to private/internal IPs
            import socket
            try:
                resolved_ip = socket.getaddrinfo(parsed.hostname, None)[0][4][0]
                import ipaddress
                ip = ipaddress.ip_address(resolved_ip)
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    return (json.dumps({
                        "status": "error",
                        "message": "URLs pointing to private/internal networks are not allowed"
                    }), 400, headers)
            except (socket.gaierror, ValueError):
                return (json.dumps({
                    "status": "error",
                    "message": "Could not resolve image URL hostname"
                }), 400, headers)

            import urllib.request
            with urllib.request.urlopen(image_url, timeout=15) as resp:
                image_bytes = resp.read()
                image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")
                # Guess media type from URL
                if image_url.lower().endswith(".jpg") or image_url.lower().endswith(".jpeg"):
                    media_type = "image/jpeg"
                elif image_url.lower().endswith(".webp"):
                    media_type = "image/webp"

        # ── Step 1: Extract receipt data with Claude Vision ──
        print(f"[{datetime.now().isoformat()}] Extracting receipt...")
        receipt_data = extract_receipt(
            image_base64=image_base64,
            media_type=media_type
        )
        print(f"  → Extracted {len(receipt_data.get('items', []))} items "
              f"from {receipt_data.get('merchant', 'unknown')}")

        # ── Step 2: Map ingredients to canonical names ──
        print("  → Mapping ingredients...")
        aliases = load_aliases()
        mapped_receipt = map_receipt_items(receipt_data, aliases)
        stats = mapped_receipt.get("_mapping_stats", {})
        print(f"  → Mapped: {stats.get('mapped', 0)}, "
              f"Unmapped: {stats.get('unmapped', 0)}")

        # ── Step 3: Write to Google Sheets ──
        print("  → Writing to Purchases Database...")
        service = get_sheets_service()
        append_result = append_receipt_to_sheet(
            SPREADSHEET_ID, mapped_receipt, source=source, service=service
        )
        print(f"  → Appended {append_result['rows_appended']} rows")

        # ── Step 4: Recompute recipe costs with updated prices ──
        print("  → Computing updated recipe costs...")
        recipe_costs = compute_recipe_costs(SPREADSHEET_ID, service=service)

        # ── Build response ──
        response = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "receipt_id": append_result["receipt_id"],
            "merchant": receipt_data.get("merchant"),
            "date": receipt_data.get("date"),
            "items_extracted": len(receipt_data.get("items", [])),
            "items_mapped": stats.get("mapped", 0),
            "items_unmapped": stats.get("unmapped", 0),
            "subtotal": receipt_data.get("subtotal"),
            "tax": receipt_data.get("tax"),
            "total": receipt_data.get("total"),
            "rows_appended": append_result["rows_appended"],
            "recipe_costs": recipe_costs,
            "items": [
                {
                    "raw": item.get("raw_description", ""),
                    "canonical": item.get("canonical_name", ""),
                    "category": item.get("category", ""),
                    "qty": item.get("quantity"),
                    "unit": item.get("unit"),
                    "unit_price": item.get("unit_price"),
                    "total": item.get("total_price"),
                }
                for item in mapped_receipt.get("items", [])
            ],
        }

        print(f"  ✓ Complete! Receipt {append_result['receipt_id']}")
        return (json.dumps(response, indent=2, default=str), 200, headers)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"  ✗ Error: {error_msg}")
        traceback.print_exc()
        return (json.dumps({
            "status": "error",
            "message": error_msg,
            "timestamp": datetime.now().isoformat(),
        }), 500, headers)


# ---------------------------------------------------------------------------
# Local testing support
# ---------------------------------------------------------------------------
def test_local(image_path: str, spreadsheet_id: str = None):
    """Run the full pipeline locally for testing."""
    from pathlib import Path

    global SPREADSHEET_ID
    if spreadsheet_id:
        SPREADSHEET_ID = spreadsheet_id

    # Read image
    with open(image_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    media_type = {".png": "image/png", ".jpg": "image/jpeg",
                  ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")

    # Step 1: Extract
    print("=" * 60)
    print(f"Testing pipeline with: {image_path}")
    print("=" * 60)

    print("\n[1/4] Extracting receipt with Claude Vision...")
    receipt_data = extract_receipt(image_base64=img_b64, media_type=media_type)
    print(f"  Merchant: {receipt_data.get('merchant')}")
    print(f"  Date: {receipt_data.get('date')}")
    print(f"  Items: {len(receipt_data.get('items', []))}")
    total_val = receipt_data.get('total')
    print(f"  Total: ${total_val:.2f}" if total_val is not None else "  Total: N/A")

    # Step 2: Map
    print("\n[2/4] Mapping ingredients...")
    aliases = load_aliases()
    mapped = map_receipt_items(receipt_data, aliases)
    stats = mapped.get("_mapping_stats", {})
    print(f"  Mapped: {stats['mapped']}/{stats['total_items']}")

    for item in mapped["items"]:
        status = "✓" if not item.get("canonical_name", "").startswith(UNMAPPED_PREFIX) else "✗"
        print(f"    {status} {item.get('raw_description', '')[:35]:<35s} "
              f"→ {item.get('canonical_name', ''):<30s} "
              f"${item.get('total_price', 0):>8.2f}")

    # Step 3: Write to Sheets (only if spreadsheet_id provided)
    if SPREADSHEET_ID:
        print(f"\n[3/4] Writing to Google Sheet {SPREADSHEET_ID}...")
        service = get_sheets_service()
        result = append_receipt_to_sheet(SPREADSHEET_ID, mapped, source="test", service=service)
        print(f"  Appended {result['rows_appended']} rows")

        print("\n[4/4] Computing recipe costs...")
        costs = compute_recipe_costs(SPREADSHEET_ID, service=service)
        for recipe in costs:
            print(f"  {recipe['product']:<25s} "
                  f"cost/roll: ${recipe['total_cost_per_roll']:.4f}  "
                  f"sell: ${recipe['frozen_price_per_roll']:.2f}  "
                  f"margin: {recipe['frozen_margin_pct']}%")
    else:
        print("\n[3/4] Skipping Sheets write (no SPREADSHEET_ID set)")
        print("[4/4] Skipping recipe cost computation")

    print("\n" + "=" * 60)
    print("Pipeline test complete!")
    print("=" * 60)

    return mapped


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py <image_path> [spreadsheet_id]")
        print("  Requires ANTHROPIC_API_KEY environment variable")
        print("  Spreadsheet write requires GOOGLE_SHEETS_CREDENTIALS_JSON env var")
        sys.exit(1)

    img_path = sys.argv[1]
    sheet_id = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("SPREADSHEET_ID")
    test_local(img_path, sheet_id)
