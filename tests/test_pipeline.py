"""
test_pipeline.py — End-to-end test of the receipt scanning pipeline.

Runs the full extract → map → (optionally) write flow using the mock receipt.
Does NOT require Google Sheets credentials unless --write flag is passed.

Usage:
    # Extract + map only (no Sheets write):
    ANTHROPIC_API_KEY=sk-... python tests/test_pipeline.py

    # Full pipeline including Sheets write:
    ANTHROPIC_API_KEY=sk-... python tests/test_pipeline.py --write <spreadsheet_id>
"""

import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from receipt_extractor import extract_receipt
from ingredient_mapper import map_receipt_items, load_aliases, UNMAPPED_PREFIX


def run_test(image_path: str, write_to_sheets: bool = False, spreadsheet_id: str = None):
    """Run the full pipeline test."""

    print("=" * 70)
    print("  SpringRoll House Receipt Scanner — Pipeline Test")
    print("=" * 70)

    # ── Step 1: Extract ──
    print(f"\n[1/3] Extracting receipt data from: {image_path}")
    print("      (Calling Claude Vision API...)\n")

    receipt_data = extract_receipt(image_path=image_path)

    print(f"  Merchant:  {receipt_data.get('merchant', 'N/A')}")
    print(f"  Date:      {receipt_data.get('date', 'N/A')}")
    print(f"  Items:     {len(receipt_data.get('items', []))}")
    print(f"  Subtotal:  ${(receipt_data.get('subtotal') or 0):.2f}")
    print(f"  Tax:       ${(receipt_data.get('tax') or 0):.2f}")
    print(f"  Total:     ${(receipt_data.get('total') or 0):.2f}")

    # ── Step 2: Map ──
    print(f"\n[2/3] Mapping items to canonical ingredient names...\n")

    aliases = load_aliases()
    mapped = map_receipt_items(receipt_data, aliases)
    stats = mapped.get("_mapping_stats", {})

    print(f"  {'Raw Description':<35s} {'Canonical Name':<30s} {'Cat':<12s} {'Total':>10s}")
    print(f"  {'─' * 35} {'─' * 30} {'─' * 12} {'─' * 10}")

    for item in mapped["items"]:
        canonical = item.get("canonical_name", "???")
        is_unmapped = canonical.startswith(UNMAPPED_PREFIX)
        marker = "✗" if is_unmapped else "✓"
        print(f"  {marker} {item.get('raw_description', '')[:33]:<33s} "
              f"{canonical[:28]:<28s} "
              f"{item.get('category', '')[:10]:<10s} "
              f"${item.get('total_price', 0):>8.2f}")

    print(f"\n  Summary: {stats['mapped']}/{stats['total_items']} mapped, "
          f"{stats['unmapped']} unmapped")

    # ── Step 3: Write to Sheets ──
    if write_to_sheets and spreadsheet_id:
        print(f"\n[3/3] Writing to Google Sheet: {spreadsheet_id}")
        from sheets_client import append_receipt_to_sheet, compute_recipe_costs, get_sheets_service

        service = get_sheets_service()
        result = append_receipt_to_sheet(spreadsheet_id, mapped, source="test", service=service)
        print(f"  ✓ Appended {result['rows_appended']} rows (Receipt ID: {result['receipt_id']})")

        print(f"\n  Updated Recipe Costs & Margins:")
        costs = compute_recipe_costs(spreadsheet_id, service=service)
        
        # Print detailed cost breakdown for each product
        print(f"\n  {'Product':<20s} {'Ingredient':>10s} {'Labor':>8s} {'Overhead':>9s} {'Total':>8s} "
              f"{'Frozen Margin':>13s} {'Cooked Margin':>15s}")
        print(f"  {'─' * 20} {'─' * 10} {'─' * 8} {'─' * 9} {'─' * 8} {'─' * 13} {'─' * 15}")
        for c in costs:
            print(f"  {c['product']:<20s} ${c['ingredient_cost_per_roll']:>8.4f} "
                  f"${c['labor_cost_per_roll']:>6.4f} ${c['overhead_cost_per_roll']:>7.4f} "
                  f"${c['total_cost_per_roll']:>6.4f} "
                  f"{c['frozen_margin_pct']:>6.1f}% (${c['frozen_profit_per_roll']:>6.4f}) "
                  f"{c['cooked_margin_low_pct']:>6.1f}-{c['cooked_margin_high_pct']:>5.1f}%")
    else:
        print(f"\n[3/3] Skipped Sheets write (pass --write <spreadsheet_id> to enable)")

    # ── Save raw output for debugging ──
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "test_output.json")
    with open(output_path, "w") as f:
        json.dump(mapped, f, indent=2, default=str)
    print(f"\n  Full output saved to: {output_path}")

    print("\n" + "=" * 70)
    print("  Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    # Default to mock receipt
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_image = os.path.join(script_dir, "mock_receipt_restaurant_depot.png")

    image = default_image
    write = False
    sheet_id = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--write" and i + 1 < len(args):
            write = True
            sheet_id = args[i + 1]
            i += 2  # Skip both --write and its value
        elif not arg.startswith("--"):
            image = arg
            i += 1
        else:
            i += 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠ ANTHROPIC_API_KEY not set. Running in dry-run mode.\n")
        print("To run the full pipeline:")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        print(f"  python {__file__} [image_path] [--write spreadsheet_id]")
        sys.exit(1)

    run_test(image, write_to_sheets=write, spreadsheet_id=sheet_id)
