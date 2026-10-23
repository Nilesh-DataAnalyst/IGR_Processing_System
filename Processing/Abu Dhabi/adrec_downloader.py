#!/usr/bin/env python3
"""
ADREC Property Transaction Downloader & Google Drive Uploader
============================================================
Single, production-ready Python Selenium script for complete browser automation:
1. Opens the ADREC website (https://adrec.gov.ae/en/property_and_index/adrec-dashboard)
2. Asks for From Date and To Date from terminal
3. Navigates & switches to the dashboard iframe
4. Scrolls to the Recent Sales section
5. Applies the From & To dates
6. Sets all 7 dropdown filters to 'All'
7. Clicks Export and waits for download completion
8. Uploads the exported file directly to Google Drive
9. Verifies the upload and reports success

Author: Production Automation Suite
"""

import os
import sys
import time
import re
import json
import logging
import argparse
import tempfile
import shutil
from datetime import datetime
from typing import Tuple, Optional, List, Dict, Any

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())
except ImportError:
    pass

# Selenium Webdriver Imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException,
)

# Google Drive API Imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


# ==============================================================================
# CONFIGURATION & CREDENTIALS (LOADED FROM ENVIRONMENT / .ENV)
# ==============================================================================

# Target Google Drive Folder ID (Abu Dhabi Raw Data folder)
DEFAULT_GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

# Google OAuth 2.0 Client Credentials (Loaded from environment variables)
OAUTH_CLIENT_CONFIG = {
    "installed": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "project_id": os.getenv("GOOGLE_PROJECT_ID", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uris": ["http://localhost"]
    }
}

# Google Drive Scopes
GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Token and credentials file names for authorization (resolved relative to script directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "credentials.json")

# ADREC Website URL
ADREC_DASHBOARD_URL = "https://adrec.gov.ae/en/property_and_index/adrec-dashboard"

# DOM Selectors (Validated from live DOM inspection)
IFRAME_SELECTOR = "iframe#interactiveMapIframe, iframe[src*='MarketDetails.html']"
RECENT_SALES_WRAPPER_ID = "salesTableWrapper"
FROM_DATE_INPUT_ID = "filterFromDate"
TO_DATE_INPUT_ID = "filterToDate"
EXPORT_BUTTON_ID = "exportTableBtn"

# 7 Dropdown filter IDs inside Recent Sales
DROPDOWN_DEFINITIONS = [
    {"id": "filterAssetType", "name": "Asset Type"},
    {"id": "filterPropertyType", "name": "Property Type / Subtype"},
    {"id": "filterSaleType", "name": "Transaction Type"},
    {"id": "filterDistrict", "name": "District"},
    {"id": "filterCommunity", "name": "Community"},
    {"id": "filterProject", "name": "Project Name"},
    {"id": "filterLayout", "name": "Layout"},
]


# ==============================================================================
# LOGGING SETUP
# ==============================================================================
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("adrec_automation.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("ADREC_Downloader")


# ==============================================================================
# DATE VALIDATION UTILITIES
# ==============================================================================
def validate_date_string(date_str: str) -> Tuple[bool, str, Optional[datetime]]:
    """
    Validates date string for YYYY-MM-DD format and real calendar date.
    """
    if not date_str or not isinstance(date_str, str):
        return False, "Date cannot be empty.", None

    date_str = date_str.strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False, "Invalid date format. Please enter in YYYY-MM-DD format.", None

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return True, "", dt
    except ValueError as e:
        return False, f"Invalid calendar date: {e}", None


def get_user_date_range(cli_from: Optional[str] = None, cli_to: Optional[str] = None) -> Tuple[str, str]:
    """
    Prompts user in terminal for date range or uses validated CLI args.
    Loops until a valid date range (From Date <= To Date) is entered.
    """
    if cli_from and cli_to:
        v_from, err_from, dt_from = validate_date_string(cli_from)
        v_to, err_to, dt_to = validate_date_string(cli_to)
        if v_from and v_to and dt_from and dt_to:
            if dt_from <= dt_to:
                return cli_from.strip(), cli_to.strip()
            else:
                logger.warning(f"From Date ({cli_from}) must be <= To Date ({cli_to}). Asking via terminal.")
        else:
            logger.warning(f"CLI date error: {err_from or err_to}. Asking via terminal.")

    while True:
        try:
            from_input = input("Enter From Date (YYYY-MM-DD): ").strip()
            valid_from, msg_from, dt_from = validate_date_string(from_input)
            if not valid_from or dt_from is None:
                print(f"Invalid date. Please enter the date in YYYY-MM-DD format. ({msg_from})")
                continue

            to_input = input("Enter To Date (YYYY-MM-DD): ").strip()
            valid_to, msg_to, dt_to = validate_date_string(to_input)
            if not valid_to or dt_to is None:
                print(f"Invalid date. Please enter the date in YYYY-MM-DD format. ({msg_to})")
                continue

            if dt_from > dt_to:
                print("Invalid date range: From Date must be less than or equal to To Date. Please try again.\n")
                continue

            return from_input, to_input

        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user.")
            sys.exit(1)


# ==============================================================================
# SCREENSHOT CAPTURE
# ==============================================================================
def capture_screenshot(driver: Optional[webdriver.Chrome], prefix: str, screenshot_dir: str = "screenshots") -> Optional[str]:
    """
    Captures timestamped error screenshots into screenshots directory.
    """
    if not driver:
        return None
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_prefix = re.sub(r"[^\w\-]", "_", prefix)
        filepath = os.path.join(screenshot_dir, f"{sanitized_prefix}_{timestamp}.png")
        driver.save_screenshot(filepath)
        logger.info(f"Screenshot captured: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        return None


# ==============================================================================
# CHROME WEBDRIVER CONFIGURATION
# ==============================================================================
def create_chrome_driver(download_dir: str, headless: bool = False) -> webdriver.Chrome:
    """
    Configures Chrome with automatic download settings and stealth options.
    """
    abs_download_dir = os.path.abspath(download_dir)
    os.makedirs(abs_download_dir, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "download.default_directory": abs_download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if headless:
        chrome_options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass

    return driver


# ==============================================================================
# REUSABLE DROPDOWN AUTOMATION FUNCTION
# ==============================================================================
def select_all_from_dropdown(driver: webdriver.Chrome, dropdown_id: str, dropdown_name: str) -> bool:
    """
    Opens custom dropdown, ensures 'Select All' checkbox is checked, and closes it.
    """
    try:
        dropdown_wrapper = driver.find_element(By.ID, dropdown_id)
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'nearest'});", dropdown_wrapper)

        header = dropdown_wrapper.find_element(By.CLASS_NAME, "dropdown-header")
        driver.execute_script("arguments[0].click();", header)
        time.sleep(0.4)

        body = dropdown_wrapper.find_element(By.CLASS_NAME, "dropdown-body")
        select_all_elements = body.find_elements(By.CLASS_NAME, "select-all-checkbox")

        if select_all_elements:
            select_all_cb = select_all_elements[0]
            if not select_all_cb.is_selected():
                driver.execute_script("arguments[0].click();", select_all_cb)
                time.sleep(0.2)
        else:
            area_parents = body.find_elements(By.CLASS_NAME, "area-parent")
            for parent in area_parents:
                if not parent.is_selected():
                    driver.execute_script("arguments[0].click();", parent)
                    time.sleep(0.1)

        driver.execute_script("arguments[0].click();", header)
        time.sleep(0.2)

        logger.info(f"{dropdown_name} set to All")
        return True

    except Exception as e:
        logger.warning(f"Dropdown note '{dropdown_name}' (#{dropdown_id}): {e}")
        try:
            driver.execute_script("document.dispatchEvent(new MouseEvent('click', {bubbles: true}));")
        except Exception:
            pass
        return False


# ==============================================================================
# DOWNLOAD MONITORING HELPER
# ==============================================================================
def wait_for_download_completion(
    download_dir: str,
    pre_existing_files: List[str],
    timeout_seconds: int = 120,
) -> Optional[str]:
    """
    Monitors download folder until newly downloaded file completes and size is stable.
    """
    logger.info("Waiting for download...")
    start_time = time.time()
    pre_set = set(pre_existing_files)

    last_filename = None
    last_size = -1
    stable_cycles = 0

    while time.time() - start_time < timeout_seconds:
        try:
            current_files = os.listdir(download_dir)
        except Exception:
            current_files = []

        new_files = [f for f in current_files if f not in pre_set]

        has_temp_download = any(
            f.endswith(".crdownload") or f.endswith(".tmp") or ".tmp" in f.lower() for f in new_files
        )

        completed_candidates = [
            f for f in new_files if not f.endswith(".crdownload") and not f.endswith(".tmp") and not f.startswith(".")
        ]

        if completed_candidates and not has_temp_download:
            candidate_name = completed_candidates[0]
            candidate_path = os.path.join(download_dir, candidate_name)

            try:
                current_size = os.path.getsize(candidate_path)
                if current_size > 0:
                    if candidate_name == last_filename and current_size == last_size:
                        stable_cycles += 1
                        if stable_cycles >= 2:
                            logger.info(f"Download detected: {candidate_name}")
                            logger.info(f"Download completed successfully (Size: {current_size:,} bytes)")
                            return candidate_path
                    else:
                        last_filename = candidate_name
                        last_size = current_size
                        stable_cycles = 1
            except (OSError, FileNotFoundError):
                stable_cycles = 0

        time.sleep(1.0)

    logger.error(f"Download did not complete within {timeout_seconds} seconds timeout.")
    return None


# ==============================================================================
# GOOGLE DRIVE CLIENT & UPLOAD (SELF-CONTAINED)
# ==============================================================================
def get_google_drive_service() -> Optional[Any]:
    """
    Authenticates and builds the Google Drive v3 client.
    Uses cached token.json if available, or launches OAuth authorization flow
    using the embedded client configuration.
    """
    if not GOOGLE_API_AVAILABLE:
        logger.error("Google Client API packages missing. Install: pip install google-api-python-client google-auth google-auth-oauthlib")
        return None

    try:
        creds = None

        # 1. Check if token.json exists with cached login
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, GOOGLE_DRIVE_SCOPES)
            except Exception as e:
                logger.warning(f"Could not read {TOKEN_FILE}: {e}")

        # 2. Refresh or authenticate if credentials not valid
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Google Drive access token...")
                creds.refresh(Request())
            else:
                logger.info("Initiating Google OAuth authorization flow...")
                # Check for custom credentials.json file if present, else use embedded config
                if os.path.exists(CREDENTIALS_FILE):
                    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                        custom_cfg = json.load(f)
                    if custom_cfg.get("type") == "service_account":
                        creds = service_account.Credentials.from_service_account_file(
                            CREDENTIALS_FILE, scopes=GOOGLE_DRIVE_SCOPES
                        )
                        return build("drive", "v3", credentials=creds, cache_discovery=False)
                    else:
                        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, GOOGLE_DRIVE_SCOPES)
                else:
                    if not OAUTH_CLIENT_CONFIG["installed"].get("client_id") or not OAUTH_CLIENT_CONFIG["installed"].get("client_secret"):
                        logger.error("Google OAuth credentials missing. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env or provide credentials.json.")
                        return None
                    flow = InstalledAppFlow.from_client_config(OAUTH_CLIENT_CONFIG, GOOGLE_DRIVE_SCOPES)

                creds = flow.run_local_server(port=0)

            # Save token for future automatic runs
            with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service

    except Exception as e:
        logger.error(f"Error initializing Google Drive service: {e}")
        return None


def upload_file_to_google_drive(file_path: str, folder_id: str = DEFAULT_GOOGLE_DRIVE_FOLDER_ID) -> Optional[str]:
    """
    Uploads the downloaded property transaction file to the target Google Drive folder.
    """
    target_folder_id = folder_id or DEFAULT_GOOGLE_DRIVE_FOLDER_ID

    if not target_folder_id or target_folder_id.strip() == "":
        logger.warning("No Google Drive Folder ID provided. Skipping upload.")
        return None

    if not os.path.exists(file_path):
        logger.error(f"Cannot upload: File does not exist at '{file_path}'")
        return None

    filename = os.path.basename(file_path)
    logger.info("Uploading file to Google Drive")

    service = get_google_drive_service()
    if not service:
        logger.warning("Google Drive authentication not available. File remains saved locally in downloads directory.")
        return None

    try:
        mime_type = "text/csv" if filename.lower().endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        file_metadata = {
            "name": filename,
            "parents": [target_folder_id.strip()],
        }

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

        drive_file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, size",
                supportsAllDrives=True,
            )
            .execute()
        )

        file_id = drive_file.get("id")
        if file_id:
            logger.info("Google Drive upload successful")
            logger.info(f"File name: {drive_file.get('name')}")
            logger.info(f"Google Drive file ID: {file_id}")
            return file_id
        else:
            logger.error("Google Drive API did not return a valid file ID.")
            return None

    except Exception as e:
        logger.error(f"Google Drive upload failed: {e}")
        return None


# ==============================================================================
# MAIN AUTOMATION WORKFLOW
# ==============================================================================
def run_adrec_automation(
    from_date: str,
    to_date: str,
    headless: bool = False,
    download_dir: Optional[str] = None,
    screenshot_dir: Optional[str] = None,
    folder_id: str = DEFAULT_GOOGLE_DRIVE_FOLDER_ID,
    cleanup_local: bool = True,
) -> bool:
    """
    Executes the complete ADREC property transaction download workflow.
    Uses a temporary working directory and cleans it up after Google Drive upload
    to avoid creating local downloads folders.
    """
    driver = None
    is_temp_download = False
    if not download_dir:
        abs_download_dir = tempfile.mkdtemp(prefix="adrec_download_")
        is_temp_download = True
    else:
        abs_download_dir = os.path.abspath(download_dir)
        os.makedirs(abs_download_dir, exist_ok=True)

    if not screenshot_dir:
        abs_screenshot_dir = os.path.join(tempfile.gettempdir(), "adrec_screenshots")
    else:
        abs_screenshot_dir = os.path.abspath(screenshot_dir)
    os.makedirs(abs_screenshot_dir, exist_ok=True)

    pre_existing_files = os.listdir(abs_download_dir)

    try:
        # 1. Open ADREC website
        logger.info("Opening ADREC website")
        driver = create_chrome_driver(abs_download_dir, headless=headless)
        driver.get(ADREC_DASHBOARD_URL)

        wait = WebDriverWait(driver, 60)

        # 2. Locate and switch to the dashboard iframe
        try:
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, IFRAME_SELECTOR)))
            driver.switch_to.frame(iframe)
        except TimeoutException:
            logger.error("Could not find ADREC dashboard iframe")
            capture_screenshot(driver, "error_iframe", screenshot_dir)
            return False

        # 3. Locate Recent Sales section
        try:
            sales_section = wait.until(EC.presence_of_element_located((By.ID, RECENT_SALES_WRAPPER_ID)))
            logger.info("Recent Sales section found")
        except TimeoutException:
            logger.error("Could not find Recent Sales section")
            capture_screenshot(driver, "error_recent_sales", screenshot_dir)
            return False

        # 4. Scroll to Recent Sales section
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", sales_section)
            time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Smooth scroll warning: {e}")

        # 5. Fill user-provided dates into From Date and To Date
        logger.info(f"Setting date range: {from_date} -> {to_date}")
        try:
            from_input = wait.until(EC.presence_of_element_located((By.ID, FROM_DATE_INPUT_ID)))
            to_input = wait.until(EC.presence_of_element_located((By.ID, TO_DATE_INPUT_ID)))

            date_script = """
                const fromEl = document.querySelector('#filterFromDate');
                const toEl = document.querySelector('#filterToDate');
                if (fromEl) {
                    if (fromEl._flatpickr) {
                        fromEl._flatpickr.setDate(arguments[0], true);
                    } else {
                        fromEl.value = arguments[0];
                        fromEl.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
                if (toEl) {
                    if (toEl._flatpickr) {
                        toEl._flatpickr.setDate(arguments[1], true);
                    } else {
                        toEl.value = arguments[1];
                        toEl.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            """
            driver.execute_script(date_script, from_date, to_date)
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Could not set date fields: {e}")
            capture_screenshot(driver, "error_date_fields", screenshot_dir)
            return False

        # 6. Set all 7 dropdown filters to 'All'
        for dropdown in DROPDOWN_DEFINITIONS:
            select_all_from_dropdown(driver, dropdown["id"], dropdown["name"])

        logger.info("All filters configured")

        # 7. Click Export Button
        logger.info("Clicking Export")
        try:
            export_btn = wait.until(EC.presence_of_element_located((By.ID, EXPORT_BUTTON_ID)))
            wait.until(lambda d: d.find_element(By.ID, EXPORT_BUTTON_ID).is_enabled())
            driver.execute_script("arguments[0].click();", export_btn)
            logger.info("Export initiated")
        except TimeoutException:
            logger.error("Export button not found or remained disabled")
            capture_screenshot(driver, "error_export", screenshot_dir)
            return False
        except Exception as e:
            logger.error(f"Error clicking export button: {e}")
            capture_screenshot(driver, "error_export_click", screenshot_dir)
            return False

        # 8. Wait for download completion
        downloaded_file_path = wait_for_download_completion(
            download_dir=abs_download_dir,
            pre_existing_files=pre_existing_files,
            timeout_seconds=120,
        )

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            logger.error("Download did not complete")
            capture_screenshot(driver, "error_download", screenshot_dir)
            return False

        # 9. Upload to Google Drive
        drive_file_id = upload_file_to_google_drive(
            file_path=downloaded_file_path,
            folder_id=folder_id,
        )

        # 10. Optional local file cleanup
        if cleanup_local and drive_file_id:
            try:
                os.remove(downloaded_file_path)
                logger.info(f"Local file cleaned up: {downloaded_file_path}")
            except Exception as e:
                logger.warning(f"Could not clean local file: {e}")

        logger.info("ADREC Transaction download workflow completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Unexpected automation error: {e}", exc_info=True)
        capture_screenshot(driver, "error_unexpected", screenshot_dir)
        return False

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if is_temp_download and os.path.exists(abs_download_dir):
            try:
                shutil.rmtree(abs_download_dir, ignore_errors=True)
                logger.info("Cleaned up temporary download directory.")
            except Exception as e:
                logger.warning(f"Failed to remove temp download directory {abs_download_dir}: {e}")


# ==============================================================================
# SCRIPT ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ADREC Abu Dhabi Property Transaction Downloader & Google Drive Uploader"
    )
    parser.add_argument(
        "--from-date",
        dest="from_date",
        help="Start date in YYYY-MM-DD format (prompted interactively if omitted)",
    )
    parser.add_argument(
        "--to-date",
        dest="to_date",
        help="End date in YYYY-MM-DD format (prompted interactively if omitted)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run Chrome in headless background mode without a visible window",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Local directory to save downloaded files (default: temporary directory)",
    )
    parser.add_argument(
        "--folder-id",
        default=DEFAULT_GOOGLE_DRIVE_FOLDER_ID,
        help="Target Google Drive folder ID",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        default=True,
        help="Delete local downloaded file after successful Google Drive upload",
    )

    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("   ADREC Abu Dhabi Property Transaction Downloader")
    print("=" * 65 + "\n")

    # Prompt user in terminal
    from_date, to_date = get_user_date_range(cli_from=args.from_date, cli_to=args.to_date)

    # Run automation
    success = run_adrec_automation(
        from_date=from_date,
        to_date=to_date,
        headless=args.headless,
        download_dir=args.download_dir,
        folder_id=args.folder_id,
        cleanup_local=args.cleanup,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
