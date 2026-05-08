#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Deploy the Receipt Scanner to Google Cloud Functions
# =============================================================================
#
# Prerequisites:
#   1. gcloud CLI installed and authenticated (gcloud auth login)
#   2. A GCP project with Cloud Functions and Sheets APIs enabled
#   3. Environment variables set in .env (or pass them below)
#
# Usage:
#   ./deploy.sh                          # Deploy with defaults
#   ./deploy.sh --project my-project     # Specify GCP project
#
# After deployment:
#   1. Note the function URL printed at the end
#   2. Run: python create_shortcut.py <function-url>
#   3. AirDrop the signed shortcut to the iPhone
# =============================================================================

set -euo pipefail

# ── Load .env if present ──
if [ -f .env ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)
fi

# ── Configuration (override via environment or CLI flags) ──
GCP_PROJECT="${GCP_PROJECT:-}"
GCP_REGION="${GCP_REGION:-us-west1}"
FUNCTION_NAME="${FUNCTION_NAME:-scan-receipt}"
RUNTIME="python312"
MEMORY="512MB"
TIMEOUT="120s"
MAX_INSTANCES="3"

# Parse CLI flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project) GCP_PROJECT="$2"; shift 2 ;;
        --region)  GCP_REGION="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ── Validate required variables ──
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY is not set. Add it to .env or export it."
    exit 1
fi
if [ -z "${SPREADSHEET_ID:-}" ]; then
    echo "ERROR: SPREADSHEET_ID is not set. Add it to .env or export it."
    exit 1
fi

# ── Validate GCP project ──
if [ -z "$GCP_PROJECT" ]; then
    GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
fi
if [ -z "$GCP_PROJECT" ]; then
    echo "ERROR: No GCP project set. Run: gcloud config set project <project-id>"
    echo "  Or: ./deploy.sh --project <project-id>"
    exit 1
fi

# ── Validate service account credentials ──
CREDS_PATH="${GOOGLE_SHEETS_CREDENTIALS_JSON:-config/service_account.json}"
if [ ! -f "$CREDS_PATH" ]; then
    echo "ERROR: Service account credentials not found at: $CREDS_PATH"
    echo "  Download from GCP Console → IAM → Service Accounts → Keys"
    echo "  Save to config/service_account.json"
    exit 1
fi

# ── Build env vars string ──
ENV_VARS="ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},SPREADSHEET_ID=${SPREADSHEET_ID}"
if [ -n "${SCANNER_API_KEY:-}" ]; then
    ENV_VARS="${ENV_VARS},SCANNER_API_KEY=${SCANNER_API_KEY}"
fi

echo "========================================"
echo "  Deploying ${FUNCTION_NAME}"
echo "  Project: ${GCP_PROJECT}"
echo "  Region:  ${GCP_REGION}"
echo "  Runtime: ${RUNTIME}"
echo "  Memory:  ${MEMORY}"
echo "  Timeout: ${TIMEOUT}"
echo "========================================"
echo ""

# ── Deploy ──
gcloud functions deploy "$FUNCTION_NAME" \
    --project "$GCP_PROJECT" \
    --gen2 \
    --runtime "$RUNTIME" \
    --region "$GCP_REGION" \
    --trigger-http \
    --allow-unauthenticated \
    --entry-point scan_receipt \
    --memory "$MEMORY" \
    --timeout "$TIMEOUT" \
    --max-instances "$MAX_INSTANCES" \
    --set-env-vars "$ENV_VARS" \
    --source .

echo ""
echo "========================================"
echo "  Deployment complete!"
echo "========================================"

# ── Print the function URL ──
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
    --project "$GCP_PROJECT" \
    --region "$GCP_REGION" \
    --gen2 \
    --format="value(serviceConfig.uri)" 2>/dev/null || true)

if [ -n "$FUNCTION_URL" ]; then
    echo ""
    echo "Function URL: ${FUNCTION_URL}"
    echo ""
    echo "Next steps:"
    echo "  1. Test:  curl -X GET ${FUNCTION_URL}/health"
    echo "  2. Generate iOS Shortcut:"
    echo "     python create_shortcut.py ${FUNCTION_URL}"
    echo "  3. AirDrop ScanReceipt-signed.shortcut to the iPhone"
else
    echo ""
    echo "Could not retrieve function URL. Run:"
    echo "  gcloud functions describe ${FUNCTION_NAME} --region ${GCP_REGION} --gen2"
fi
