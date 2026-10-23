# ADREC Abu Dhabi Property Transaction Downloader

Production-ready standalone Python Selenium automation script for downloading Abu Dhabi real estate transaction data from the official ADREC website and automatically uploading it to Google Drive.

---

## 📋 Requirements

- **Python 3.8+** installed on your system.
- **Google Chrome** browser installed.

---

## 🚀 Quick Setup (3 Minutes)

### Step 1: Install Required Python Packages
Open your terminal/command prompt and run:

```bash
pip install selenium google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```
*(Or if you have `requirements.txt`: `pip install -r requirements.txt`)*

---

## 🏃 How to Run the Script

### Option 1: Interactive Mode (Terminal Prompts)
Run the script directly:

```bash
python adrec_downloader.py
```

You will see:
```text
=================================================================
   ADREC Abu Dhabi Property Transaction Downloader
=================================================================

Enter From Date (YYYY-MM-DD): 2026-01-01
Enter To Date (YYYY-MM-DD): 2026-10-08
```

---

### Option 2: Automated Mode (Command-Line Arguments)
For automated tasks or cron jobs without typing dates:

```bash
python adrec_downloader.py --from-date 2026-01-01 --to-date 2026-10-08
```

Optional flags:
- `--headless`: Runs Chrome in the background without opening a browser window.
- `--folder-id YOUR_FOLDER_ID`: Uploads to a custom Google Drive folder ID.
- `--cleanup`: Deletes the local CSV file after successful Google Drive upload.

---

## 🔐 First-Time Google Sign-In (One-Time Only)

Because Google OAuth credentials are built directly into the script, you **do not** need to download or configure any JSON files manually.

When you run the script for the **first time**:
1. A Google sign-in page will automatically open in your browser.
2. Select your Google account.
3. If you see **"Google hasn't verified this app"**, click **"Advanced"** and then **"Go to ADREC Downloader (unsafe)"**.
4. Click **"Continue" / "Allow"** to grant permission to upload files to your Google Drive.
5. A local `token.json` file will be created automatically.
6. **All future runs will execute 100% automatically in the background without any popups.**

---

## ⚙️ Customizing the Google Drive Folder (Optional)

By default, files are uploaded to the pre-configured Google Drive folder:
`1h_cUque4NqERMGvE__LaJgLuanXu1Ov2`

If you want to change the target folder, open `adrec_downloader.py` and edit line 60:
```python
DEFAULT_GOOGLE_DRIVE_FOLDER_ID = "YOUR_NEW_GOOGLE_DRIVE_FOLDER_ID"
```
*(Or pass `--folder-id YOUR_NEW_ID` when running the command).*

---

## 🔄 Complete Automation Workflow

```text
Start
  ↓
User enters From Date & To Date
  ↓
Open ADREC Website (https://adrec.gov.ae/en/property_and_index/adrec-dashboard)
  ↓
Switch into Dashboard Iframe Context
  ↓
Scroll to 'Recent Sales' section
  ↓
Enter From Date & To Date into Datepickers
  ↓
Set all 7 Dropdowns to 'All' (Asset Type, Property Type, Transaction Type, District, Community, Project, Layout)
  ↓
Click Export & Wait for CSV Download
  ↓
Upload CSV file to Google Drive folder
  ↓
Verify Upload & Print Google Drive File ID
```

---

## ❓ Troubleshooting

- **Google Sign-in "Access blocked: App has not completed the Google verification process"**:
  Make sure your Gmail account is added under **Test users** in the Google Cloud Console OAuth consent screen, or sign in with the authorized account.
- **Chrome fails to launch**:
  Ensure you have the latest version of Google Chrome installed. Selenium 4 automatically manages ChromeDriver.
- **Wrong Date Range**:
  Dates must follow the `YYYY-MM-DD` format (e.g. `2026-01-01`), and `From Date` must be less than or equal to `To Date`.
