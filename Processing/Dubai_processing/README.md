# Dubai Land Department Real Estate Data Scraper & Google Drive Uploader

Automated Python web-scraping script for **Dubai Land Department Open Data portal** ([https://dubailand.gov.ae/en/open-data/real-estate-data/#/](https://dubailand.gov.ae/en/open-data/real-estate-data/#/)).

---

## 🚀 Features & Workflow
1. **Navigates to the portal**: Loads the real estate open data interface.
2. **Selects Date Range**: Simple configuration in `config.py` (or via CLI arguments).
3. **Automated reCAPTCHA Click**: Automatically detects and clicks the `<div class="recaptcha-checkbox-border" role="presentation"></div>` element inside the Google reCAPTCHA iframe.
4. **Triggers Search**: Scrolls and clicks the Search button, waiting for the dataset query to complete.
5. **Downloads CSV**: Locates and triggers `Download as CSV` and waits until download is 100% saved locally.
6. **Uploads to Google Drive**: Automatically uploads the downloaded CSV directly into a shared Google Drive folder.

---

## 📁 Project Structure

```
Dubai1/
├── dubai_scraper_all_in_one.py  # 🌟 Single merged all-in-one script (easy to share)
├── config.py                    # User settings (Dates, Tab selection, Google Drive folder ID)
├── dubai_scraper.py             # Modular automation scraper script
├── gdrive_uploader.py           # Google Drive upload integration module
├── requirements.txt             # Python dependencies
└── downloads/                   # Local directory where CSV files are saved
```

---

## ⚙️ Configuration

Open [`config.py`](file:///d:/Pankaj(2)/Dubai1/config.py) to set your parameters:

```python
# 1. Dates (Format: DD/MM/YYYY)
FROM_DATE = "01/09/2026"
TO_DATE = "15/09/2026"

# 2. Target Tab (Default: "Transactions")
TARGET_TAB = "Transactions"  # Options: "Transactions", "Rents", "Project", "Valuations", "Building", "Developer"

# 3. Google Drive Shared Folder ID or URL
GOOGLE_DRIVE_FOLDER_ID = "https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE"

# 4. Authentication Method ("service_account" or "oauth")
AUTH_TYPE = "service_account"
```

---

## 🔑 Google Drive Setup

You can use either of the following two methods to upload to Google Drive:

### Option A: Service Account (Recommended for automated scripts)
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and enable the **Google Drive API**.
2. Create a Service Account and download its JSON key as `service_account.json` into this project folder.
3. Open your Google Drive shared folder and **share it with the Service Account email** (with `Editor` permissions).
4. Set `GOOGLE_DRIVE_FOLDER_ID` in `config.py`.

### Option B: OAuth Client
1. Download OAuth 2.0 Client credentials from Google Cloud Console as `credentials.json` into this project folder.
2. In `config.py`, set `AUTH_TYPE = "oauth"`.
3. On first run, a browser window will open for one-time login authorization.

---

## 🏃 How to Run

### Method 1: Using All-In-One Single Script (Easiest to share)
```bash
python dubai_scraper_all_in_one.py
```

### Method 2: Using `config.py` with modular scripts
```bash
python dubai_scraper.py
```

### Method 3: Passing command-line arguments
```bash
python dubai_scraper_all_in_one.py --from-date 01/01/2025 --to-date 15/09/2026
```

### Optional Flags:
- `--headless`: Run Chrome in background mode without GUI.
- `--non-interactive`: Skip terminal prompts and run using defaults.
