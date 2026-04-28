"""Local development server — wraps main.py's scan_receipt as a Flask app."""
import os
from dotenv import load_dotenv
load_dotenv()

import json
from flask import Flask, request, make_response
from main import scan_receipt

app = Flask(__name__)

@app.route("/", methods=["POST", "OPTIONS"])
def handler():
    # Debug: log what we actually receive
    print(f"  [DEBUG] Content-Type: {request.content_type}")
    print(f"  [DEBUG] Data length: {len(request.get_data())}")
    raw = request.get_data(as_text=True)
    print(f"  [DEBUG] First 200 chars: {raw[:200]}")
    print(f"  [DEBUG] get_json result: {request.get_json(silent=True) is not None}")
    body, status, headers = scan_receipt(request)
    resp = make_response(body, status)
    for k, v in headers.items():
        resp.headers[k] = v
    return resp

@app.route("/scan", methods=["POST", "OPTIONS"])
def scan_direct():
    """Accept raw image bytes directly — no JSON wrapping needed.
    iOS Shortcuts: just POST the photo to /scan."""
    import base64 as b64
    from werkzeug.datastructures import ImmutableMultiDict

    if request.method == "OPTIONS":
        return "", 204, {"Access-Control-Allow-Origin": "*",
                         "Access-Control-Allow-Methods": "POST",
                         "Access-Control-Allow-Headers": "*"}

    from PIL import Image
    from io import BytesIO

    image_data = request.get_data()
    print(f"  [DEBUG /scan] Content-Type: {request.content_type}")
    print(f"  [DEBUG /scan] Data length: {len(image_data)} bytes")

    if not image_data or len(image_data) < 100:
        return json.dumps({"status": "error",
                           "message": f"No image data received. Content-Type: {request.content_type}, length: {len(image_data)}"}), 400

    # Detect actual image format from magic bytes
    if image_data[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"

    # Compress if over 4MB (Claude limit is 5MB)
    MAX_SIZE = 4 * 1024 * 1024
    if len(image_data) > MAX_SIZE:
        print(f"  [DEBUG /scan] Image too large ({len(image_data)} bytes), compressing...")
        img = Image.open(BytesIO(image_data))
        max_dim = 2048
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        image_data = buf.getvalue()
        media_type = "image/jpeg"
        print(f"  [DEBUG /scan] Compressed to {len(image_data)} bytes")
    img_b64 = b64.standard_b64encode(image_data).decode("utf-8")

    # Build a fake request object with the JSON body that scan_receipt expects
    class FakeRequest:
        method = "POST"
        headers = request.headers
        def get_json(self, silent=False):
            return {"image_base64": img_b64, "media_type": media_type, "source": "iphone"}
        def get_data(self, as_text=False):
            return json.dumps(self.get_json()) if as_text else b""

    body, status, headers = scan_receipt(FakeRequest())

    # Build a human-friendly plain-text summary for iOS Shortcuts
    try:
        data = json.loads(body)
        if data.get("status") == "success":
            lines = []
            lines.append(f"Receipt Scanned!")
            lines.append(f"Merchant: {data.get('merchant', 'Unknown')}")
            lines.append(f"Date: {data.get('date', 'Unknown')}")
            lines.append(f"Items: {data.get('items_extracted', 0)} extracted, {data.get('items_mapped', 0)} mapped")
            if data.get('items_unmapped', 0) > 0:
                lines.append(f"Unmapped: {data['items_unmapped']} (logged for review)")
            subtotal = data.get('subtotal')
            if subtotal:
                lines.append(f"Subtotal: ${subtotal:.2f}")
            lines.append(f"Rows written to Google Sheets: {data.get('rows_appended', 0)}")
            lines.append("")
            costs = data.get("recipe_costs", [])
            if costs:
                lines.append("Updated Recipe Costs:")
                for r in costs:
                    lines.append(f"  {r['product']}: ${r['total_cost_per_roll']:.3f}/roll — {r['frozen_margin_pct']}% margin")
            summary = "\n".join(lines)
        else:
            summary = f"Error: {data.get('message', 'Unknown error')}"
    except Exception:
        summary = body

    resp = make_response(summary, status)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    for k, v in headers.items():
        if k.lower() != "content-type":
            resp.headers[k] = v
    return resp

@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    print("Starting local receipt scanner on http://0.0.0.0:8080")
    print("  POST / with {image_base64, media_type, source}")
    app.run(host="0.0.0.0", port=8080, debug=False)
