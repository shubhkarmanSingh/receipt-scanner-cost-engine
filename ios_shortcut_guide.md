# iOS Shortcut Setup — "Scan Receipt"

One-tap receipt scanning from Tony's iPhone. Takes a photo (or picks from gallery), sends it to the Cloud Function, and shows the result.

## Prerequisites

- The Cloud Function must be deployed (see README.md)
- You need the function URL: `https://REGION-PROJECT.cloudfunctions.net/scan-receipt`
- If `SCANNER_API_KEY` is set, you need that key too

## Step-by-Step: Create the Shortcut

Open the **Shortcuts** app on iPhone and tap **+** to create a new shortcut.

### Action 1: Take or Choose Photo

- Add action: **"Take Photo"**
  - Toggle OFF "Show Camera Preview" if you want it faster
- **OR** add action: **"Choose from Menu"** with options "Take Photo" / "Choose from Library"
  - Under "Take Photo": add **Take Photo** action
  - Under "Choose from Library": add **Select Photos** action (limit to 1)

### Action 2: Convert Image to Base64

- Add action: **"Base64 Encode"**
  - Input: Photo from previous step
  - Line Breaks: None

### Action 3: Build the JSON Body

- Add action: **"Text"**
- Paste this (replace the variable reference with the Base64 output):

```
{"image_base64": "[Base64 Encoded]", "media_type": "image/jpeg", "source": "iphone"}
```

To insert the variable: tap in the text field, tap where `[Base64 Encoded]` is, delete it, then tap the "Base64 Encoded" magic variable from the bar above the keyboard.

### Action 4: Send to Cloud Function

- Add action: **"Get Contents of URL"**
- URL: `https://REGION-PROJECT.cloudfunctions.net/scan-receipt`
- Method: **POST**
- Headers:
  - `Content-Type`: `application/json`
  - `X-API-Key`: `your-scanner-api-key` (only if SCANNER_API_KEY is configured)
- Request Body: **File**
  - Select the Text output from Action 3

### Action 5: Parse the Response

- Add action: **"Get Dictionary Value"**
  - Key: `status`
- Add action: **"If"**
  - Condition: "is" → "success"
  - **If yes:**
    - Add action: **"Get Dictionary Value"** from Contents of URL
      - Key: `items_mapped`
    - Add action: **"Show Notification"**
      - Title: "Receipt Scanned"
      - Body: `[items_mapped] items mapped to ingredients`
  - **Otherwise:**
    - Add action: **"Get Dictionary Value"** from Contents of URL
      - Key: `message`
    - Add action: **"Show Notification"**
      - Title: "Scan Failed"
      - Body: the error message

### Action 6: Name and Add to Home Screen

- Tap the shortcut name at top → rename to **"Scan Receipt"**
- Tap the icon → choose a camera or receipt icon
- Tap **⋯** → **Add to Home Screen**

## Usage

1. Buy ingredients at Restaurant Depot
2. Tap **"Scan Receipt"** on iPhone home screen
3. Take photo of receipt
4. Wait 5-10 seconds
5. Notification appears: "12 items mapped to ingredients"
6. Done — Google Sheet is updated with new prices and costs

## Sharing the Shortcut

To install on Tony's phone:
1. Build the shortcut on your phone first
2. Tap ⋯ on the shortcut → Share → Copy iCloud Link
3. Text the link to Tony — he taps it to install
4. He may need to go to Settings → Shortcuts → allow untrusted shortcuts

## Alternative: Share Sheet Integration

Instead of a standalone shortcut, you can make it appear in the iOS Share Sheet so Tony can share a photo from the Camera Roll:

1. In the shortcut editor, tap ⋯ → toggle **"Show in Share Sheet"**
2. Set accepted types to **Images**
3. Replace Action 1 with **"Shortcut Input"** (receives the shared image)
4. Now Tony can: open Photos → select receipt → tap Share → tap "Scan Receipt"

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not connect to server" | Check the Cloud Function URL is correct and deployed |
| "Invalid or missing API key" | Add X-API-Key header matching SCANNER_API_KEY |
| Timeout after 30s | iPhone shortcuts timeout at 30s by default. The Cloud Function has 60s. Try again — large receipts take longer. |
| "No items extracted" | Photo may be blurry or too dark. Retake with flash. |
| Shortcut won't run | Settings → Shortcuts → Allow Running Scripts must be ON |
