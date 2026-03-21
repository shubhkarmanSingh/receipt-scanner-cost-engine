"""Generate a realistic mock receipt image for testing the AI extraction pipeline."""

import os
import random
from PIL import Image, ImageDraw, ImageFont

def generate_mock_receipt(output_path="mock_receipt_restaurant_depot.png"):
    """Generate a receipt that mimics a Restaurant Depot purchase for SpringRoll House."""

    width = 640
    line_height = 28
    lines = [
        ("center", "RESTAURANT DEPOT #1247"),
        ("center", "1221 AURORA AVE N"),
        ("center", "SEATTLE, WA 98109"),
        ("center", "(206) 555-0192"),
        ("center", ""),
        ("center", "DATE: 03/04/2026  TIME: 09:23 AM"),
        ("center", "CASHIER: MIKE    REG: 04"),
        ("center", "MEMBER: SPRINGROLL HOUSE DELI"),
        ("center", "ACCT: ****4821"),
        ("center", "=" * 44),
        ("left",   ""),
        # Line items: description, qty, price
        ("item",   ("GRD PORK 80/20 10LB CS", "35 LB", "$70.00")),
        ("item",   ("MINCED CHICKEN BREAST", "40 LB", "$80.00")),
        ("item",   ("RAW SHRIMP 16/20 IQF", "25 LB", "$162.50")),
        ("item",   ("RICE PAPER WRAPPER 12IN", "1200 SHT", "$60.00")),
        ("item",   ("RICE PAPER WRAPPER 8IN", "1500 SHT", "$75.00")),
        ("item",   ("VERMICELLI RICE NOODLE", "8 PKG", "$10.00")),
        ("item",   ("FRESH CARROTS WHOLE 25LB", "23 LB", "$20.00")),
        ("item",   ("TARO ROOT", "35 LB", "$50.00")),
        ("item",   ("GREEN CABBAGE 50LB CS", "25 LB", "$25.00")),
        ("item",   ("YELLOW ONION 50LB BAG", "23 LB", "$20.00")),
        ("item",   ("GARLIC POWDER 5LB", "1 EA", "$12.99")),
        ("item",   ("SALT IODIZED 10LB", "1 EA", "$10.00")),
        ("item",   ("SUGAR GRANULATED 25LB", "1 EA", "$25.00")),
        ("item",   ("BLACK PEPPER GROUND 5LB", "1 EA", "$35.00")),
        ("item",   ("CHICKEN BOUILLON PWD 5LB", "1 EA", "$20.00")),
        ("item",   ("MUSHROOM SEASONING 1LB", "1 EA", "$5.50")),
        ("item",   ("FRESH GARLIC PEELED 5LB", "14 LB", "$28.00")),
        ("item",   ("SOYBEAN OIL 35LB CONT", "4 EA", "$139.96")),
        ("left",   ""),
        ("center", "-" * 44),
        ("right",  ("SUBTOTAL:", "$848.95")),
        ("right",  ("TAX (10.25%):", "$87.02")),
        ("center", "=" * 44),
        ("right",  ("TOTAL:", "$935.97")),
        ("center", ""),
        ("right",  ("VISA ****6411:", "$935.97")),
        ("center", ""),
        ("center", "ITEMS SOLD: 18"),
        ("center", ""),
        ("center", "THANK YOU FOR YOUR BUSINESS!"),
        ("center", "MEMBER SINCE: 2005"),
        ("center", ""),
        ("center", "*** KEEP RECEIPT FOR RETURNS ***"),
    ]

    # Calculate image height
    height = (len(lines) + 4) * line_height + 40
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Use default font (monospace-like)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
        font_bold = font

    y = 20
    margin = 30

    for line_type, content in lines:
        if line_type == "center":
            text = content
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            use_font = font_bold if "RESTAURANT DEPOT" in text or "TOTAL:" in text else font
            draw.text((x, y), text, fill="black", font=use_font)

        elif line_type == "left":
            draw.text((margin, y), content, fill="black", font=font)

        elif line_type == "item":
            desc, qty, price = content
            # Description on left
            draw.text((margin, y), desc, fill="black", font=font)
            y += line_height
            # Qty and price on same line, right-aligned
            qty_price = f"  {qty:>12s}  {price:>10s}"
            bbox = draw.textbbox((0, 0), qty_price, font=font)
            text_width = bbox[2] - bbox[0]
            draw.text((width - margin - text_width, y), qty_price, fill="black", font=font)

        elif line_type == "right":
            label, value = content
            text = f"{label:>30s} {value:>10s}"
            bbox = draw.textbbox((0, 0), text, font=font_bold if "TOTAL:" == label else font)
            text_width = bbox[2] - bbox[0]
            draw.text((width - margin - text_width, y), text, fill="black",
                       font=font_bold if "TOTAL:" == label else font)

        y += line_height

    # Add slight noise/texture to make it look more like a real scan
    pixels = img.load()
    for i in range(width):
        for j in range(height):
            r, g, b = pixels[i, j]
            noise = random.randint(-8, 8)
            pixels[i, j] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )

    img.save(output_path)
    print(f"Mock receipt saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output = os.path.join(script_dir, "mock_receipt_restaurant_depot.png")
    generate_mock_receipt(output)
