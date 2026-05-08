"""
gmail_watcher.py — Monitor a Gmail inbox for receipt photos and auto-process them.

This script runs as a secondary Cloud Function (or cron job) that:
  1. Checks the dedicated Gmail inbox for unprocessed emails with image attachments
  2. Downloads the image
  3. Calls the receipt extraction pipeline
  4. Labels the email as "Processed"

Setup:
  - Requires Gmail API credentials (OAuth2 or service account with domain-wide delegation)
  - Set GMAIL_CREDENTIALS_JSON env var to the credentials file path
  - Set RECEIPT_EMAIL to the monitored address (e.g., springrollhouse.receipts@gmail.com)

For V1, this can also be triggered manually:
    python gmail_watcher.py
"""

import os

from logger import get_logger
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from receipt_extractor import extract_receipt
from ingredient_mapper import map_receipt_items, load_aliases
from sheets_client import append_receipt_to_sheet, get_sheets_service

# Gmail API scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Label for processed receipts
logger = get_logger(__name__)

PROCESSED_LABEL = "Receipts/Processed"
FAILED_LABEL = "Receipts/Failed"
_MAX_FAILURES_PER_MESSAGE = 3


def get_gmail_service(credentials_path: str = None, token_path: str = None):
    """Authenticate with Gmail API using OAuth2 flow."""
    if credentials_path is None:
        credentials_path = os.environ.get(
            "GMAIL_CREDENTIALS_JSON",
            os.path.join(os.path.dirname(__file__), "config", "gmail_credentials.json")
        )
    if token_path is None:
        token_path = os.path.join(os.path.dirname(__file__), "config", "gmail_token.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_or_create_label(gmail_service, label_name: str) -> str:
    """Get or create a Gmail label, returns label ID."""
    results = gmail_service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])

    for label in labels:
        if label["name"] == label_name:
            return label["id"]

    # Create the label
    label_body = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created = gmail_service.users().labels().create(userId="me", body=label_body).execute()
    return created["id"]


def get_image_attachments(gmail_service, message_id: str) -> list:
    """Extract image attachments from a Gmail message, including nested multipart parts."""
    message = gmail_service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    attachments = []

    def _collect_parts(parts):
        """Recursively walk message parts to find image attachments."""
        for part in parts:
            mime_type = part.get("mimeType", "")
            # Recurse into multipart containers
            if mime_type.startswith("multipart/"):
                _collect_parts(part.get("parts", []))
                continue
            filename = part.get("filename", "")
            if mime_type.startswith("image/"):
                attachment_id = part.get("body", {}).get("attachmentId")
                if attachment_id:
                    att = gmail_service.users().messages().attachments().get(
                        userId="me", messageId=message_id, id=attachment_id
                    ).execute()
                    data = att.get("data", "")
                    # Gmail API returns URL-safe base64
                    data = data.replace("-", "+").replace("_", "/")
                    attachments.append({
                        "filename": filename,
                        "media_type": mime_type,
                        "base64_data": data,
                    })

    payload = message.get("payload", {})
    top_parts = payload.get("parts", [])
    if top_parts:
        _collect_parts(top_parts)
    else:
        # Single-part message — check the payload itself
        _collect_parts([payload])

    return attachments


def process_inbox(spreadsheet_id: str = None, max_messages: int = 10):
    """
    Check Gmail inbox for new receipt images and process them.

    Looks for unread messages or messages without the 'Processed' label.
    """
    if spreadsheet_id is None:
        spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.error("SPREADSHEET_ID not provided and not set as an environment variable.")
        return 0

    gmail = get_gmail_service()
    sheets = get_sheets_service()
    aliases = load_aliases()

    # Get or create labels
    processed_label_id = get_or_create_label(gmail, PROCESSED_LABEL)
    failed_label_id = get_or_create_label(gmail, FAILED_LABEL)

    # Track per-message failure counts within this run
    failure_counts: dict[str, int] = {}

    # Search for unprocessed messages with attachments
    query = f"has:attachment -label:{PROCESSED_LABEL} -label:{FAILED_LABEL} newer_than:7d"
    results = gmail.users().messages().list(
        userId="me", q=query, maxResults=max_messages
    ).execute()

    messages = results.get("messages", [])
    logger.info("Found %d unprocessed messages with attachments", len(messages))

    processed_count = 0
    for msg_info in messages:
        msg_id = msg_info["id"]
        logger.info("Processing message %s...", msg_id)

        try:
            # Get image attachments
            attachments = get_image_attachments(gmail, msg_id)
            if not attachments:
                logger.info("  No image attachments in message %s, skipping", msg_id)
                continue

            for att in attachments:
                logger.info("  Processing: %s (%s)", att['filename'], att['media_type'])

                # Extract receipt data
                receipt_data = extract_receipt(
                    image_base64=att["base64_data"],
                    media_type=att["media_type"]
                )

                # Map ingredients
                mapped = map_receipt_items(receipt_data, aliases)
                stats = mapped.get("_mapping_stats", {})

                # Write to sheets
                result = append_receipt_to_sheet(
                    spreadsheet_id, mapped, source="email", service=sheets
                )

                logger.info("  %s — %d/%d items mapped, %d rows written",
                            receipt_data.get('merchant', 'Unknown'),
                            stats['mapped'], stats['total_items'],
                            result['rows_appended'])

            # Label message as processed
            gmail.users().messages().modify(
                userId="me", id=msg_id,
                body={"addLabelIds": [processed_label_id]}
            ).execute()
            processed_count += 1

        except Exception as e:
            failure_counts[msg_id] = failure_counts.get(msg_id, 0) + 1
            logger.error("Error processing message %s (attempt %d): %s",
                         msg_id, failure_counts[msg_id], e, exc_info=True)
            if failure_counts[msg_id] >= _MAX_FAILURES_PER_MESSAGE:
                logger.warning("Message %s failed %d times, labeling as Failed",
                               msg_id, failure_counts[msg_id])
                try:
                    gmail.users().messages().modify(
                        userId="me", id=msg_id,
                        body={"addLabelIds": [failed_label_id]}
                    ).execute()
                except Exception:
                    logger.error("Could not label message %s as Failed", msg_id)
            continue

    logger.info("Done! Processed %d/%d messages", processed_count, len(messages))
    return processed_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    sheet_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SPREADSHEET_ID")
    if not sheet_id:
        print("Usage: python gmail_watcher.py <spreadsheet_id>")
        print("  Or set SPREADSHEET_ID environment variable")
        sys.exit(1)

    process_inbox(sheet_id)
