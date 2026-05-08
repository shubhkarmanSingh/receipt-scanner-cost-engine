# Receipt Scanner — Small Business Cost Intelligence

AI-powered receipt scanning pipeline for small businesses. Extracts purchases from receipt photos using Claude Vision, maps them to canonical item names, writes to a Google Sheets database, and auto-updates product costs and margins.

Configurable for any industry — no code changes needed.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   INPUT CHANNELS    │     │    PROCESSING        │     │    OUTPUT           │
│                     │     │                      │     │                     │
│  Phone photo        │────>│  Claude Vision API   │────>│  Google Sheets      │
│  (iOS Shortcut)     │     │  (receipt_extractor) │     │  "Purchases" tab    │
│                     │     │                      │     │                     │
│  Supplier email     │────>│  Item Mapper         │────>│  "Latest Prices"    │
│  (auto-parsed)      │     │  (ingredient_mapper) │     │  (auto-calculated)  │
│                     │     │                      │     │                     │
│  JSON / curl        │────>│  Sheets Client       │────>│  "Product Costs"    │
│                     │     │  (sheets_client)     │     │  (cost/unit, margin)│
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
                                      │
                                      v
                            ┌──────────────────────┐
                            │  Google Cloud        │
                            │  Function (main.py)  │
                            │  HTTP-triggered      │
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
cd receipt-scanner-cost-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### 2. Configure your business

Run the interactive setup wizard:

```bash
python setup_wizard.py
```

This walks you through:

- Business name and industry
- Item categories and aliases (what you buy)
- Products/recipes (what you make)
- Monthly overhead costs
- Pricing tiers (how you sell)

Takes about 10-15 minutes. You can also start from an industry template (restaurant, retail, or service).

To add items later:

```bash
python setup_wizard.py --add-item
```

### 3. Set up Google Sheets

**Create the spreadsheet:**

1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet
2. Copy the spreadsheet ID from the URL (the long string between `/d/` and `/edit`)
3. Add it to your `.env` as `SPREADSHEET_ID`

**Create a service account:**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable the Google Sheets API
4. Go to IAM & Admin > Service Accounts > Create Service Account
5. Download the JSON key file and save as `config/service_account.json`
6. Share your Google Sheet with the service account email (as Editor)

**Initialize the spreadsheet:**

```bash
python sheets_client.py init YOUR_SPREADSHEET_ID
```

### 4. Test locally

```bash
# Start the local dev server
python serve_local.py

# In another terminal, test with a receipt image
curl -X POST http://localhost:8080/scan --data-binary @receipt.jpg

# Or test the pipeline directly
python main.py path/to/receipt.jpg
```

### 5. Run tests

```bash
python -m pytest tests/ -v
```

## File Structure

```
receipt-scanner-cost-engine/
├── main.py                    # Cloud Function entry point (HTTP handler)
├── receipt_extractor.py       # Claude Vision API — image to structured JSON
├── ingredient_mapper.py       # Maps receipt text to canonical item names
├── sheets_client.py           # Google Sheets read/write + cost calculator
├── config_loader.py           # Business config loading and validation
├── setup_wizard.py            # Interactive business setup CLI
├── gmail_watcher.py           # Monitors Gmail inbox for receipt emails
├── serve_local.py             # Local Flask dev server
├── logger.py                  # Structured logging setup
├── deploy.sh                  # Google Cloud Functions deployment script
├── create_shortcut.py         # iOS Shortcut generator
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── config/
│   ├── business_config.json   # Your business config (gitignored)
│   ├── service_account.json   # Google Cloud credentials (gitignored)
│   └── templates/             # Industry starter templates
│       ├── restaurant.json
│       ├── retail.json
│       └── service.json
└── tests/
    ├── test_config.py         # Config loader tests
    ├── test_extractor.py      # Receipt extraction + prompt tests
    ├── test_mapper.py         # Item mapping tests
    └── test_security.py       # Security validation tests
```

## Deployment to Google Cloud Functions

Use the included deploy script:

```bash
./deploy.sh
# Or specify a project:
./deploy.sh --project my-gcp-project --region us-west1
```

Or deploy manually:

```bash
gcloud functions deploy scan-receipt \
    --gen2 \
    --runtime python312 \
    --trigger-http \
    --allow-unauthenticated \
    --entry-point scan_receipt \
    --region us-west1 \
    --memory 512MB \
    --timeout 120s \
    --set-env-vars "ANTHROPIC_API_KEY=...,SPREADSHEET_ID=..."
```

## iPhone Setup (iOS Shortcut)

Generate a shortcut that lets you scan receipts from your iPhone home screen:

```bash
python create_shortcut.py https://REGION-PROJECT.cloudfunctions.net/scan-receipt
```

AirDrop the generated `.shortcut` file to your iPhone. Tap to install.

**Flow:** Tap shortcut > take photo > receipt is processed > results shown.

## How It Works

1. **Scan a receipt** — take a photo, email it, or POST it to the API
2. **Claude Vision extracts** every line item (item, quantity, price)
3. **Item mapper** matches receipt text to your configured canonical names
4. **Sheets client** writes to your Purchases Database
5. **Cost engine** recomputes product costs using latest prices
6. **Unmapped items** are logged for review — add new aliases anytime

## Item Mapping

The system maps raw receipt descriptions (like "GRD PORK 80/20 10LB CS") to canonical names (like "Pork") using pattern matching defined in your business config.

Unmapped items are logged to the "Unmapped Items" tab for review. Add new mappings via the wizard or by editing `config/business_config.json`.

## Cost Model

The cost engine is fully configurable:

- **Item costs** = sum of (item qty x latest unit price) / batch size
- **Overhead costs** = each monthly cost category / monthly production
- **Total cost** = item costs + all overhead categories
- **Margins** = computed per pricing tier (wholesale, retail, etc.)

All overhead categories, pricing tiers, and product definitions are driven by your business config.

## Costs

- **Claude Vision API:** ~$0.01-0.03 per receipt image
- **Google Sheets API:** Free
- **Google Cloud Functions:** Free tier covers ~2M invocations/month
- **Estimated monthly cost for 100 receipts:** $1-3

## Security

- API key authentication (timing-safe comparison)
- SSRF prevention on image URL downloads
- Bounded image downloads (10MB cap)
- Media type allowlist (PNG, JPEG, WEBP, GIF)
- Safe error messages (no internal details leaked to clients)
- Request ID tracking for log correlation
- Business configs and credentials gitignored
