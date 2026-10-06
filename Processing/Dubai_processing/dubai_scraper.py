"""
========================================================================================
DUBAI LAND DEPARTMENT REAL ESTATE DATA SCRAPER & GOOGLE DRIVE UPLOADER (ALL-IN-ONE)
========================================================================================

Description:
    This is an all-in-one standalone script that automates the extraction of real estate
    open data from the Dubai Land Department portal and automatically uploads the resulting
    CSV datasets to Google Drive (via OAuth or Service Account).

Features & Optimizations:
    - Smart reCAPTCHA resolution with automatic bypass detection and manual Image Challenge handling loop.
    - Glowing visual element and button highlighting so the user can easily monitor automation actions.
    - High-speed dynamic WebDriverWait synchronization eliminating unnecessary multi-second delays.
    - Direct Google Drive Cloud upload and local sync directory support.

Quick Install Dependencies:
    pip install selenium webdriver-manager google-api-python-client google-auth-oauthlib google-auth-httplib2

How to Run:
    1. Interactive Mode (prompts for dates in terminal):
       python dubai_scraper_all_in_one.py

    2. Automated / Background Mode (using predefined config or CLI arguments):
       python dubai_scraper_all_in_one.py --from-date 01/01/2025 --to-date 15/09/2026

========================================================================================
TABLE OF CONTENTS / SEARCH INDEX (Use Ctrl+F to find sections):
    [SECTION 1] - IMPORTS & SYSTEM CONFIGURATION
    [SECTION 2] - USER CONFIGURATION & SETTINGS
    [SECTION 3] - GOOGLE DRIVE UPLOAD & AUTHENTICATION ENGINE
    [SECTION 4] - VISUAL HIGHLIGHTING & AUTOMATION UTILITIES
    [SECTION 5] - BROWSER & SELENIUM DRIVER SETUP
    [SECTION 6] - TERMINAL USER INTERFACE & INPUT VALIDATION
    [SECTION 7] - CORE SCRAPER AUTOMATION WORKFLOW
    [SECTION 8] - CLI ARGUMENT PARSING & SCRIPT ENTRYPOINT
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
from datetime import datetime, timedelta

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

# Ensure Processing directory is on sys.path to access city_config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSING_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROCESSING_DIR not in sys.path:
    sys.path.insert(0, PROCESSING_DIR)

from city_config import CITY_CONFIG, get_city_config, resolve_drive_directory, extract_folder_id

# Database Configuration & Runtime Query Engine
try:
    from pipeline_core import DB_PARAMS
except Exception:
    DB_PARAMS = {
        "host": "localhost",
        "port": "5432",
        "database": "nilesh",
        "user": "postgres",
        "password": "nilesh",
    }


def get_runtime_city_id(city_name: str = "Dubai", db_params: dict = None) -> int | None:
    """
    Fetches the runtime city_id dynamically from public.dim_city for the given city name.
    Falls back to DUBAI_CITY_CONFIG or 15 if database query is unsuccessful.
    """
    params = dict(db_params or DB_PARAMS)
    params.setdefault("connect_timeout", 3)
    try:
        import psycopg2
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT city_id FROM public.dim_city WHERE lower(city_name) = lower(%s) LIMIT 1;",
                    (city_name,)
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception:
        pass
    return DUBAI_CITY_CONFIG.get("city_id", 15) if "DUBAI_CITY_CONFIG" in globals() else 15


def get_last_transaction_date_from_db(city_name: str = "Dubai", db_params: dict = None) -> str | None:
    """
    Dynamically queries public.dim_city to obtain the runtime city_id, then retrieves
    the latest transaction_date from public.transactions for that city.
    Returns the start date (latest transaction date + 1 day) formatted as 'DD/MM/YYYY' or None on failure.
    """
    params = dict(db_params or DB_PARAMS)
    params.setdefault("connect_timeout", 3)
    try:
        import psycopg2
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                # 1. Fetch runtime city_id from dim_city
                cur.execute(
                    "SELECT city_id FROM public.dim_city WHERE lower(city_name) = lower(%s) LIMIT 1;",
                    (city_name,)
                )
                city_row = cur.fetchone()
                fallback_cid = DUBAI_CITY_CONFIG.get("city_id", 15) if "DUBAI_CITY_CONFIG" in globals() else 15
                city_id = city_row[0] if (city_row and city_row[0] is not None) else fallback_cid

                # 2. Fetch max transaction_date using index
                cur.execute(
                    "SELECT MAX(transaction_date) FROM public.transactions WHERE city_id = %s;",
                    (city_id,)
                )
                row = cur.fetchone()
                if row and row[0]:
                    last_date = row[0]
                    if isinstance(last_date, str):
                        try:
                            dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
                        except ValueError:
                            dt = datetime.strptime(last_date[:10], "%d/%m/%Y")
                    elif hasattr(last_date, "year"):
                        dt = datetime(last_date.year, last_date.month, last_date.day)
                    else:
                        dt = datetime.strptime(str(last_date)[:10], "%Y-%m-%d")

                    next_date = dt + timedelta(days=1)
                    return next_date.strftime("%d/%m/%Y")
    except Exception:
        pass
    return None


# ==============================================================================
# [SECTION 2] - USER CONFIGURATION & SETTINGS
# ==============================================================================
# ------------------------------------------------------------------------------
# 2.1 Date Range Settings (Format: DD/MM/YYYY)
# ------------------------------------------------------------------------------
# Start date is automatically resolved from the latest transaction in the database
_db_last_date = get_last_transaction_date_from_db("Dubai")
FROM_DATE = _db_last_date or "01/01/2025"
TO_DATE = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")

# ------------------------------------------------------------------------------
# 2.2 Portal & Web Settings
# ------------------------------------------------------------------------------
WEBSITE_URL = "https://dubailand.gov.ae/en/open-data/real-estate-data/#/"

# Target Data Tab to scrape:
# Options: "Transactions", "Rents", "Project", "Valuations", "Building", "Developer"
TARGET_TAB = "Transactions"

# Run browser in headless mode (False = visible Chrome window, True = background)
HEADLESS = False

# Maximum time (in seconds) to wait for user to solve image CAPTCHA challenge if presented
CAPTCHA_TIMEOUT = 120

# ------------------------------------------------------------------------------
# 2.3 Google Drive Cloud Storage Settings (Loaded dynamically from CITY_CONFIG)
# ------------------------------------------------------------------------------
DUBAI_CITY_CONFIG = get_city_config("dubai")

# Retrieve Drive paths from CITY_CONFIG
# Scraped raw data will be uploaded to Dubai's input_drive_url (raw input folder)
GOOGLE_DRIVE_FOLDER_ID = DUBAI_CITY_CONFIG.get("input_drive_url") or DUBAI_CITY_CONFIG.get("parent_drive_url") or ""
GOOGLE_DRIVE_PARENT_FOLDER_ID = DUBAI_CITY_CONFIG.get("parent_drive_url") or ""
GOOGLE_DRIVE_FINAL_FOLDER_ID = DUBAI_CITY_CONFIG.get("final_drive_url") or ""

# Local Google Drive Desktop sync path on G: (Standard used for Pune and Mumbai)
LOCAL_GDRIVE_PATH = resolve_drive_directory(GOOGLE_DRIVE_FOLDER_ID) or ""

# Authentication Method: "oauth" or "service_account" (used only as fallback if G: desktop sync is unavailable)
# - "oauth": Uses credentials.json and prompts browser login on first run (saves token.json)
# - "service_account": Uses service_account.json downloaded from Google Cloud Console
AUTH_TYPE = "oauth"

# Credential file paths (auto-resolves in script directory or working directory)
def _resolve_cred(name: str) -> str:
    p = os.path.join(SCRIPT_DIR, name)
    return p if os.path.exists(p) else name

SERVICE_ACCOUNT_FILE = _resolve_cred("service_account.json")
OAUTH_CREDENTIALS_FILE = _resolve_cred("credentials.json")
OAUTH_TOKEN_FILE = _resolve_cred("token.json")

# ------------------------------------------------------------------------------
# 2.4 Local Download Directory
# ------------------------------------------------------------------------------
DOWNLOAD_DIR_NAME = os.path.join(SCRIPT_DIR, "downloads")


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


def format_range_filename(from_date: str, to_date: str, original_filename: str = "") -> str:
    """
    Generates a filename based on the scraping date range with 2-digit year (e.g. '13aug26_14sept26.csv').
    """
    ext = os.path.splitext(original_filename)[1] if original_filename else ".csv"
    if not ext:
        ext = ".csv"

    MONTH_MAP = {
        1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
        7: "jul", 8: "aug", 9: "sept", 10: "oct", 11: "nov", 12: "dec"
    }

    try:
        dt_from = datetime.strptime(str(from_date).strip(), "%d/%m/%Y")
        dt_to = datetime.strptime(str(to_date).strip(), "%d/%m/%Y")

        m_from = MONTH_MAP.get(dt_from.month, dt_from.strftime("%b").lower())
        m_to = MONTH_MAP.get(dt_to.month, dt_to.strftime("%b").lower())

        y_from = dt_from.strftime("%y")
        y_to = dt_to.strftime("%y")

        return f"{dt_from.day}{m_from}{y_from}_{dt_to.day}{m_to}{y_to}{ext}"
    except Exception:
        clean_from = re.sub(r'[/\\:\s]+', '_', str(from_date).strip())
        clean_to = re.sub(r'[/\\:\s]+', '_', str(to_date).strip())
        return f"{clean_from}_{clean_to}{ext}"


def upload_file_to_gdrive(local_file_path: str,
                          folder_id: str = GOOGLE_DRIVE_FOLDER_ID,
                          auth_type: str = AUTH_TYPE,
                          service_account_file: str = SERVICE_ACCOUNT_FILE,
                          oauth_credentials_file: str = OAUTH_CREDENTIALS_FILE,
                          oauth_token_file: str = OAUTH_TOKEN_FILE,
                          local_gdrive_path: str = LOCAL_GDRIVE_PATH,
                          target_filename: str = None) -> bool:
    """
    Uploads a downloaded file to Google Drive.
    Supports Google Drive API direct cloud upload to folder_id and/or copying to local Google Drive desktop sync path.
    """
    if not os.path.exists(local_file_path):
        print(f"[!] Error: File '{local_file_path}' does not exist.")
        return False

    filename = target_filename or os.path.basename(local_file_path)
    # 1. Primary: Check Google Drive Desktop Sync (G:\) - Same as Pune and Mumbai
    desktop_sync_dir = local_gdrive_path or resolve_drive_directory(folder_id or GOOGLE_DRIVE_FOLDER_ID) or LOCAL_GDRIVE_PATH
    if desktop_sync_dir and os.path.exists(desktop_sync_dir):
        target_dest = os.path.join(desktop_sync_dir, filename)
        shutil.copy2(local_file_path, target_dest)
        print(f"[✔] Successfully saved '{filename}' to Google Drive Desktop folder (G:):")
        print(f"    Path    : {target_dest}")
        print(f"    Status  : Synchronized with Google Drive Desktop (same standard as Pune/Mumbai).")
        return True

    # 2. Secondary: Upload via Google Drive API (Fallback if G: is not mounted)
    clean_folder_id = extract_folder_id(folder_id or GOOGLE_DRIVE_FOLDER_ID)
    if not clean_folder_id:
        print("\n[i] Note: GOOGLE_DRIVE_FOLDER_ID is not configured.")
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
# [SECTION 4] - VISUAL HIGHLIGHTING & AUTOMATION UTILITIES
# ==============================================================================
def highlight_and_scroll(driver, element, color="#FF5722", border="3px solid #FF5722", bg_color="rgba(255, 87, 34, 0.15)", duration=0.3):
    """
    Smoothly scrolls element into center of the viewport and applies a glowing visual
    highlight so the user can easily see what the script is interacting with.
    """
    try:
        driver.execute_script("""
            var el = arguments[0];
            el.scrollIntoView({behavior: 'smooth', block: 'center'});
            var origBorder = el.style.border;
            var origBoxShadow = el.style.boxShadow;
            var origBg = el.style.backgroundColor;
            var origTransition = el.style.transition;
            
            el.style.transition = 'all 0.25s ease-in-out';
            el.style.border = arguments[1];
            el.style.boxShadow = '0 0 16px ' + arguments[2];
            el.style.backgroundColor = arguments[3];
            
            el._origStyles = {border: origBorder, boxShadow: origBoxShadow, bg: origBg, transition: origTransition};
        """, element, border, color, bg_color)
        
        if duration > 0:
            time.sleep(duration)
    except Exception:
        pass


def unhighlight(driver, element):
    """Restores the element's original visual styling after interaction."""
    try:
        driver.execute_script("""
            var el = arguments[0];
            if (el._origStyles) {
                el.style.border = el._origStyles.border || '';
                el.style.boxShadow = el._origStyles.boxShadow || '';
                el.style.backgroundColor = el._origStyles.bg || '';
                el.style.transition = el._origStyles.transition || '';
            } else {
                el.style.boxShadow = '';
                el.style.border = '';
            }
        """, element)
    except Exception:
        pass


def click_visible(driver, element, name="Button", highlight_color="#28a745", duration=0.3):
    """
    Smoothly scrolls to element, applies glowing visual feedback, clicks it, and restores styling.
    """
    highlight_and_scroll(
        driver, 
        element, 
        color=highlight_color, 
        border=f"3px solid {highlight_color}", 
        bg_color="rgba(40, 167, 69, 0.18)", 
        duration=duration
    )
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    time.sleep(0.15)
    unhighlight(driver, element)


def bring_chrome_to_front(driver):
    """
    Brings the Chrome automation browser window to the foreground on Windows
    so the user can immediately see and interact with the page, captcha, or automation.
    """
    try:
        driver.maximize_window()
        driver.switch_to.window(driver.current_window_handle)
        driver.execute_script("window.focus();")
    except Exception:
        pass

    if sys.platform.startswith('win'):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Temporarily tag document title to pinpoint this EXACT automation window
            # even if the user already has personal Chrome windows open
            unique_marker = f"__DUBAI_SCRAPER_WINDOW_{os.getpid()}__"
            orig_title = ""
            try:
                orig_title = driver.title
                driver.execute_script(f"document.title = '{unique_marker}';")
                time.sleep(0.08)
            except Exception:
                pass

            # Search by unique title first, then fallback to Chrome window class
            hwnd = user32.FindWindowW(None, unique_marker)
            if not hwnd:
                hwnd = user32.FindWindowW("Chrome_WidgetWin_1", None)

            if hwnd:
                SW_RESTORE = 9
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040

                # Attach thread input to bypass Windows foreground lockout
                fg_hwnd = user32.GetForegroundWindow()
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                cur_thread = kernel32.GetCurrentThreadId()

                if fg_thread and fg_thread != cur_thread:
                    user32.AttachThreadInput(cur_thread, fg_thread, True)

                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetForegroundWindow(hwnd)
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

                if fg_thread and fg_thread != cur_thread:
                    user32.AttachThreadInput(cur_thread, fg_thread, False)

            # Restore original document title
            if orig_title:
                try:
                    driver.execute_script(f"document.title = {json.dumps(orig_title)};")
                except Exception:
                    pass
        except Exception:
            pass

        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


def is_recaptcha_solved(driver) -> bool:
    """
    Checks if Google reCAPTCHA has been successfully solved:
    1. Evaluates grecaptcha.getResponse() across all potential widget IDs (0..9).
    2. Checks g-recaptcha-response textarea tokens in DOM.
    NOTE: Runs purely via non-intrusive JavaScript so it does NOT switch frames or
    interfere with user mouse clicks while the challenge popup is open!
    """
    try:
        solved = driver.execute_script("""
            try {
                if (typeof grecaptcha !== 'undefined' && typeof grecaptcha.getResponse === 'function') {
                    for (var i = 0; i < 10; i++) {
                        try {
                            var resp = grecaptcha.getResponse(i);
                            if (resp && resp.length > 0) return true;
                        } catch(e) {}
                    }
                    var resp = grecaptcha.getResponse();
                    if (resp && resp.length > 0) return true;
                }
                var textareas = document.querySelectorAll('textarea[name="g-recaptcha-response"], textarea#g-recaptcha-response');
                for (var i = 0; i < textareas.length; i++) {
                    if (textareas[i].value && textareas[i].value.trim().length > 0) {
                        return true;
                    }
                }
            } catch(e) {}
            return false;
        """)
        if solved:
            return True
    except Exception:
        pass

    return False


def handle_recaptcha(driver, wait, timeout=120):
    """
    Locates and clicks the reCAPTCHA checkbox, then checks if it auto-resolves or requires
    manual image challenge resolution. If an Image Challenge appears, brings Chrome to the foreground,
    alerts the user, and non-intrusively monitors for resolution so the puzzle popup remains fully clickable.
    """
    print("\n[Step 4/6] 🤖 Locating and verifying reCAPTCHA...")
    iframes = driver.find_elements(
        By.CSS_SELECTOR, 
        ".tab-pane.active iframe[src*='recaptcha/api2/anchor'], .tab-pane.show iframe[src*='recaptcha/api2/anchor'], iframe[title='reCAPTCHA'], iframe[src*='recaptcha/api2/anchor']"
    )
    recaptcha_frame = None
    for frame in iframes:
        try:
            if frame.is_displayed():
                recaptcha_frame = frame
                break
        except Exception:
            pass

    if not recaptcha_frame:
        # Fallback to any visible recaptcha iframe
        all_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[title='reCAPTCHA'], iframe[src*='recaptcha']")
        for frame in all_frames:
            try:
                if frame.is_displayed():
                    recaptcha_frame = frame
                    break
            except Exception:
                pass

    if not recaptcha_frame:
        print("   ℹ️ No visible reCAPTCHA iframe detected, continuing...")
        return True

    # Visually highlight reCAPTCHA iframe
    highlight_and_scroll(
        driver, 
        recaptcha_frame, 
        color="#007bff", 
        border="3px solid #007bff", 
        bg_color="rgba(0, 123, 255, 0.12)", 
        duration=0.3
    )

    # Switch inside iframe and click checkbox
    driver.switch_to.frame(recaptcha_frame)
    try:
        checkbox = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, ".recaptcha-checkbox-border, #recaptcha-anchor, .recaptcha-checkbox"
        )))
        try:
            checkbox.click()
        except Exception:
            driver.execute_script("arguments[0].click();", checkbox)
        print("   ✔ Clicked reCAPTCHA checkbox!")
    except Exception as e:
        print(f"   ⚠️ Could not click checkbox directly: {e}")
    finally:
        driver.switch_to.default_content()
        unhighlight(driver, recaptcha_frame)

    # Wait briefly for Google response
    time.sleep(1.5)
    if is_recaptcha_solved(driver):
        print("   ✔ [AUTO-VERIFIED] CAPTCHA passed automatically (Green checkmark)!")
        return True

    # Bring Chrome window to front so the user immediately sees the challenge puzzle
    bring_chrome_to_front(driver)

    # Image puzzle challenge detected -> Prompt user and poll dynamically
    print("\n" + "=" * 75)
    print(" 🔔 [MANUAL CAPTCHA ACTION REQUIRED]")
    print(" 🧩 An Image Selection CAPTCHA challenge appeared in the Chrome browser!")
    print(" 👉 Please solve the image puzzle directly in your open Chrome window.")
    print(f" ⏳ Script is actively waiting for resolution (Timeout: {timeout}s)...")
    print("=" * 75)

    start_wait = time.time()
    last_print_time = 0
    while time.time() - start_wait < timeout:
        if is_recaptcha_solved(driver):
            elapsed = time.time() - start_wait
            print(f"\n   ✔ [CAPTCHA SOLVED] Successfully verified (took {elapsed:.1f}s)! Resuming...")
            time.sleep(0.4)
            return True
        
        current_time = time.time()
        if current_time - last_print_time >= 2:
            time_left = int(timeout - (current_time - start_wait))
            print(f"\r   ⏳ Waiting for user to solve CAPTCHA puzzle in Chrome... ({time_left}s remaining)", end="", flush=True)
            last_print_time = current_time

        time.sleep(1.0)

    print(f"\n   ⚠️ CAPTCHA wait timeout ({timeout}s) reached. Continuing with search...")
    return False


# ==============================================================================
# [SECTION 5] - BROWSER & SELENIUM DRIVER SETUP
# ==============================================================================
def get_driver(download_dir: str, headless: bool = False):
    """
    Configures and initializes Chrome WebDriver with custom download settings,
    anti-detection parameters, popup-blocking disabled, and automatic download triggers.
    """
    os.makedirs(download_dir, exist_ok=True)

    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--window-size=1440,900")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-session-crashed-bubble")
    chrome_options.add_argument("--noerrdialogs")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.popups": 1,
        "profile.default_content_settings.popups": 0
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def wait_for_new_download(download_dir: str, existing_files: set, timeout: int = 60) -> str:
    """
    Monitors the download folder with high-frequency polling and waits until a new file finishes downloading.
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
            time.sleep(0.4)
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(" Done!")
                return file_path
        print(".", end="", flush=True)
        time.sleep(0.4)
    print(" Timed out.")
    return ""


# ==============================================================================
# [SECTION 6] - TERMINAL USER INTERFACE & INPUT VALIDATION
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
    
    # 1. From Date (Auto-detected from Dubai transactions database)
    db_last_date = get_last_transaction_date_from_db("Dubai")
    default_from = db_last_date or FROM_DATE or "01/01/2025"
    if db_last_date:
        print(f"   ℹ️  Auto-detected last Dubai transaction date in DB: {db_last_date}")
    else:
        print(f"   ℹ️  Using default start date: {default_from} (DB date unavailable)")

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

    # 2. To Date (Defaults dynamically to yesterday's date)
    default_to = TO_DATE or (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
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

    print("-" * 75)
    print(f"🎯 Selected Configuration:")
    print(f"   • Module     : Real Estate {selected_tab}")
    print(f"   • From Date  : {from_date}")
    print(f"   • To Date    : {to_date}")
    print(f"   • GDrive URL : {GOOGLE_DRIVE_FOLDER_ID or 'Not configured'}")
    if LOCAL_GDRIVE_PATH and os.path.exists(LOCAL_GDRIVE_PATH):
        print(f"   • Desktop G: : {LOCAL_GDRIVE_PATH}")
    print("-" * 75)
    input("⚡ Press [ENTER] to start scraping...")
    return from_date, to_date, selected_tab


# ==============================================================================
# [SECTION 7] - CORE SCRAPER AUTOMATION WORKFLOW
# ==============================================================================
def run_scraper(from_date: str = None,
                to_date: str = None,
                tab_name: str = TARGET_TAB,
                headless: bool = HEADLESS,
                captcha_timeout: int = CAPTCHA_TIMEOUT,
                drive_folder_id: str = None):
    """
    Main automation engine for Dubai Land Department Open Data portal:
    1. Launches Chrome with custom download settings
    2. Switches to requested data tab (Transactions, Rents, etc.) with visual feedback
    3. Injects date ranges with DOM dispatch events and visible highlights
    4. Automatically clicks Google reCAPTCHA checkbox & handles manual image challenges
    5. Submits search query and dynamically waits for data table rendering
    6. Downloads exported CSV file with visual highlight and uploads directly to Google Drive
    """
    if not from_date:
        from_date = get_last_transaction_date_from_db("Dubai") or FROM_DATE or "01/01/2025"
    if not to_date:
        to_date = TO_DATE or datetime.now().strftime("%d/%m/%Y")
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
        bring_chrome_to_front(driver)
        
        # Dynamic explicit wait for initial page elements to load
        wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "input[placeholder*='Date'], input[id*='pFromDate'], .nav-tabs, form"
        )))
        bring_chrome_to_front(driver)
        print("   ✔ Webpage loaded and form controls ready.")

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
            click_visible(driver, tab_element, name=f"Tab '{tab_name}'", highlight_color="#007bff", duration=0.3)
            # Wait for tab's input to become ready
            wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, f"#{prefix}_pFromDate, input[placeholder*='From Date']"
            )))
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

        # Highlight & set From Date
        highlight_and_scroll(driver, from_date_input, color="#fd7e14", border="3px solid #fd7e14", bg_color="rgba(253, 126, 20, 0.15)", duration=0.2)
        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        """, from_date_input, from_date)
        unhighlight(driver, from_date_input)

        # Highlight & set To Date
        highlight_and_scroll(driver, to_date_input, color="#fd7e14", border="3px solid #fd7e14", bg_color="rgba(253, 126, 20, 0.15)", duration=0.2)
        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        """, to_date_input, to_date)
        unhighlight(driver, to_date_input)

        print(f"   ✔ Dates populated: From '{from_date}' | To '{to_date}'")

        # Step 4: Locate and Verify Google reCAPTCHA
        handle_recaptcha(driver, wait, timeout=captcha_timeout)

        # Step 5: Submit Search Request
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

        # Visually highlight and click Search button
        click_visible(driver, visible_search_btn, name="Search Button", highlight_color="#28a745", duration=0.35)
        print("   ✔ Search button clicked! Waiting for database response...")

        # Dynamic wait for Download CSV button / data table to become ready (avoids rigid sleep)
        print("   ⏳ Dynamically awaiting search results & export button...")
        try:
            visible_csv_btn = WebDriverWait(driver, 40).until(
                EC.element_to_be_clickable((
                    By.XPATH, "//button[contains(text(),'Download as CSV') or contains(@class,'js-ExportCsv')]"
                ))
            )
            print("   ✔ Data loaded and 'Download as CSV' button is ready!")
        except Exception:
            # Fallback search if already rendered
            csv_buttons = driver.find_elements(
                By.XPATH, "//button[contains(text(),'Download as CSV') or contains(@class,'js-ExportCsv')]"
            )
            visible_csv_btn = csv_buttons[0] if csv_buttons else None

        # Step 6: Locate & Trigger CSV Download
        print("\n[Step 6/6] 📥 Triggering CSV Download...")
        if not visible_csv_btn:
            csv_buttons = driver.find_elements(
                By.XPATH, "//button[contains(text(),'Download as CSV') or contains(@class,'js-ExportCsv')]"
            )
            for btn in csv_buttons:
                if btn.is_displayed():
                    visible_csv_btn = btn
                    break

        if visible_csv_btn:
            click_visible(driver, visible_csv_btn, name="Download as CSV", highlight_color="#17a2b8", duration=0.35)
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
            orig_filename = os.path.basename(downloaded_file_path)

            # Generate filename based on scraping date range (e.g. 15aug_to_15sept.csv)
            target_filename = format_range_filename(from_date, to_date, orig_filename)

            # Rename local downloaded file
            renamed_local_path = os.path.join(os.path.dirname(downloaded_file_path), target_filename)
            try:
                if os.path.exists(renamed_local_path) and os.path.abspath(renamed_local_path) != os.path.abspath(downloaded_file_path):
                    os.remove(renamed_local_path)
                os.rename(downloaded_file_path, renamed_local_path)
                downloaded_file_path = renamed_local_path
                filename = target_filename
            except Exception:
                filename = target_filename

            print(f"\n   🎉 File Downloaded: {filename} ({file_size_kb:.2f} KB)")
            print(f"   📁 Local Path     : {downloaded_file_path}")

            # Google Drive Upload
            print("\n" + "=" * 75)
            print(" ☁️   GOOGLE DRIVE UPLOADER")
            print("=" * 75)
            upload_target_folder = drive_folder_id or GOOGLE_DRIVE_FOLDER_ID
            upload_success = upload_file_to_gdrive(
                local_file_path=downloaded_file_path,
                folder_id=upload_target_folder,
                auth_type=AUTH_TYPE,
                service_account_file=SERVICE_ACCOUNT_FILE,
                oauth_credentials_file=OAUTH_CREDENTIALS_FILE,
                oauth_token_file=OAUTH_TOKEN_FILE,
                local_gdrive_path=LOCAL_GDRIVE_PATH,
                target_filename=target_filename
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
        try:
            driver.quit()
        except Exception:
            pass


# ==============================================================================
# [SECTION 8] - CLI ARGUMENT PARSING & SCRIPT ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    print_banner()

    parser = argparse.ArgumentParser(
        description="Dubai Land Department Real Estate Data Scraper & Google Drive Uploader (All-In-One)"
    )
    parser.add_argument("--from-date", type=str, help="Start Date (DD/MM/YYYY)")
    parser.add_argument("--to-date", type=str, help="End Date (DD/MM/YYYY)")
    parser.add_argument("--tab", type=str, help="Data Tab (Transactions, Rents, Project, Valuations, Building, Developer)")
    parser.add_argument("--non-interactive", action="store_true", help="Skip interactive terminal prompts and use config defaults")
    parser.add_argument("--captcha-timeout", type=int, default=CAPTCHA_TIMEOUT, help="Maximum seconds to wait for manual CAPTCHA solving")
    parser.add_argument("--drive-folder-id", type=str, default=None, help="Google Drive folder ID or URL (defaults to Dubai input folder from CITY_CONFIG)")
    parser.add_argument("--db", type=str, default="nilesh", help="PostgreSQL target database (default: nilesh)")

    args = parser.parse_args()

    active_db = args.db or "nilesh"
    active_db_params = {"host": "localhost", "port": 5432, "database": active_db, "user": "postgres", "password": "nilesh"}

    # Determine execution mode:
    # If user provided CLI flags or --non-interactive, run directly; otherwise prompt in interactive terminal
    if args.from_date or args.to_date or args.non_interactive:
        f_date = args.from_date or get_last_transaction_date_from_db("Dubai", db_params=active_db_params) or FROM_DATE
        t_date = args.to_date or TO_DATE or (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
        tab = args.tab or TARGET_TAB
    else:
        f_date, t_date, tab = get_terminal_inputs()

    run_scraper(
        from_date=f_date,
        to_date=t_date,
        tab_name=tab,
        headless=False,
        captcha_timeout=args.captcha_timeout,
        drive_folder_id=args.drive_folder_id or GOOGLE_DRIVE_FOLDER_ID
    )
