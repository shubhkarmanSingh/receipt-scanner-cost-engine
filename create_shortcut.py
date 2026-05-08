"""
Generate an Apple Shortcuts .shortcut file for the SpringRoll Receipt Scanner.

The shortcut takes a photo and POSTs the raw image bytes to the server.
Works with both Cloud Functions and local dev server.

Usage:
    python create_shortcut.py <cloud_function_url>
    python create_shortcut.py https://us-west1-myproject.cloudfunctions.net/scan-receipt

For local development:
    python create_shortcut.py http://localhost:8080
"""
import os
import plistlib
import subprocess
import sys
import uuid


def make_uuid():
    return str(uuid.uuid4()).upper()


def create_shortcut(server_url: str) -> bytes:
    photo_uuid = make_uuid()
    url_uuid = make_uuid()

    shortcut = {
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 4282601983,
            "WFWorkflowIconGlyphNumber": 59493,
        },
        "WFWorkflowClientVersion": "2302.0.4",
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowTypes": ["NCWidget", "WatchKit"],
        "WFWorkflowActions": [
            # 1. Take Photo
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.takephoto",
                "WFWorkflowActionParameters": {
                    "WFCameraCaptureShowPreview": True,
                    "UUID": photo_uuid,
                },
            },
            # 2. POST raw photo to /scan
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
                "WFWorkflowActionParameters": {
                    "WFURL": server_url.rstrip("/") + "/scan",
                    "WFHTTPMethod": "POST",
                    "WFHTTPBodyType": "File",
                    "WFRequestVariable": {
                        "Value": {
                            "Type": "ActionOutput",
                            "OutputUUID": photo_uuid,
                            "OutputName": "Photo",
                        },
                        "WFSerializationType": "WFTextTokenAttachment",
                    },
                    "UUID": url_uuid,
                },
            },
            # 3. Show the full response
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.showresult",
                "WFWorkflowActionParameters": {
                    "Text": {
                        "Value": {
                            "attachmentsByRange": {
                                "{0, 1}": {
                                    "Type": "ActionOutput",
                                    "OutputUUID": url_uuid,
                                    "OutputName": "Contents of URL",
                                }
                            },
                            "string": "\uFFFC",
                        },
                        "WFSerializationType": "WFTextTokenString",
                    }
                },
            },
        ],
    }

    return plistlib.dumps(shortcut, fmt=plistlib.FMT_BINARY)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_shortcut.py <server_url>")
        print("")
        print("  For Cloud Functions (production):")
        print("    python create_shortcut.py https://REGION-PROJECT.cloudfunctions.net/scan-receipt")
        print("")
        print("  For local development:")
        print("    python create_shortcut.py http://localhost:8080")
        sys.exit(1)

    url = sys.argv[1]

    unsigned_path = "ScanReceipt.shortcut"
    signed_path = "ScanReceipt-signed.shortcut"

    data = create_shortcut(url)
    with open(unsigned_path, "wb") as f:
        f.write(data)

    print(f"Unsigned shortcut: {unsigned_path}")
    print(f"Server URL: {url}/scan")
    print(f"\nSigning...")

    result = subprocess.run(
        ["shortcuts", "sign", "--mode", "anyone",
         "--input", unsigned_path, "--output", signed_path],
        capture_output=True, text=True
    )

    if os.path.exists(signed_path) and os.path.getsize(signed_path) > 0:
        print(f"Signed shortcut: {signed_path}")
        print(f"\nAirDrop '{signed_path}' to your iPhone to install.")
    else:
        print(f"Signing failed: {result.stderr}")
