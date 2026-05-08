"""
main.py — Google Cloud Function entry point for the Receipt Scanner.

A configurable receipt scanning pipeline that works for any business.
Business-specific behavior (extraction prompt, item mapping, cost categories,
pricing tiers) is driven by config/business_config.json.

Deployment:
    gcloud functions deploy scan-receipt \
        --runtime python312 \
        --trigger-http \
        --entry-point scan_receipt \
        --set-env-vars ANTHROPIC_API_KEY=sk-...,SPREADSHEET_ID=1abc...,SCANNER_API_KEY=your-secret \
        --memory 512MB \
        --timeout 60s
"""

import functions_framework
import json
import os
import base64
import secrets
import uuid
from datetime import datetime

from config_loader import load_business_config
from receipt_extractor import extract_receipt
from ingredient_mapper import map_receipt_items, load_aliases, UNMAPPED_PREFIX
from sheets_client import (
    append_receipt_to_sheet,
    compute_recipe_costs,
    get_sheets_service,
)
from logger import get_logger

logger = get_logger(__name__)


# Environment variables
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # Used by anthropic SDK
API_KEY = os.environ.get("SCANNER_API_KEY")  # Optional: set to require auth on requests

# ── Startup validation ──
if not ANTHROPIC_API_KEY:
    logger.warning("ANTHROPIC_API_KEY is not set — receipt extraction will fail")
if not SPREADSHEET_ID:
    logger.warning("SPREADSHEET_ID is not set — Sheets writes will fail")
if not API_KEY:
    logger.warning("SCANNER_API_KEY is not set — endpoint is unauthenticated")

# Allowed image media types
ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Max image download size (10MB) — Claude's limit is ~5MB base64
MAX_IMAGE_DOWNLOAD = 10 * 1024 * 1024


# Max raw image size before compression (4MB — Claude limit is 5MB base64)
MAX_RAW_IMAGE = 4 * 1024 * 1024


def _detect_raw_image(request) -> dict | None:
    """Detect if a request contains raw image bytes (not JSON).

    iOS Shortcuts POSTs the photo as the raw body. We detect this by checking
    magic bytes at the start of the body. Returns a dict with image_base64
    and media_type, or None if the body is not a raw image.
    """
    content_type = getattr(request, 'content_type', '') or ''

    # If content type is explicitly JSON, skip raw detection
    if 'json' in content_type.lower():
        return None

    data = request.get_data()
    if not data or len(data) < 100:
        return None

    # Detect image format from magic bytes
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP':
        media_type = "image/webp"
    elif data[:3] == b'\xff\xd8\xff':
        media_type = "image/jpeg"
    else:
        # Not a recognizable image — let the JSON path handle it
        return None

    # Compress oversized images
    if len(data) > MAX_RAW_IMAGE:
        try:
            from PIL import Image
            from io import BytesIO
            logger.info("Raw image too large (%d bytes), compressing...", len(data))
            img = Image.open(BytesIO(data))
            max_dim = 2048
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            buf = BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            data = buf.getvalue()
            media_type = "image/jpeg"
            logger.info("Compressed to %d bytes", len(data))
        except Exception as e:
            logger.warning("Image compression failed: %s", e)
            # Continue with original data — Claude might still handle it

    return {
        "image_base64": base64.standard_b64encode(data).decode("utf-8"),
        "media_type": media_type,
    }


def _format_text_summary(response_data: dict) -> str:
    """Format a human-readable plain-text summary for iOS Shortcuts."""
    if response_data.get("status") != "success":
        return f"Error: {response_data.get('message', 'Unknown error')}"

    lines = [
        "Receipt Scanned!",
        f"Merchant: {response_data.get('merchant', 'Unknown')}",
        f"Date: {response_data.get('date', 'Unknown')}",
        f"Items: {response_data.get('items_extracted', 0)} extracted, "
        f"{response_data.get('items_mapped', 0)} mapped",
    ]
    if response_data.get('items_unmapped', 0) > 0:
        lines.append(f"Unmapped: {response_data['items_unmapped']} (logged for review)")
    subtotal = response_data.get('subtotal')
    if subtotal:
        lines.append(f"Subtotal: ${subtotal:.2f}")
    lines.append(f"Rows written to Google Sheets: {response_data.get('rows_appended', 0)}")
    lines.append("")
    costs = response_data.get("recipe_costs", [])
    if costs:
        lines.append("Updated Product Costs:")
        for r in costs:
            unit = r.get('unit_name', 'unit')
            lines.append(f"  {r['product']}: ${r['total_cost_per_unit']:.3f}/{unit} "
                         f"— {r.get('frozen_margin_pct', 0)}% margin")
    return "\n".join(lines)


@functions_framework.http
def scan_receipt(request):
    """
    Cloud Function entry point. Accepts an HTTP POST with a receipt image,
    extracts data using Claude Vision, maps ingredients, writes to Sheets,
    and returns updated recipe costs.

    Also handles GET /health for uptime monitoring.
    """
    # ── Health check endpoint ──
    if request.method == "GET" and getattr(request, 'path', '/') in ("/health", "/"):
        creds_path = os.environ.get(
            "GOOGLE_SHEETS_CREDENTIALS_JSON",
            os.path.join(os.path.dirname(__file__), "config", "service_account.json")
        )
        try:
            config = load_business_config()
            business_name = config.get("business", {}).get("name", "Unknown")
            config_loaded = True
        except (FileNotFoundError, ValueError):
            business_name = "Not configured"
            config_loaded = False

        checks = {
            "business_name": business_name,
            "config_loaded": config_loaded,
            "anthropic_key_configured": bool(ANTHROPIC_API_KEY),
            "spreadsheet_id_configured": bool(SPREADSHEET_ID),
            "scanner_api_key_configured": bool(API_KEY),
            "credentials_file_exists": os.path.exists(creds_path),
        }
        healthy = checks["anthropic_key_configured"] and checks["spreadsheet_id_configured"] and config_loaded
        return (json.dumps({
            "status": "healthy" if healthy else "degraded",
            "checks": checks,
        }), 200 if healthy else 503, {
            "Content-Type": "application/json",
            "X-Content-Type-Options": "nosniff",
        })

    # ── CORS headers for browser requests ──
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
        "X-Content-Type-Options": "nosniff",
    }

    # ── Request ID for log correlation ──
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])

    # ── API key authentication (if SCANNER_API_KEY is configured) ──
    if API_KEY:
        provided_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided_key, API_KEY):
            return (json.dumps({
                "status": "error",
                "message": "Invalid or missing API key. Set X-API-Key header."
            }), 401, headers)

    try:
        # ── Parse request ──
        # Detect if the request is raw image bytes (from iOS Shortcuts)
        # vs. JSON with base64 (from curl / programmatic callers)
        raw_image = _detect_raw_image(request)

        if raw_image:
            image_base64 = raw_image["image_base64"]
            media_type = raw_image["media_type"]
            image_url = None
            source = "iphone"
            logger.info("[%s] Received raw image (%s, %d bytes encoded)",
                        request_id, media_type, len(image_base64))
        else:
            request_json = request.get_json(silent=True)
            if not request_json:
                try:
                    request_json = json.loads(request.get_data(as_text=True))
                except (json.JSONDecodeError, TypeError):
                    request_json = {}
            image_base64 = request_json.get("image_base64")
            image_url = request_json.get("image_url")
            media_type = request_json.get("media_type", "image/png")
            source = request_json.get("source", "photo")

        if not image_base64 and not image_url:
            return (json.dumps({
                "status": "error",
                "message": "Provide 'image_base64' or 'image_url' in request body, "
                           "or POST raw image bytes.",
                "request_id": request_id,
            }), 400, headers)

        if media_type not in ALLOWED_MEDIA_TYPES:
            return (json.dumps({
                "status": "error",
                "message": f"Unsupported media type: {media_type}. "
                           f"Allowed: {', '.join(sorted(ALLOWED_MEDIA_TYPES))}",
                "request_id": request_id,
            }), 400, headers)

        if not SPREADSHEET_ID:
            return (json.dumps({
                "status": "error",
                "message": "SPREADSHEET_ID environment variable not set",
                "request_id": request_id,
            }), 500, headers)

        # If URL provided, fetch the image
        if image_url and not image_base64:
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            if parsed.scheme not in ("https",):
                return (json.dumps({
                    "status": "error",
                    "message": "Only https:// image URLs are allowed",
                    "request_id": request_id,
                }), 400, headers)
            # Block requests to private/internal IPs (check ALL resolved addresses)
            import socket
            import ipaddress
            try:
                resolved = socket.getaddrinfo(parsed.hostname, None)
                for result in resolved:
                    ip = ipaddress.ip_address(result[4][0])
                    if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                        return (json.dumps({
                            "status": "error",
                            "message": "URLs pointing to private/internal networks are not allowed",
                            "request_id": request_id,
                        }), 400, headers)
            except (socket.gaierror, ValueError):
                return (json.dumps({
                    "status": "error",
                    "message": "Could not resolve image URL hostname",
                    "request_id": request_id,
                }), 400, headers)

            import urllib.request
            with urllib.request.urlopen(image_url, timeout=15) as resp:
                chunks = []
                total_read = 0
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    total_read += len(chunk)
                    if total_read > MAX_IMAGE_DOWNLOAD:
                        return (json.dumps({
                            "status": "error",
                            "message": f"Image exceeds maximum download size "
                                       f"({MAX_IMAGE_DOWNLOAD // (1024*1024)}MB)",
                            "request_id": request_id,
                        }), 413, headers)
                    chunks.append(chunk)
                image_bytes = b"".join(chunks)
                image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")
                # Guess media type from URL
                if image_url.lower().endswith(".jpg") or image_url.lower().endswith(".jpeg"):
                    media_type = "image/jpeg"
                elif image_url.lower().endswith(".webp"):
                    media_type = "image/webp"

        # ── Load business config ──
        config = load_business_config()

        # ── Step 1: Extract receipt data with Claude Vision ──
        logger.info("[%s] Extracting receipt...", request_id)
        receipt_data = extract_receipt(
            image_base64=image_base64,
            media_type=media_type,
            config=config,
        )
        logger.info("[%s] Extracted %d items from %s", request_id,
                     len(receipt_data.get('items', [])),
                     receipt_data.get('merchant', 'unknown'))

        # ── Step 2: Map items to canonical names ──
        aliases = load_aliases()
        mapped_receipt = map_receipt_items(receipt_data, aliases)
        stats = mapped_receipt.get("_mapping_stats", {})
        logger.info("[%s] Mapped: %d, Unmapped: %d", request_id,
                     stats.get('mapped', 0), stats.get('unmapped', 0))

        # ── Step 3: Write to Google Sheets ──
        logger.info("[%s] Writing to Purchases Database...", request_id)
        service = get_sheets_service()
        append_result = append_receipt_to_sheet(
            SPREADSHEET_ID, mapped_receipt, source=source, service=service,
            config=config,
        )
        logger.info("[%s] Appended %d rows", request_id, append_result['rows_appended'])

        # ── Step 4: Recompute product costs with updated prices ──
        logger.info("[%s] Computing updated product costs...", request_id)
        recipe_costs = compute_recipe_costs(SPREADSHEET_ID, config=config, service=service)

        # ── Build response ──
        response = {
            "status": "success",
            "request_id": request_id,
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

        logger.info("[%s] Complete! Receipt %s", request_id, append_result['receipt_id'])

        # Return plain-text summary for iOS Shortcuts, JSON for everything else
        if raw_image:
            summary = _format_text_summary(response)
            text_headers = dict(headers)
            text_headers["Content-Type"] = "text/plain; charset=utf-8"
            return (summary, 200, text_headers)

        return (json.dumps(response, indent=2, default=str), 200, headers)

    except ValueError as e:
        # Client errors (bad input, duplicate receipt, validation failures)
        logger.warning("[%s] Client error: %s", request_id, e)
        error_body = {
            "status": "error",
            "request_id": request_id,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        if raw_image:
            return (f"Error: {e}", 400, {"Content-Type": "text/plain; charset=utf-8"})
        return (json.dumps(error_body), 400, headers)

    except Exception as e:
        # Server errors — log full details, return safe message to client
        logger.error("[%s] Internal error: %s", request_id,
                     f"{type(e).__name__}: {e}", exc_info=True)
        if raw_image:
            return (f"Error: Something went wrong. Ref: {request_id}",
                    500, {"Content-Type": "text/plain; charset=utf-8"})
        return (json.dumps({
            "status": "error",
            "request_id": request_id,
            "message": f"An internal error occurred. Reference ID: {request_id}",
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
