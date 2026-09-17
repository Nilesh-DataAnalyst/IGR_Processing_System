"""
========================================================================================
DUBAI LAND DEPARTMENT REAL ESTATE DATA SCRAPER & GOOGLE DRIVE UPLOADER (ALL-IN-ONE)
========================================================================================

Description:
    This is an all-in-one standalone script that automates the extraction of real estate
    open data from the Dubai Land Department portal and automatically uploads the resulting
    CSV datasets to Google Drive (via OAuth or Service Account).

Quick Install Dependencies:
    pip install selenium webdriver-manager google-api-python-client google-auth-oauthlib google-auth-httplib2

How to Run:
    1. Interactive Mode (prompts for dates in terminal):
       python dubai_scraper_all_in_one.py

    2. Automated / Background Mode (using predefined config or CLI arguments):
       python dubai_scraper_all_in_one.py --from-date 01/01/2025 --to-date 15/09/2026 --headless

========================================================================================
TABLE OF CONTENTS / SEARCH INDEX (Use Ctrl+F to find sections):
    [SECTION 1] - IMPORTS & SYSTEM CONFIGURATION
    [SECTION 2] - USER CONFIGURATION & SETTINGS
    [SECTION 3] - GOOGLE DRIVE UPLOAD & AUTHENTICATION ENGINE
    [SECTION 4] - BROWSER & SELENIUM DRIVER SETUP
    [SECTION 5] - TERMINAL USER INTERFACE & INPUT VALIDATION
    [SECTION 6] - CORE SCRAPER AUTOMATION WORKFLOW
    [SECTION 7] - CLI ARGUMENT PARSING & SCRIPT ENTRYPOINT
========================================================================================
"""

# ==============================================================================
# [SECTION 1] - IMPORTS & SYSTEM CONFIGURATION
# ==============================================================================
import os
import sys
import io
import time
import re
import shutil
import mimetypes
import argparse
import json
from datetime import datetime

# Selenium Web Automation Modules
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Google Drive API & Authentication Modules
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.oauth2.credentials

# Force UTF-8 standard output for Windows console emoji/symbol support
if sys.platform.startswith('win'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass


# ==============================================================================
# [SECTION 2] - USER CONFIGURATION & SETTINGS
# ==============================================================================
# ------------------------------------------------------------------------------
# 2.1 Date Range Settings (Format: DD/MM/YYYY)
# ------------------------------------------------------------------------------
FROM_DATE = "01/01/2025"
TO_DATE = "15/09/2026"

# ------------------------------------------------------------------------------
# 2.2 Portal & Web Settings
# ------------------------------------------------------------------------------
WEBSITE_URL = "https://dubailand.gov.ae/en/open-data/real-estate-data/#/"

# Target Data Tab to scrape:
# Options: "Transactions", "Rents", "Project", "Valuations", "Building", "Developer"
TARGET_TAB = "Transactions"

# Run browser in headless mode (False = visible Chrome window, True = background)
HEADLESS = False

# ------------------------------------------------------------------------------
# 2.3 Google Drive Cloud Storage Settings
# ------------------------------------------------------------------------------
# Paste your Shared Google Drive Folder ID or full URL here:
# Example: "https://drive.google.com/drive/folders/15p5cTByYqE-9i74seXQGXXhYRnmlc1Zc?usp=drive_link"
GOOGLE_DRIVE_FOLDER_ID = "https://drive.google.com/drive/folders/15p5cTByYqE-9i74seXQGXXhYRnmlc1Zc?usp=drive_link"

# Authentication Method: "oauth" or "service_account"
# - "oauth": Uses credentials.json and prompts browser login on first run (saves token.json)
# - "service_account": Uses service_account.json downloaded from Google Cloud Console
AUTH_TYPE = "oauth"

# Credential file paths
SERVICE_ACCOUNT_FILE = "service_account.json"
OAUTH_CREDENTIALS_FILE = "credentials.json"
OAUTH_TOKEN_FILE = "token.json"

# (Optional) Local Google Drive sync path (if you use Google Drive Desktop App)
# Example: r"G:\Shared drives\MyTeamFolder" or r"C:\Users\Username\Google Drive\MyFolder"
LOCAL_GDRIVE_PATH = ""

# ------------------------------------------------------------------------------
# 2.4 Local Download Directory
# ------------------------------------------------------------------------------
DOWNLOAD_DIR_NAME = "downloads"


# ==============================================================================
# [SECTION 3] - GOOGLE DRIVE UPLOAD & AUTHENTICATION ENGINE
# ==============================================================================
# Google Drive API permissions scope
GDRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']


def extract_folder_id(folder_input: str) -> str:
    """
    Extracts the clean folder ID whether user passed a raw ID or full Google Drive URL.
    
    Examples:
        - Input: 'https://drive.google.com/drive/folders/1ABC123xyz' -> Output: '1ABC123xyz'
        - Input: '1ABC123xyz' -> Output: '1ABC123xyz'
    """
    if not folder_input:
        return ""
    folder_input = folder_input.strip()
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_input)
    if match:
        return match.group(1)
    match = re.search(r'id=([a-zA-Z0-9_-]+)', folder_input)
    if match:
        return match.group(1)
    return folder_input


def get_drive_service(auth_type: str = AUTH_TYPE,
                      service_account_file: str = SERVICE_ACCOUNT_FILE,
                      oauth_credentials_file: str = OAUTH_CREDENTIALS_FILE,
                      oauth_token_file: str = OAUTH_TOKEN_FILE):
    """
    Authenticates with Google APIs and returns an authorized Google Drive v3 service client.
    Supports both Service Account and OAuth 2.0 flows.
    """
    creds = None
    auth_type = (auth_type or "").lower()

    if auth_type == "service_account":
        if not os.path.exists(service_account_file):
            print(f"\n[!] Service account file '{service_account_file}' not found.")
            print("    Please place your Google Cloud Service Account JSON key in the project root")
            print("    or switch AUTH_TYPE to 'oauth' in the configuration section.")
            return None
        creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=GDRIVE_SCOPES
        )
        print(f"[+] Authenticated via Service Account ({service_account_file})")

    elif auth_type == "oauth":
        if os.path.exists(oauth_token_file):
            with open(oauth_token_file, 'r') as token:
                token_data = json.load(token)
                creds = google.oauth2.credentials.Credentials.from_authorized_user_info(token_data, GDRIVE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(oauth_credentials_file):
                    print(f"\n[!] OAuth credentials file '{oauth_credentials_file}' not found.")
                    print("    Please download OAuth client ID JSON from Google Cloud Console as 'credentials.json'")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(oauth_credentials_file, GDRIVE_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(oauth_token_file, 'w') as token:
                token.write(creds.to_json())
        print(f"[+] Authenticated via OAuth ({oauth_credentials_file})")
    else:
        print(f"[!] Unknown AUTH_TYPE: {auth_type}. Must be 'service_account' or 'oauth'")
        return None

    service = build('drive', 'v3', credentials=creds)
    return service


def upload_file_to_gdrive(local_file_path: str,
                          folder_id: str = GOOGLE_DRIVE_FOLDER_ID,
                          auth_type: str = AUTH_TYPE,
                          service_account_file: str = SERVICE_ACCOUNT_FILE,
                          oauth_credentials_file: str = OAUTH_CREDENTIALS_FILE,
                          oauth_token_file: str = OAUTH_TOKEN_FILE,
                          local_gdrive_path: str = LOCAL_GDRIVE_PATH) -> bool:
    """
    Uploads a downloaded file to Google Drive.
    Supports Google Drive API direct cloud upload to folder_id and/or copying to local Google Drive desktop sync path.
    """
    if not os.path.exists(local_file_path):
        print(f"[!] Error: File '{local_file_path}' does not exist.")
        return False

    filename = os.path.basename(local_file_path)
    clean_folder_id = extract_folder_id(folder_id)

    # 1. Check if user configured local Google Drive desktop sync folder
    if local_gdrive_path and os.path.exists(local_gdrive_path):
        target_dest = os.path.join(local_gdrive_path, filename)
        shutil.copy2(local_file_path, target_dest)
        print(f"[+] Successfully copied '{filename}' to local Google Drive sync folder: {target_dest}")

    # 2. Upload via Google Drive API
    if not clean_folder_id:
        print("\n[i] Note: GOOGLE_DRIVE_FOLDER_ID is not configured.")
        print("    If you want automatic cloud upload, set GOOGLE_DRIVE_FOLDER_ID in [SECTION 2].")
        print(f"    Downloaded file is safely preserved locally at: {os.path.abspath(local_file_path)}")
        return True

    service = get_drive_service(
        auth_type=auth_type,
        service_account_file=service_account_file,
        oauth_credentials_file=oauth_credentials_file,
        oauth_token_file=oauth_token_file
    )

    if not service:
        print("[!] Skipping Google Drive cloud upload due to missing credentials.")
        return False

    file_metadata = {
        'name': filename,
        'parents': [clean_folder_id]
    }

    mime_type, _ = mimetypes.guess_type(local_file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    media = MediaFileUpload(local_file_path, mimetype=mime_type, resumable=True)

    print(f"[+] Uploading '{filename}' to Google Drive Folder ID: {clean_folder_id} ...")
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()

        print(f"[✔] Upload Successful!")
        print(f"    File Name: {file.get('name')}")
        print(f"    File ID  : {file.get('id')}")
        if file.get('webViewLink'):
            print(f"    Link     : {file.get('webViewLink')}")
        return True

    except Exception as e:
        print(f"[!] Error uploading to Google Drive: {e}")
        print("    Tips:")
        print("    - If using Service Account, share the folder with the Service Account email with 'Editor' permissions.")
        print("    - Verify the GOOGLE_DRIVE_FOLDER_ID is valid.")
        return False


# ==============================================================================
# [SECTION 4] - BROWSER & SELENIUM DRIVER SETUP
# ==============================================================================
def get_driver(download_dir: str, headless: bool = False):
    """
    Configures and initializes Chrome WebDriver with custom download settings,
    anti-detection parameters, and automatic download triggers.
    """
    os.makedirs(download_dir, exist_ok=True)

    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def wait_for_new_download(download_dir: str, existing_files: set, timeout: int = 60) -> str:
    """
    Monitors the download folder and waits until a new file finishes downloading.
    Ignores temporary/partial download extensions (.crdownload, .tmp).
    """
    start_time = time.time()
    print("   ⏳ Tracking download progress...", end="", flush=True)
    while time.time() - start_time < timeout:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - existing_files
        valid_files = [
            f for f in new_files 
            if not f.endswith('.crdownload') and not f.endswith('.tmp') and not f.startswith('.')
        ]
        if valid_files:
            downloaded_file = valid_files[0]
            file_path = os.path.join(download_dir, downloaded_file)
            time.sleep(1)
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(" Done!")
                return file_path
        print(".", end="", flush=True)
        time.sleep(1)
    print(" Timed out.")
    return ""


# ==============================================================================
# [SECTION 5] - TERMINAL USER INTERFACE & INPUT VALIDATION
# ==============================================================================
def print_banner():
    """Prints a styled CLI banner for the scraper."""
    print("=" * 75)
    print(" 🏙️   DUBAI LAND DEPARTMENT - REAL ESTATE DATA SCRAPER & UPLOADER")
    print("=" * 75)


def validate_date(date_str: str) -> bool:
    """Validates that the input date string is in the valid DD/MM/YYYY format."""
    pattern = r"^\d{2}/\d{2}/\d{4}$"
    if not re.match(pattern, date_str):
        return False
    try:
        datetime.strptime(date_str, "%d/%m/%Y")
        return True
    except ValueError:
        return False


def get_terminal_inputs():
    """
    Interactive terminal setup menu to collect date ranges and options from user,
    providing pre-filled defaults and real-time validation.
    """
    print("\n📋 [Terminal Interactive Setup]")
    print("-" * 75)
    
    # 1. From Date
    default_from = FROM_DATE or "01/01/2025"
    while True:
        user_from = input(f"👉 Enter FROM Date (DD/MM/YYYY) [Default: {default_from}]: ").strip()
        if not user_from:
            from_date = default_from
            break
        elif validate_date(user_from):
            from_date = user_from
            break
        else:
            print("   ❌ Invalid date format! Please enter in DD/MM/YYYY format (e.g. 01/01/2025).")

    # 2. To Date
    default_to = TO_DATE or datetime.now().strftime("%d/%m/%Y")
    while True:
        user_to = input(f"👉 Enter TO Date   (DD/MM/YYYY) [Default: {default_to}]: ").strip()
        if not user_to:
            to_date = default_to
            break
        elif validate_date(user_to):
            to_date = user_to
            break
        else:
            print("   ❌ Invalid date format! Please enter in DD/MM/YYYY format (e.g. 15/09/2026).")

    # Selected Tab
    selected_tab = TARGET_TAB or "Transactions"

    # 3. Headless mode
    headless_choice = input(f"👉 Run browser in Background / Headless mode? (y/N) [Default: N]: ").strip().lower()
    is_headless = headless_choice in ['y', 'yes', 'true']

    print("-" * 75)
    print(f"🎯 Selected Configuration:")
    print(f"   • Module     : Real Estate {selected_tab}")
    print(f"   • From Date  : {from_date}")
    print(f"   • To Date    : {to_date}")
    print(f"   • Headless   : {is_headless}")
    print(f"   • GDrive URL : {GOOGLE_DRIVE_FOLDER_ID or 'Not configured'}")
    print("-" * 75)
    input("⚡ Press [ENTER] to start scraping...")
    return from_date, to_date, selected_tab, is_headless


# ==============================================================================
# [SECTION 6] - CORE SCRAPER AUTOMATION WORKFLOW
# ==============================================================================
def run_scraper(from_date: str = FROM_DATE,
                to_date: str = TO_DATE,
                tab_name: str = TARGET_TAB,
                headless: bool = HEADLESS):
    """
    Main automation engine for Dubai Land Department Open Data portal:
    1. Launches Chrome with custom download settings
    2. Switches to requested data tab (Transactions, Rents, etc.)
    3. Injects date ranges with DOM dispatch events
    4. Automatically clicks Google reCAPTCHA checkbox inside iframe
    5. Submits search query
    6. Downloads exported CSV file and uploads directly to Google Drive
    """
    start_time = time.time()
    download_dir = os.path.abspath(DOWNLOAD_DIR_NAME)
    existing_files = set(os.listdir(download_dir)) if os.path.exists(download_dir) else set()

    print("\n" + "=" * 75)
    print(f"🚀 INITIATING AUTOMATION WORKFLOW")
    print(f"   Date Range : {from_date} ➔ {to_date}")
    print(f"   Data Tab   : {tab_name}")
    print(f"   Download To: {download_dir}")
    print("=" * 75)

    print("\n[Step 1/6] 🌐 Launching Chrome & Opening Portal...")
    driver = get_driver(download_dir, headless=headless)
    wait = WebDriverWait(driver, 30)

    try:
        driver.get(WEBSITE_URL)
        time.sleep(5)
        print("   ✔ Webpage loaded successfully.")

        # Step 2: Tab Switching
        tab_prefix_map = {
            "Transactions": "transaction",
            "Rents": "rent",
            "Project": "project",
            "Valuations": "valuation",
            "Building": "building",
            "Developer": "developer"
        }
        prefix = tab_prefix_map.get(tab_name, "transaction")

        print(f"\n[Step 2/6] 📑 Selecting Data Tab: '{tab_name}'...")
        if tab_name.lower() != "transactions":
            tab_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//a[contains(text(),'{tab_name}') or contains(@aria-controls,'{tab_name.lower()}')]"
            )))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_element)
            driver.execute_script("arguments[0].click();", tab_element)
            time.sleep(2)
            print(f"   ✔ Switched to '{tab_name}' tab.")
        else:
            print(f"   ✔ Default tab '{tab_name}' active.")

        # Step 3: Populate Date Range
        print(f"\n[Step 3/6] 📅 Entering Date Range: {from_date} to {to_date}...")
        from_input_id = f"{prefix}_pFromDate"
        to_input_id = f"{prefix}_pToDate"

        try:
            from_date_input = wait.until(EC.presence_of_element_located((By.ID, from_input_id)))
            to_date_input = wait.until(EC.presence_of_element_located((By.ID, to_input_id)))
        except Exception:
            from_date_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='From Date']")
            to_date_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='To Date']")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", from_date_input)
        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        """, from_date_input, from_date)

        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        """, to_date_input, to_date)
        print(f"   ✔ Dates populated: From '{from_date}' | To '{to_date}'")
        time.sleep(1)

        # Step 4: Locate and Click Google reCAPTCHA Checkbox
        print("\n[Step 4/6] 🤖 Locating and clicking reCAPTCHA checkbox...")
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[title='reCAPTCHA'], iframe[src*='recaptcha']")
        recaptcha_frame = None
        for frame in iframes:
            if frame.is_displayed():
                recaptcha_frame = frame
                break

        if recaptcha_frame:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", recaptcha_frame)
            time.sleep(1)
            driver.switch_to.frame(recaptcha_frame)

            try:
                checkbox = wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, ".recaptcha-checkbox-border, #recaptcha-anchor"
                )))
                try:
                    checkbox.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", checkbox)
                print("   ✔ Successfully clicked <div class='recaptcha-checkbox-border'>!")
            except Exception as e:
                print(f"   ⚠️ Warning clicking reCAPTCHA checkbox: {e}")

            driver.switch_to.default_content()
        else:
            print("   ⚠️ No visible reCAPTCHA iframe detected, continuing...")

        time.sleep(3)

        # Step 5: Submit Search
        print("\n[Step 5/6] 🔍 Submitting Search Request...")
        search_buttons = driver.find_elements(
            By.XPATH, "//button[contains(text(),'Search') and not(contains(@class,'mobile'))]"
        )
        visible_search_btn = None
        for btn in search_buttons:
            if btn.is_displayed():
                visible_search_btn = btn
                break

        if not visible_search_btn:
            visible_search_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn_1")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", visible_search_btn)
        time.sleep(1)
        try:
            visible_search_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", visible_search_btn)
        print("   ✔ Search button clicked! Waiting for database response...")

        # Allow time for data table to render
        time.sleep(8)

        # Step 6: Locate & Trigger CSV Download
        print("\n[Step 6/6] 📥 Triggering CSV Download...")
        csv_buttons = driver.find_elements(
            By.XPATH, "//button[contains(text(),'Download as CSV') or contains(@class,'js-ExportCsv')]"
        )
        visible_csv_btn = None
        for btn in csv_buttons:
            if btn.is_displayed():
                visible_csv_btn = btn
                break

        if not visible_csv_btn and csv_buttons:
            visible_csv_btn = csv_buttons[0]

        if visible_csv_btn:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", visible_csv_btn)
            time.sleep(1)
            try:
                visible_csv_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", visible_csv_btn)
            print("   ✔ 'Download as CSV' button clicked!")
        else:
            raise RuntimeError("Could not locate 'Download as CSV' button on webpage.")

        # Track and wait for file download completion
        downloaded_file_path = wait_for_new_download(download_dir, existing_files, timeout=120)

        if not downloaded_file_path:
            all_files = [
                os.path.join(download_dir, f) for f in os.listdir(download_dir) 
                if not f.endswith('.crdownload') and not f.endswith('.tmp')
            ]
            if all_files:
                downloaded_file_path = max(all_files, key=os.path.getmtime)

        if downloaded_file_path and os.path.exists(downloaded_file_path):
            file_size_kb = os.path.getsize(downloaded_file_path) / 1024
            filename = os.path.basename(downloaded_file_path)
            print(f"\n   🎉 File Downloaded: {filename} ({file_size_kb:.2f} KB)")
            print(f"   📁 Local Path     : {downloaded_file_path}")

            # Google Drive Upload
            print("\n" + "=" * 75)
            print(" ☁️   GOOGLE DRIVE UPLOADER")
            print("=" * 75)
            upload_success = upload_file_to_gdrive(
                local_file_path=downloaded_file_path,
                folder_id=GOOGLE_DRIVE_FOLDER_ID,
                auth_type=AUTH_TYPE,
                service_account_file=SERVICE_ACCOUNT_FILE,
                oauth_credentials_file=OAUTH_CREDENTIALS_FILE,
                oauth_token_file=OAUTH_TOKEN_FILE,
                local_gdrive_path=LOCAL_GDRIVE_PATH
            )

            elapsed = time.time() - start_time
            print("=" * 75)
            print(f"✨ COMPLETED IN {elapsed:.1f} SECONDS!")
            print("=" * 75)
            return downloaded_file_path
        else:
            print("   ❌ Download failed or timed out.")
            return None

    finally:
        print("\n🔒 Closing browser session.")
        driver.quit()


# ==============================================================================
# [SECTION 7] - CLI ARGUMENT PARSING & SCRIPT ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    print_banner()

    parser = argparse.ArgumentParser(
        description="Dubai Land Department Real Estate Data Scraper & Google Drive Uploader (All-In-One)"
    )
    parser.add_argument("--from-date", type=str, help="Start Date (DD/MM/YYYY)")
    parser.add_argument("--to-date", type=str, help="End Date (DD/MM/YYYY)")
    parser.add_argument("--tab", type=str, help="Data Tab (Transactions, Rents, Project, Valuations, Building, Developer)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in background headless mode")
    parser.add_argument("--non-interactive", action="store_true", help="Skip interactive terminal prompts and use config defaults")

    args = parser.parse_args()

    # Determine execution mode:
    # If user provided CLI flags or --non-interactive, run directly; otherwise prompt in interactive terminal
    if args.from_date or args.to_date or args.non_interactive:
        f_date = args.from_date or FROM_DATE
        t_date = args.to_date or TO_DATE
        tab = args.tab or TARGET_TAB
        head = args.headless if args.headless else HEADLESS
    else:
        f_date, t_date, tab, head = get_terminal_inputs()

    run_scraper(
        from_date=f_date,
        to_date=t_date,
        tab_name=tab,
        headless=head
    )
