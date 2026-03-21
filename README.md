# SpringRoll House Receipt Scanner

AI-powered receipt scanning pipeline for SpringRoll House Deli. Extracts ingredient purchases from receipt photos using Claude Vision, maps them to canonical ingredient names, writes to a Google Sheets database, and auto-updates unit costs per spring roll.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   INPUT CHANNELS    │     │    PROCESSING        │     │    OUTPUT           │
│                     │     │                      │     │                     │
│  📸 Phone photo     │────▶│  Claude Vision API   │────▶│  Google Sheets      │
│     (text/email)    │     │  (receipt_extractor)  │     │  "Purchases" tab    │
│                     │     │                      │     │                     │
│  📧 Supplier email  │────▶│  Ingredient Mapper   │────▶│  "Latest Prices"    │
│     (auto-parsed)   │     │  (ingredient_mapper)  │     │  (auto-calculated)  │
│                     │     │                      │     │                     │
│  📄 CSV export      │────▶│  Sheets Client       │────▶│  "Recipe Costs"     │
│     (Restaurant     │     │  (sheets_client)      │     │  (cost/roll, margin)│
│      Depot portal)  │     │                      │     │                     │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
                                      │
                                      ▼
                            ┌──────────────────────┐
                            │  Google Cloud         │
                            │  Function (main.py)   │
                            │  HTTP-triggered        │
                            └──────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/) (~$0.01-0.03 per receipt)
- A Google Cloud project with Sheets API enabled
- A Google Cloud service account (free)

### 1. Clone and install

```bash
git clone <repo-url>
cd springroll-receipt-scanner
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### 2. Set up Google Sheets

**Create the spreadsheet:**
1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet
2. Name it "SpringRoll House — Purchases Database"
3. Copy the spreadsheet ID from the URL (the long string between `/d/` and `/edit`)
4. Add it to your `.env` as `SPREADSHEET_ID`

**Create a service account:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable the Google Sheets API
4. Go to IAM & Admin → Service Accounts → Create Service Account
5. Download the JSON key file → save as `config/service_account.json`
6. Share your Google Sheet with the service account email (as Editor)

**Initialize the spreadsheet:**
```bash
python sheets_client.py init YOUR_SPREADSHEET_ID
```

This creates the tabs: Purchases, Latest Prices, Recipes, Margins, Unmapped Items.

### 3. Test locally with the mock receipt

```bash
# Generate the mock receipt image (if not already present)
python tests/generate_mock_receipt.py

# Run the full pipeline (extract + map, no Sheets write)
export ANTHROPIC_API_KEY=sk-ant-...
python tests/test_pipeline.py

# Run with Sheets write
python tests/test_pipeline.py --write YOUR_SPREADSHEET_ID
```

### 4. Test with a real receipt

```bash
# Just point it at any receipt photo
python main.py path/to/receipt.jpg YOUR_SPREADSHEET_ID
```

## File Structure

```
springroll-receipt-scanner/
├── main.py                    # Cloud Function entry point (HTTP handler)
├── receipt_extractor.py       # Claude Vision API — image → structured JSON
├── ingredient_mapper.py       # Maps receipt text → canonical ingredient names
├── sheets_client.py           # Google Sheets read/write + recipe cost calculator
├── gmail_watcher.py           # Monitors Gmail inbox for receipt emails (V2)
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore
├── config/
│   ├── ingredients.json       # Ingredient aliases, recipes, and pricing
│   ├── service_account.json   # Google Cloud credentials (DO NOT COMMIT)
│   └── gmail_credentials.json # Gmail OAuth2 creds (DO NOT COMMIT)
└── tests/
    ├── generate_mock_receipt.py    # Creates a realistic mock receipt image
    ├── mock_receipt_restaurant_depot.png  # Generated mock receipt
    └── test_pipeline.py           # End-to-end pipeline test
```

## Deployment to Google Cloud Functions

```bash
# Deploy the HTTP-triggered function
gcloud functions deploy scan-receipt \
    --gen2 \
    --runtime python312 \
    --trigger-http \
    --allow-unauthenticated \
    --entry-point scan_receipt \
    --region us-west1 \
    --memory 512MB \
    --timeout 60s \
    --set-env-vars "ANTHROPIC_API_KEY=sk-ant-...,SPREADSHEET_ID=1abc..."

# Note: You'll also need to upload the service account credentials.
# Option A: Bundle config/service_account.json with the deployment
# Option B: Use Google Secret Manager (recommended for production)
```

**Calling the deployed function:**
```bash
# With base64 image
curl -X POST https://us-west1-YOUR-PROJECT.cloudfunctions.net/scan-receipt \
    -H "Content-Type: application/json" \
    -d '{
        "image_base64": "'$(base64 -i receipt.png)'",
        "media_type": "image/png",
        "source": "photo"
    }'
```

## iPhone Setup (iOS Shortcut)

Tony can scan receipts directly from his iPhone home screen — no app install needed. See **[ios_shortcut_guide.md](ios_shortcut_guide.md)** for step-by-step setup.

**How it works:** Tap shortcut → take photo → receipt is processed → notification with results.

The shortcut sends the photo to the Cloud Function as base64, which runs the full pipeline.

## How Tony Uses This (End-User Flow)

1. **Buy ingredients** at Restaurant Depot, Costco, etc.
2. **Tap "Scan Receipt"** on iPhone home screen (or share a photo from Camera Roll)
3. **Done!** The pipeline automatically:
   - Extracts every line item (ingredient, quantity, price)
   - Maps it to the correct ingredient in the cost model
   - Writes it to the Purchases Database
   - Updates the cost-per-roll for every product
   - Flags any unknown items for manual review

## Ingredient Mapping

The system maps raw receipt descriptions (like "GRD PORK 80/20 10LB CS") to canonical names (like "Pork") using pattern matching defined in `config/ingredients.json`.

Currently mapped ingredients:
- **Proteins:** Pork, Minced Chicken, Shrimp
- **Produce:** Carrot, Taro, Cabbage, Onion
- **Seasonings:** Garlic Powder, Salt, Sugar, Black Pepper, Chicken Flavor Bouillon, Mushroom Seasoning
- **Wrappers:** Large 12in, Small 8in, Wonton Wrappers
- **Starch:** Vermicelli
- **Supply:** Soybean Oil

Unmapped items (packaging, cleaning supplies, etc.) are logged to the "Unmapped Items" tab for review. To add new mappings, edit `config/ingredients.json`.

## Recipe Cost Model

Recipes are defined in `config/ingredients.json` under `product_recipes`. Each recipe specifies:
- Ingredients and quantities per batch
- Batch size (number of rolls)
- Wholesale price per roll

The system computes a full cost breakdown per roll:
- **Ingredient cost** = sum of (ingredient qty × latest unit price) ÷ batch size
- **Labor cost** = monthly labor ($35,700) ÷ monthly production (200,000 rolls)
- **Overhead cost** = monthly fixed overhead ($6,168) ÷ production
- **Insurance cost** = monthly insurance ($3,550) ÷ production
- **Supplies cost** = monthly supplies ($979) ÷ production
- **Total cost** = sum of all above
- **Margin** = (sell price − total cost) ÷ sell price

Margins are computed against both frozen wholesale and cooked retail prices.

Products currently modeled:
| Product | Size | Batch | Wholesale $/roll |
|---------|------|-------|------------------|
| Large Vegetable | 1.5"×5" | 1,200 | $0.76 |
| Small Vegetable | 1"×4" | 1,500 | $0.72 |
| Large Chicken | 1.5"×5" | 1,200 | $0.76 |
| Small Chicken | 1"×4" | 1,500 | $0.74 |
| Large Pork | 1.5"×5" | 1,200 | $0.76 |
| Small Pork | 1"×4" | 1,500 | $0.74 |
| Taro | 1"×4" | 1,500 | $0.72 |
| Shrimp | 1"×4" | 1,500 | $0.88 |
| Pork & Shrimp | 1"×4" | 1,500 | $0.80 |

## Costs

- **Claude Vision API:** ~$0.01–0.03 per receipt image
- **Google Sheets API:** Free
- **Google Cloud Functions:** Free tier covers ~2M invocations/month
- **Estimated monthly cost for 100 receipts:** $1–3

## Future Enhancements (V2+)

- [ ] Gmail watcher for auto-processing emailed receipts
- [ ] Restaurant Depot CSV import
- [x] iOS Shortcut for one-tap receipt capture (see [ios_shortcut_guide.md](ios_shortcut_guide.md))
- [ ] Price trend alerts (ingredient cost spikes)
- [ ] Weekly purchase forecast based on sales patterns
- [ ] QuickBooks export integration
- [ ] Web dashboard for recipe cost visualization
