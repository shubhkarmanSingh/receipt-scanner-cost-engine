"""
generate_pipeline_diagram.py — Creates a visual pipeline diagram for SpringRoll House Receipt Scanner.

Warm deli-inspired palette: golden wrappers, fresh greens, rich sauces, crispy browns.
"""

from PIL import Image, ImageDraw, ImageFont
import math
import os

WIDTH = 1800
HEIGHT = 1220
CARD_RADIUS = 16

# SpringRoll Deli palette
# Warm cream background, golden/amber accents, veggie greens, sauce reds
COLORS = {
    "bg": "#fdf6ec",              # warm parchment cream
    "header_bg": "#8b5e3c",       # warm roasted brown
    "header_text": "#fff8f0",
    "input_bg": "#fef9f0",        # light warm white
    "input_border": "#d4a24e",    # golden spring roll crust
    "process_bg": "#f0f7ed",      # fresh herb/veggie green tint
    "process_border": "#5a9a3c",  # fresh green (cabbage/taro leaf)
    "output_bg": "#fdf0e8",       # light peach/warm
    "output_border": "#b87a4b",   # warm terracotta
    "arrow": "#d4a24e",           # golden
    "arrow_head": "#b8862d",      # deeper gold
    "text_primary": "#2c1810",    # rich dark brown (soy sauce)
    "text_secondary": "#6b4c3b",  # warm medium brown
    "text_accent": "#a0522d",     # sienna brown accent
    "text_green": "#3d7a24",      # veggie green for step numbers
    "cost_bg": "#fdf5e6",         # old lace / warm
    "cost_border": "#d4a24e",     # golden
    "divider": "#e8d5b8",         # light tan
    "product_bg": "#f7eed7",      # light golden
    "product_border": "#d4a24e",  # golden crust
    "overhead_bg": "#f2e8d5",     # warm sand
    "cloud_bg": "#e8f4e2",        # very light green
    "cloud_border": "#7ab85e",    # spring green
    "badge_bg": "#a0522d",        # sienna badge
    "badge_text": "#ffffff",
    "footer_bg": "#3d2517",       # dark rich brown
    "footer_text": "#e8d5b8",
}


def get_font(size, bold=False):
    """Try to load a nice font, fall back to default."""
    font_paths = [
        "/System/Library/Fonts/SFCompact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    bold_paths = [
        "/System/Library/Fonts/SFCompact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    paths = bold_paths if bold else font_paths
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def rounded_rect(draw, xy, fill, outline=None, radius=16, width=2):
    """Draw a rounded rectangle."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_arrow(draw, start, end, color, width=3, head_size=12):
    """Draw an arrow from start to end."""
    draw.line([start, end], fill=color, width=width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    x1 = end[0] - head_size * math.cos(angle - math.pi / 6)
    y1 = end[1] - head_size * math.sin(angle - math.pi / 6)
    x2 = end[0] - head_size * math.cos(angle + math.pi / 6)
    y2 = end[1] - head_size * math.sin(angle + math.pi / 6)
    draw.polygon([end, (x1, y1), (x2, y2)], fill=COLORS["arrow_head"])


def draw_arrow_down(draw, start, end, color, width=3, head_size=12):
    """Draw a vertical arrow."""
    draw.line([start, end], fill=color, width=width)
    angle = math.pi / 2
    x1 = end[0] - head_size * math.cos(angle - math.pi / 6)
    y1 = end[1] - head_size * math.sin(angle - math.pi / 6)
    x2 = end[0] - head_size * math.cos(angle + math.pi / 6)
    y2 = end[1] - head_size * math.sin(angle + math.pi / 6)
    draw.polygon([end, (x1, y1), (x2, y2)], fill=COLORS["arrow_head"])


def draw_step_badge(draw, x, y, number, font):
    """Draw a circular step number badge."""
    r = 16
    draw.ellipse((x - r, y - r, x + r, y + r), fill=COLORS["text_green"])
    draw.text((x, y), str(number), fill="#ffffff", font=font, anchor="mm")


def draw_dashed_line(draw, start, end, color, dash_len=8, gap_len=5, width=2):
    """Draw a dashed line."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    pos = 0
    while pos < length:
        seg_end = min(pos + dash_len, length)
        sx = start[0] + ux * pos
        sy = start[1] + uy * pos
        ex = start[0] + ux * seg_end
        ey = start[1] + uy * seg_end
        draw.line([(sx, sy), (ex, ey)], fill=color, width=width)
        pos += dash_len + gap_len


def create_diagram():
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(img)

    font_title = get_font(34, bold=True)
    font_subtitle = get_font(18)
    font_heading = get_font(19, bold=True)
    font_body = get_font(15)
    font_small = get_font(13)
    font_label = get_font(14, bold=True)
    font_badge = get_font(16, bold=True)
    font_product_name = get_font(13, bold=True)
    font_product_detail = get_font(12)
    font_price = get_font(14, bold=True)

    # ── Title bar with warm gradient feel ──
    rounded_rect(draw, (0, 0, WIDTH, 75), fill=COLORS["header_bg"], radius=0)
    # Subtle lighter stripe at top
    draw.line([(0, 0), (WIDTH, 0)], fill="#a07050", width=3)
    draw.text((WIDTH // 2, 26), "SpringRoll House",
              fill=COLORS["header_text"], font=font_title, anchor="mm")
    draw.text((WIDTH // 2, 55), "Receipt Scanner  —  Full Pipeline",
              fill="#e8d0b8", font=font_subtitle, anchor="mm")

    # ── Column headers ──
    col_starts = [40, 460, 880, 1340]
    col_labels = ["INPUT", "EXTRACT & MAP", "WRITE & COMPUTE", "OUTPUT"]
    col_widths = [380, 380, 420, 420]
    col_colors = [COLORS["input_border"], COLORS["text_green"], COLORS["cost_border"], COLORS["text_accent"]]

    for x, label, w, c in zip(col_starts, col_labels, col_widths, col_colors):
        draw.text((x + w // 2, 102), label, fill=c, font=font_label, anchor="mm")
        draw.line([(x + 20, 117), (x + w - 20, 117)], fill=c, width=2)

    # =====================================================================
    # COLUMN 1: INPUT SOURCES
    # =====================================================================
    input_x = 50
    input_w = 360

    # iPhone Shortcut card
    y = 140
    rounded_rect(draw, (input_x, y, input_x + input_w, y + 145),
                 fill=COLORS["input_bg"], outline=COLORS["input_border"], radius=CARD_RADIUS, width=2)
    # Small icon area
    draw.rounded_rectangle((input_x + 15, y + 14, input_x + 43, y + 42),
                           radius=8, fill=COLORS["input_border"])
    draw.text((input_x + 29, y + 28), "P", fill="#fff", font=font_badge, anchor="mm")
    draw.text((input_x + 55, y + 18), "iPhone Shortcut",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((input_x + 20, y + 52), "Tap home screen icon",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y + 74), "Camera opens  ->  snap receipt",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y + 96), "Base64 encode + POST to API",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y + 120), "Push notification with results",
              fill=COLORS["text_secondary"], font=font_small)

    # Gmail Watcher card
    y2 = 310
    rounded_rect(draw, (input_x, y2, input_x + input_w, y2 + 120),
                 fill=COLORS["input_bg"], outline=COLORS["input_border"], radius=CARD_RADIUS, width=2)
    draw.rounded_rectangle((input_x + 15, y2 + 14, input_x + 43, y2 + 42),
                           radius=8, fill=COLORS["input_border"])
    draw.text((input_x + 29, y2 + 28), "E", fill="#fff", font=font_badge, anchor="mm")
    draw.text((input_x + 55, y2 + 18), "Gmail Watcher",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((input_x + 20, y2 + 50), "Monitors inbox for receipt photos",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y2 + 72), "Extracts image attachments",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y2 + 96), "Labels processed messages",
              fill=COLORS["text_secondary"], font=font_small)

    # HTTP API card
    y3 = 455
    rounded_rect(draw, (input_x, y3, input_x + input_w, y3 + 120),
                 fill=COLORS["input_bg"], outline=COLORS["input_border"], radius=CARD_RADIUS, width=2)
    draw.rounded_rectangle((input_x + 15, y3 + 14, input_x + 43, y3 + 42),
                           radius=8, fill=COLORS["input_border"])
    draw.text((input_x + 29, y3 + 28), "H", fill="#fff", font=font_badge, anchor="mm")
    draw.text((input_x + 55, y3 + 18), "Direct HTTP POST",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((input_x + 20, y3 + 50), "Base64 image or image URL",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y3 + 72), "API key authentication",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y3 + 96), "curl / any HTTP client",
              fill=COLORS["text_secondary"], font=font_small)

    # CLI card
    y4 = 600
    rounded_rect(draw, (input_x, y4, input_x + input_w, y4 + 95),
                 fill=COLORS["input_bg"], outline=COLORS["input_border"], radius=CARD_RADIUS, width=2)
    draw.rounded_rectangle((input_x + 15, y4 + 14, input_x + 43, y4 + 42),
                           radius=8, fill=COLORS["input_border"])
    draw.text((input_x + 29, y4 + 28), "C", fill="#fff", font=font_badge, anchor="mm")
    draw.text((input_x + 55, y4 + 18), "CLI  (Local Testing)",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((input_x + 20, y4 + 50), "python main.py receipt.jpg",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((input_x + 20, y4 + 74), "python tests/test_pipeline.py",
              fill=COLORS["text_secondary"], font=font_small)

    # ── Arrows from inputs converging to processing ──
    arrow_start_x = input_x + input_w + 8
    arrow_end_x = 472

    input_arrow_ys = [212, 370, 515, 647]
    target_y = 355
    for ay in input_arrow_ys:
        draw_arrow(draw, (arrow_start_x, ay), (arrow_end_x, target_y),
                   COLORS["arrow"], width=2, head_size=10)

    # =====================================================================
    # COLUMN 2: PROCESSING (inside Cloud Function wrapper)
    # =====================================================================
    proc_x = 480
    proc_w = 370

    # Cloud Function wrapper — dashed border, light green
    rounded_rect(draw, (proc_x - 12, 130, proc_x + proc_w + 12, 700),
                 fill=COLORS["cloud_bg"], outline=None, radius=CARD_RADIUS + 4)
    # Dashed outline
    for side in [
        ((proc_x - 12, 130), (proc_x + proc_w + 12, 130)),   # top
        ((proc_x + proc_w + 12, 130), (proc_x + proc_w + 12, 700)),  # right
        ((proc_x + proc_w + 12, 700), (proc_x - 12, 700)),   # bottom
        ((proc_x - 12, 700), (proc_x - 12, 130)),             # left
    ]:
        draw_dashed_line(draw, side[0], side[1], COLORS["cloud_border"], dash_len=10, gap_len=6, width=2)

    draw.text((proc_x + proc_w // 2, 150), "Google Cloud Function  (main.py)",
              fill=COLORS["text_green"], font=font_label, anchor="mm")

    # Step 1: Claude Vision
    s1_y = 172
    rounded_rect(draw, (proc_x, s1_y, proc_x + proc_w, s1_y + 135),
                 fill=COLORS["process_bg"], outline=COLORS["process_border"], radius=CARD_RADIUS, width=2)
    draw_step_badge(draw, proc_x + 25, s1_y + 25, 1, font_badge)
    draw.text((proc_x + 48, s1_y + 14), "Claude Vision API",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((proc_x + 48, s1_y + 38), "receipt_extractor.py",
              fill=COLORS["text_green"], font=font_small)
    draw.text((proc_x + 18, s1_y + 62), "Image  ->  structured JSON",
              fill=COLORS["text_primary"], font=font_body)
    draw.text((proc_x + 18, s1_y + 84), "Merchant, date, line items",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((proc_x + 18, s1_y + 106), "Qty, unit, unit price, total",
              fill=COLORS["text_secondary"], font=font_body)

    # Arrow down
    draw_arrow_down(draw, (proc_x + proc_w // 2, s1_y + 140),
                    (proc_x + proc_w // 2, s1_y + 162), COLORS["arrow"], width=2, head_size=9)

    # Step 2: Ingredient Mapper
    s2_y = 335
    rounded_rect(draw, (proc_x, s2_y, proc_x + proc_w, s2_y + 135),
                 fill=COLORS["process_bg"], outline=COLORS["process_border"], radius=CARD_RADIUS, width=2)
    draw_step_badge(draw, proc_x + 25, s2_y + 25, 2, font_badge)
    draw.text((proc_x + 48, s2_y + 14), "Ingredient Mapper",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((proc_x + 48, s2_y + 38), "ingredient_mapper.py",
              fill=COLORS["text_green"], font=font_small)
    draw.text((proc_x + 18, s2_y + 62), "33 canonical ingredients",
              fill=COLORS["text_primary"], font=font_body)
    draw.text((proc_x + 18, s2_y + 84), "Regex pattern matching",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((proc_x + 18, s2_y + 106), "Flags unmapped items for review",
              fill=COLORS["text_secondary"], font=font_body)

    # Arrow down to config
    draw_dashed_line(draw, (proc_x + proc_w // 2, s2_y + 140),
                     (proc_x + proc_w // 2, s2_y + 180), "#7ab85e", dash_len=5, gap_len=4, width=1)

    # Config card (subtle, supporting role)
    cfg_y = 530
    rounded_rect(draw, (proc_x + 20, cfg_y, proc_x + proc_w - 20, cfg_y + 90),
                 fill=COLORS["product_bg"], outline=COLORS["divider"], radius=12, width=1)
    draw.text((proc_x + 35, cfg_y + 10), "config/ingredients.json",
              fill=COLORS["input_border"], font=font_label)
    draw.text((proc_x + 35, cfg_y + 34), "9 product recipes + batch sizes",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((proc_x + 35, cfg_y + 56), "Overhead, labor, insurance, supplies",
              fill=COLORS["text_secondary"], font=font_body)

    # Dashed line from config up to mapper
    draw_dashed_line(draw, (proc_x + proc_w // 2, cfg_y),
                     (proc_x + proc_w // 2, s2_y + 135), COLORS["divider"], dash_len=6, gap_len=4, width=1)

    # ── Arrow from processing to write ──
    draw_arrow(draw, (proc_x + proc_w + 15, 400), (893, 400),
               COLORS["arrow"], width=3, head_size=12)

    # =====================================================================
    # COLUMN 3: WRITE & COMPUTE
    # =====================================================================
    write_x = 900
    write_w = 400

    # Step 3: Sheets Writer
    s3_y = 140
    rounded_rect(draw, (write_x, s3_y, write_x + write_w, s3_y + 150),
                 fill=COLORS["cost_bg"], outline=COLORS["cost_border"], radius=CARD_RADIUS, width=2)
    draw_step_badge(draw, write_x + 25, s3_y + 25, 3, font_badge)
    draw.text((write_x + 48, s3_y + 14), "Google Sheets Writer",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((write_x + 48, s3_y + 38), "sheets_client.py",
              fill=COLORS["text_green"], font=font_small)
    draw.text((write_x + 18, s3_y + 62), "Appends to Purchases tab (11 cols)",
              fill=COLORS["text_primary"], font=font_body)
    draw.text((write_x + 18, s3_y + 84), "Duplicate receipt detection",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((write_x + 18, s3_y + 106), "Unmapped items  ->  separate tab",
              fill=COLORS["text_secondary"], font=font_body)
    draw.text((write_x + 18, s3_y + 128), "Auto-formats headers & borders",
              fill=COLORS["text_secondary"], font=font_small)

    # Arrow down
    draw_arrow_down(draw, (write_x + write_w // 2, s3_y + 155),
                    (write_x + write_w // 2, s3_y + 195), COLORS["arrow"], width=2, head_size=9)

    # Step 4: Cost Calculator
    s4_y = 340
    rounded_rect(draw, (write_x, s4_y, write_x + write_w, s4_y + 185),
                 fill=COLORS["cost_bg"], outline=COLORS["cost_border"], radius=CARD_RADIUS, width=2)
    draw_step_badge(draw, write_x + 25, s4_y + 25, 4, font_badge)
    draw.text((write_x + 48, s4_y + 14), "Cost Breakdown Engine",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((write_x + 48, s4_y + 38), "compute_recipe_costs()",
              fill=COLORS["text_green"], font=font_small)

    # Cost layers with colored bullets
    layers = [
        ("Ingredient cost", "latest prices x recipe qty", COLORS["text_green"]),
        ("+ Labor cost", "$35,700/mo  /  200K rolls", COLORS["input_border"]),
        ("+ Overhead", "$6,168/mo fixed costs", COLORS["input_border"]),
        ("+ Insurance", "$3,550/mo", COLORS["input_border"]),
        ("+ Supplies", "$979/mo", COLORS["input_border"]),
    ]
    ly = s4_y + 62
    for label, detail, bullet_color in layers:
        # Small dot
        draw.ellipse((write_x + 20, ly + 4, write_x + 28, ly + 12), fill=bullet_color)
        draw.text((write_x + 34, ly), label, fill=COLORS["text_primary"], font=font_body)
        draw.text((write_x + 200, ly), detail, fill=COLORS["text_secondary"], font=font_small)
        ly += 23

    # Total line
    draw.line([(write_x + 20, ly + 2), (write_x + write_w - 20, ly + 2)],
              fill=COLORS["divider"], width=1)
    draw.text((write_x + 34, ly + 6), "= Total cost per roll",
              fill=COLORS["text_accent"], font=font_label)

    # Arrow down
    draw_arrow_down(draw, (write_x + write_w // 2, s4_y + 190),
                    (write_x + write_w // 2, s4_y + 218), COLORS["arrow"], width=2, head_size=9)

    # Step 5: Margin Calculator
    s5_y = 560
    rounded_rect(draw, (write_x, s5_y, write_x + write_w, s5_y + 120),
                 fill=COLORS["cost_bg"], outline=COLORS["cost_border"], radius=CARD_RADIUS, width=2)
    draw_step_badge(draw, write_x + 25, s5_y + 25, 5, font_badge)
    draw.text((write_x + 48, s5_y + 14), "Margin Calculator",
              fill=COLORS["text_primary"], font=font_heading)
    draw.text((write_x + 18, s5_y + 45), "Frozen wholesale margins",
              fill=COLORS["text_primary"], font=font_body)
    draw.text((write_x + 18, s5_y + 67), "Cooked retail margins (low / high)",
              fill=COLORS["text_primary"], font=font_body)
    draw.text((write_x + 18, s5_y + 92), "Profit per roll for each channel",
              fill=COLORS["text_secondary"], font=font_body)

    # ── Arrow from write to output ──
    draw_arrow(draw, (write_x + write_w + 15, 400), (1353, 400),
               COLORS["arrow"], width=3, head_size=12)

    # =====================================================================
    # COLUMN 4: OUTPUT
    # =====================================================================
    out_x = 1360
    out_w = 400

    # Google Sheets
    o1_y = 140
    rounded_rect(draw, (out_x, o1_y, out_x + out_w, o1_y + 170),
                 fill=COLORS["output_bg"], outline=COLORS["output_border"], radius=CARD_RADIUS, width=2)
    draw.text((out_x + 18, o1_y + 14), "Google Sheets Database",
              fill=COLORS["text_primary"], font=font_heading)

    tabs = [
        ("Purchases", "all line items"),
        ("Latest Prices", "per ingredient"),
        ("Recipe Costs", "cost/roll breakdown"),
        ("Margins", "profit per product"),
        ("Unmapped Items", "for review"),
    ]
    ty = o1_y + 44
    for tab_name, tab_desc in tabs:
        draw.text((out_x + 25, ty), tab_name, fill=COLORS["text_accent"], font=font_label)
        draw.text((out_x + 160, ty), tab_desc, fill=COLORS["text_secondary"], font=font_small)
        ty += 24

    # JSON Response
    o2_y = 335
    rounded_rect(draw, (out_x, o2_y, out_x + out_w, o2_y + 165),
                 fill=COLORS["output_bg"], outline=COLORS["output_border"], radius=CARD_RADIUS, width=2)
    draw.text((out_x + 18, o2_y + 14), "API JSON Response",
              fill=COLORS["text_primary"], font=font_heading)

    fields = [
        "receipt_id, merchant, date",
        "items_mapped / items_unmapped",
        "Per-item: canonical name, cost",
        "recipe_costs[] with full breakdown",
        "frozen + cooked margins",
    ]
    fy = o2_y + 44
    for field in fields:
        draw.ellipse((out_x + 22, fy + 4, out_x + 30, fy + 12),
                     fill=COLORS["input_border"])
        draw.text((out_x + 38, fy), field, fill=COLORS["text_secondary"], font=font_body)
        fy += 24

    # iPhone Notification
    o3_y = 525
    rounded_rect(draw, (out_x, o3_y, out_x + out_w, o3_y + 100),
                 fill=COLORS["output_bg"], outline=COLORS["output_border"], radius=CARD_RADIUS, width=2)
    draw.text((out_x + 18, o3_y + 14), "iPhone Notification",
              fill=COLORS["text_primary"], font=font_heading)
    # Simulated notification bubble
    rounded_rect(draw, (out_x + 18, o3_y + 44, out_x + out_w - 18, o3_y + 88),
                 fill="#f5ebe0", outline=COLORS["text_accent"], radius=10, width=1)
    draw.text((out_x + 30, o3_y + 50), "Receipt Scanned",
              fill=COLORS["text_accent"], font=font_label)
    draw.text((out_x + 30, o3_y + 68), "12 items mapped to ingredients",
              fill=COLORS["text_secondary"], font=font_small)

    # =====================================================================
    # BOTTOM: Products Bar
    # =====================================================================
    bar_y = 750
    draw.line([(40, bar_y), (WIDTH - 40, bar_y)], fill=COLORS["divider"], width=2)

    # Section title with decorative dots
    draw.ellipse((WIDTH // 2 - 130, bar_y + 13, WIDTH // 2 - 122, bar_y + 21),
                 fill=COLORS["input_border"])
    draw.text((WIDTH // 2, bar_y + 17), "9 PRODUCTS TRACKED",
              fill=COLORS["input_border"], font=font_label, anchor="mm")
    draw.ellipse((WIDTH // 2 + 118, bar_y + 13, WIDTH // 2 + 126, bar_y + 21),
                 fill=COLORS["input_border"])

    products = [
        ("Lg Vegetable", "1.5x5", "1200", "$0.76"),
        ("Sm Vegetable", "1x4", "1500", "$0.72"),
        ("Lg Chicken", "1.5x5", "1200", "$0.76"),
        ("Sm Chicken", "1x4", "1500", "$0.74"),
        ("Lg Pork", "1.5x5", "1200", "$0.76"),
        ("Sm Pork", "1x4", "1500", "$0.74"),
        ("Taro", "1x4", "1500", "$0.72"),
        ("Shrimp", "1x4", "1500", "$0.88"),
        ("Pork&Shrimp", "1x4", "1500", "$0.80"),
    ]

    px = 50
    pw = (WIDTH - 100) // 9
    for name, size, batch, price in products:
        rounded_rect(draw, (px, bar_y + 38, px + pw - 10, bar_y + 130),
                     fill=COLORS["product_bg"], outline=COLORS["product_border"],
                     radius=12, width=1)
        draw.text((px + (pw - 10) // 2, bar_y + 55), name,
                  fill=COLORS["text_primary"], font=font_product_name, anchor="mm")
        draw.text((px + (pw - 10) // 2, bar_y + 75), f"{size}  |  {batch}",
                  fill=COLORS["text_secondary"], font=font_product_detail, anchor="mm")
        # Price in a warm pill
        pill_w = 70
        pill_x = px + (pw - 10) // 2 - pill_w // 2
        rounded_rect(draw, (pill_x, bar_y + 92, pill_x + pill_w, bar_y + 112),
                     fill=COLORS["input_border"], outline=None, radius=10)
        draw.text((px + (pw - 10) // 2, bar_y + 102), f"{price}/roll",
                  fill="#ffffff", font=font_product_detail, anchor="mm")
        px += pw

    # ── Bottom bar: overhead summary ──
    bar2_y = bar_y + 150
    draw.line([(40, bar2_y), (WIDTH - 40, bar2_y)], fill=COLORS["divider"], width=2)

    draw.ellipse((WIDTH // 2 - 180, bar2_y + 13, WIDTH // 2 - 172, bar2_y + 21),
                 fill=COLORS["text_accent"])
    draw.text((WIDTH // 2, bar2_y + 17), "OVERHEAD MODEL   (200,000 rolls/month)",
              fill=COLORS["text_accent"], font=font_label, anchor="mm")
    draw.ellipse((WIDTH // 2 + 168, bar2_y + 13, WIDTH // 2 + 176, bar2_y + 21),
                 fill=COLORS["text_accent"])

    overhead_items = [
        ("Labor", "$35,700/mo", "$0.1785/roll", False),
        ("Fixed Overhead", "$6,168/mo", "$0.0308/roll", False),
        ("Insurance", "$3,550/mo", "$0.0178/roll", False),
        ("Supplies", "$979/mo", "$0.0049/roll", False),
        ("TOTAL", "Non-Ingredient", "$0.2320/roll", True),
    ]

    ox = 120
    ow = (WIDTH - 240) // 5
    for label, monthly, per_roll, is_total in overhead_items:
        if is_total:
            # Accent pill for total
            rounded_rect(draw, (ox + 10, bar2_y + 36, ox + ow - 10, bar2_y + 104),
                         fill=COLORS["badge_bg"], outline=None, radius=12)
            draw.text((ox + ow // 2, bar2_y + 50), label,
                      fill="#ffffff", font=font_label, anchor="mm")
            draw.text((ox + ow // 2, bar2_y + 68), monthly,
                      fill="#e8d0b8", font=font_small, anchor="mm")
            draw.text((ox + ow // 2, bar2_y + 86), per_roll,
                      fill="#ffffff", font=font_price, anchor="mm")
        else:
            rounded_rect(draw, (ox + 10, bar2_y + 36, ox + ow - 10, bar2_y + 104),
                         fill=COLORS["overhead_bg"], outline=COLORS["divider"], radius=12, width=1)
            draw.text((ox + ow // 2, bar2_y + 50), label,
                      fill=COLORS["text_primary"], font=font_body, anchor="mm")
            draw.text((ox + ow // 2, bar2_y + 68), monthly,
                      fill=COLORS["text_secondary"], font=font_small, anchor="mm")
            draw.text((ox + ow // 2, bar2_y + 86), per_roll,
                      fill=COLORS["input_border"], font=font_price, anchor="mm")
        ox += ow

    # ── Footer ──
    rounded_rect(draw, (0, HEIGHT - 40, WIDTH, HEIGHT), fill=COLORS["footer_bg"], radius=0)
    draw.text((WIDTH // 2, HEIGHT - 20),
              "SpringRoll House Deli   |   9 employees   |   200,000 rolls/month   |   ~$0.01-0.03 per receipt scan",
              fill=COLORS["footer_text"], font=font_small, anchor="mm")

    # Save
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_diagram.png")
    img.save(output_path, "PNG", quality=95)
    print(f"Pipeline diagram saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    create_diagram()
