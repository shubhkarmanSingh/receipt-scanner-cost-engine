"""Local development server — wraps main.py's scan_receipt as a Flask app.

Usage:
    python serve_local.py

The server listens on http://0.0.0.0:8080 and accepts:
  - POST /      — JSON body with {image_base64, media_type, source}
  - POST /scan  — Raw image bytes (for iOS Shortcuts)
  - GET  /health — Health check
"""
import os
from dotenv import load_dotenv
load_dotenv()

import json
from flask import Flask, request, make_response
from main import scan_receipt
from logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__)


@app.route("/", methods=["POST", "OPTIONS"])
@app.route("/scan", methods=["POST", "OPTIONS"])
def handler():
    """Handle both JSON and raw-image requests.

    main.py's scan_receipt() now detects raw image bytes automatically,
    so both / (JSON) and /scan (raw photo from iOS) go through the same path.
    """
    logger.debug("Request: %s %s Content-Type=%s Size=%d",
                 request.method, request.path, request.content_type, len(request.get_data()))

    body, status, headers = scan_receipt(request)
    resp = make_response(body, status)
    for k, v in headers.items():
        resp.headers[k] = v
    return resp


@app.route("/health")
def health():
    """Lightweight health check."""
    body, status, headers = scan_receipt(request)
    return make_response(body, status)


if __name__ == "__main__":
    logger.info("Starting local receipt scanner on http://0.0.0.0:8080")
    logger.info("  POST /      — JSON {image_base64, media_type, source}")
    logger.info("  POST /scan  — Raw image bytes (iOS Shortcuts)")
    logger.info("  GET  /health — Health check")
    app.run(host="0.0.0.0", port=8080, debug=False)
