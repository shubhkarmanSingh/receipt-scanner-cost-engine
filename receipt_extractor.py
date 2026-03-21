"""
receipt_extractor.py — Extract structured data from receipt images using Claude Vision API.

Sends a receipt image to Claude's vision model with a structured prompt tuned for
SpringRoll House's typical suppliers (Restaurant Depot, Costco, local wholesalers).
Returns a validated JSON object with merchant info and line items.
"""

import anthropic
import base64
import json
from pathlib import Path


# The extraction prompt — tuned for food service supplier receipts
EXTRACTION_PROMPT = """You are a receipt data extraction system for a food production business called SpringRoll House.
They buy ingredients in bulk from suppliers like Restaurant Depot, Costco Business Center, and local wholesalers.

Extract ALL line items from this receipt image. Return ONLY valid JSON with no other text.

Required JSON format:
{
  "merchant": "Store name exactly as printed",
  "merchant_address": "Full address if visible",
  "date": "YYYY-MM-DD format",
  "time": "HH:MM if visible, null otherwise",
  "receipt_id": "Receipt/transaction number if visible, null otherwise",
  "payment_method": "VISA/CASH/CHECK etc if visible, null otherwise",
  "items": [
    {
      "raw_description": "Exact text from receipt for this item",
      "name": "Clean, human-readable ingredient name",
      "quantity": 0.0,
      "unit": "lb/oz/sheet/pkg/ea/gal/cs/bag",
      "unit_price": 0.00,
      "total_price": 0.00
    }
  ],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00
}

Rules:
- Extract EVERY line item, even packaging supplies (bags, trays, labels)
- For quantity, use the number and unit as printed (e.g., 35 LB, 1200 SHT, 4 EA)
- Calculate unit_price as total_price / quantity when not explicitly shown
- If a price seems to be for a case/bulk unit, note the full description in raw_description
- Use null for any field you cannot determine from the receipt
- Ensure all prices are numbers (not strings), without dollar signs
- The date should always be YYYY-MM-DD even if printed differently on the receipt
"""


def extract_receipt(image_path: str = None, image_base64: str = None,
                    media_type: str = "image/png") -> dict:
    """
    Extract structured data from a receipt image using Claude Vision.

    Args:
        image_path: Path to a receipt image file (PNG, JPG, WEBP)
        image_base64: Base64-encoded image string (alternative to image_path)
        media_type: MIME type of the image (image/png, image/jpeg, image/webp)

    Returns:
        dict: Structured receipt data with merchant info and line items

    Raises:
        ValueError: If neither image_path nor image_base64 is provided
        anthropic.APIError: If the API call fails
    """
    if image_path is None and image_base64 is None:
        raise ValueError("Provide either image_path or image_base64")

    # Read and encode the image if path provided
    if image_path and image_base64 is None:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Receipt image not found: {image_path}")

        with open(path, "rb") as f:
            image_base64 = base64.standard_b64encode(f.read()).decode("utf-8")

        # Detect media type from extension
        ext = path.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        media_type = media_type_map.get(ext, media_type)

    # Call Claude Vision API
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    # Parse the response
    response_text = message.content[0].text

    # Clean up response — strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]  # Remove first line (e.g. "```json")
    response_text = response_text.strip()  # Strip before checking endswith
    if response_text.endswith("```"):
        response_text = response_text.rsplit("```", 1)[0]
    response_text = response_text.strip()

    try:
        receipt_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nResponse: {response_text[:500]}")

    # Validate required fields
    _validate_receipt(receipt_data)

    return receipt_data


def _validate_receipt(data: dict) -> None:
    """Basic validation of extracted receipt data."""
    required_fields = ["merchant", "items", "total"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        raise ValueError("Receipt must have at least one item")

    for i, item in enumerate(data["items"]):
        for field in ["name", "quantity", "total_price"]:
            if field not in item:
                raise ValueError(f"Item {i} missing required field: {field}")


# ---------------------------------------------------------------------------
# Local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python receipt_extractor.py <image_path>")
        print("  Requires ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    image_file = sys.argv[1]
    print(f"Extracting receipt data from: {image_file}")

    try:
        result = extract_receipt(image_path=image_file)
        print(json.dumps(result, indent=2))
        print(f"\n✓ Extracted {len(result['items'])} items from {result['merchant']}")
        print(f"  Total: ${result['total']:.2f}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
