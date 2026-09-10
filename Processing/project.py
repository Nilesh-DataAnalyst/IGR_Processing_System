import os
import re
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import psycopg2
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

warnings.filterwarnings("ignore")

HEADER = "\033[95m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ============================================================
# CONFIGURATION & CONSTANTS
# ============================================================

from divisor import SALEABLE_TO_CARPET_DIVISOR_BY_CITY
from city_config import CITY_CONFIG, get_city_config, extract_folder_id

BUILDUP_TO_CARPET_DIVISOR = 1.2

DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "database": "nilesh",
    "user": "postgres",
    "password": "nilesh",
}

# Initial default city configuration (Pune)
CURRENT_CITY_CONFIG = get_city_config("pune")
CURRENT_CITY_KEY = "pune"

DEFAULT_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["final_drive_url"]
DEFAULT_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG["final_drive_id"]

DEFAULT_INPUT_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["input_drive_url"]
DEFAULT_INPUT_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG["input_drive_id"]

DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["manual_correction_drive_url"]
DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG["manual_correction_drive_id"]


def set_active_city(city_key_or_id: str | int = "pune") -> dict:
    """
    Sets the active city and dynamically configures:
    1. Input, Manual Correction, and Final Google Drive URLs and IDs
    2. Target City ID and Name
    3. Saleable to Carpet divisor (from divisor.py)
    """
    global CURRENT_CITY_CONFIG, CURRENT_CITY_KEY
    global DEFAULT_DRIVE_FOLDER_URL, DEFAULT_DRIVE_FOLDER_ID
    global DEFAULT_INPUT_DRIVE_FOLDER_URL, DEFAULT_INPUT_DRIVE_FOLDER_ID
    global DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL, DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_ID

    CURRENT_CITY_CONFIG = get_city_config(city_key_or_id)
    CURRENT_CITY_KEY = CURRENT_CITY_CONFIG.get("key", str(city_key_or_id).lower())

    DEFAULT_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["final_drive_url"]
    DEFAULT_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG.get("final_drive_id") or extract_folder_id(DEFAULT_DRIVE_FOLDER_URL)

    DEFAULT_INPUT_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["input_drive_url"]
    DEFAULT_INPUT_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG.get("input_drive_id") or extract_folder_id(DEFAULT_INPUT_DRIVE_FOLDER_URL)

    DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL = CURRENT_CITY_CONFIG["manual_correction_drive_url"]
    DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_ID = CURRENT_CITY_CONFIG.get("manual_correction_drive_id") or extract_folder_id(DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL)

    return CURRENT_CITY_CONFIG




def resolve_drive_directory(drive_target: str = DEFAULT_DRIVE_FOLDER_URL) -> str:
    """Resolves a Google Drive folder URL, folder ID, or local Drive path to a writable local directory on G:."""
    if not drive_target or not str(drive_target).strip():
        return None

    # If it is already an existing directory, test write access
    if os.path.isdir(str(drive_target).strip()):
        return str(drive_target).strip()

    # Extract folder ID if URL or string provided
    clean_target = str(drive_target).strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    if not folder_id:
        return None

    # Look up in Google Drive Desktop shortcut targets
    base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
    if os.path.exists(base_shortcut_path):
        try:
            sub_items = [
                os.path.join(base_shortcut_path, d)
                for d in os.listdir(base_shortcut_path)
                if os.path.isdir(os.path.join(base_shortcut_path, d))
            ]
            # Prefer 'Final processed file' if present
            for sub in sub_items:
                if "final processed" in os.path.basename(sub).lower():
                    return sub
            # Otherwise return any writable subdirectory
            for sub in sub_items:
                test_file = os.path.join(sub, ".test_write.tmp")
                try:
                    with open(test_file, "w") as f:
                        f.write("1")
                    os.remove(test_file)
                    return sub
                except Exception:
                    continue
        except Exception:
            pass
        return base_shortcut_path

    # Fallback checks on G: drive
    if os.path.exists(r"G:\My Drive"):
        return r"G:\My Drive"

    return None


def resolve_manual_correction_directory(
    drive_target: str = DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL,
    location_name: str = None,
) -> str:
    """
    Resolves the Google Drive folder for Manually Corrected files.
    If location_name is given, ensures a subfolder for that location is created and returned.
    """
    if not drive_target or not str(drive_target).strip():
        return None

    clean_target = str(drive_target).strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    if not folder_id:
        return None

    base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
    manual_root = None

    if os.path.exists(base_shortcut_path):
        sub_items = [
            os.path.join(base_shortcut_path, d)
            for d in os.listdir(base_shortcut_path)
            if os.path.isdir(os.path.join(base_shortcut_path, d))
        ]
        for sub in sub_items:
            if "manually corrected" in os.path.basename(sub).lower():
                manual_root = sub
                break
        if not manual_root and sub_items:
            manual_root = sub_items[0]
        elif not manual_root:
            manual_root = base_shortcut_path
    elif os.path.isdir(str(drive_target)):
        manual_root = drive_target

    if not manual_root or not os.path.exists(manual_root):
        return None

    if location_name:
        loc_dir = os.path.join(manual_root, location_name)
        os.makedirs(loc_dir, exist_ok=True)
        return loc_dir

    return manual_root


def get_manual_corrected_file(
    default_file: str = None,
    drive_url: str = DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL,
) -> tuple:
    """
    Lists available location folders in Google Drive '3. Manually Corrected' directory,
    allows selecting a location and file, while keeping default_file as the default on Enter.
    Also supports custom manual file path entry.
    """
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 7/20] Loading Manually Corrected File...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

    clean_target = str(drive_url).strip() if drive_url else ""
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    manual_root = None
    if folder_id:
        base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
        if os.path.exists(base_shortcut_path):
            for d in os.listdir(base_shortcut_path):
                sub = os.path.join(base_shortcut_path, d)
                if os.path.isdir(sub) and "manually corrected" in d.lower():
                    manual_root = sub
                    break
            if not manual_root:
                manual_root = base_shortcut_path
    elif clean_target and os.path.isdir(clean_target):
        manual_root = clean_target

    location_dict = {}
    valid_extensions = (".xlsx", ".xls", ".csv")

    if manual_root and os.path.exists(manual_root):
        for root, dirs, files in os.walk(manual_root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            excel_files = [
                f for f in files
                if f.lower().endswith(valid_extensions) and not f.startswith("~$")
            ]
            if excel_files:
                loc_name = os.path.basename(root)
                if loc_name.lower() != os.path.basename(manual_root).lower():
                    location_dict[loc_name] = {
                        "folder_path": root,
                        "files": [os.path.join(root, f) for f in excel_files],
                    }

    selected_file = None

    if location_dict:
        print(f"  {CYAN}🌐 Google Drive :{RESET} {drive_url}")
        print(f"  {CYAN}📂 Drive Path   :{RESET} {manual_root}")
        print(f"  {CYAN}📂 Available Location Folders in 3. Manually Corrected:{RESET}")
        print(f"{HEADER}{'-' * 60}{RESET}")

        locations = sorted(list(location_dict.keys()))
        for idx, loc in enumerate(locations, 1):
            file_count = len(location_dict[loc]["files"])
            sample_file = os.path.basename(location_dict[loc]["files"][0])
            print(f"  {CYAN}[{idx}]{RESET} {BOLD}{loc}{RESET} ({file_count} file{'s' if file_count > 1 else ''}: {sample_file})")
        print(f"  {CYAN}[0]{RESET} Enter path manually")
        print(f"{HEADER}{'-' * 60}{RESET}")

        default_candidate = default_file if (default_file and os.path.exists(default_file)) else None
        if not default_candidate and locations:
            sorted_init = sorted(
                location_dict[locations[0]]["files"],
                key=lambda f: 0 if ("_for_manual" in f.lower() or "_corrected" in f.lower()) else 1,
            )
            default_candidate = sorted_init[0]

        default_hint = f" [default: {default_candidate}]" if default_candidate else ""

        while True:
            prompt_text = f"\n{YELLOW}Press Enter to use default{default_hint},\nor select location (1 to {len(locations)}) / enter path: {RESET}"
            user_choice = input(prompt_text).strip().strip('"')

            if not user_choice:
                if default_candidate:
                    selected_file = default_candidate
                    break
                else:
                    print(f"{YELLOW}No default available. Please select an option.{RESET}")
                    continue

            if user_choice == "0":
                manual_path = input(f"{YELLOW}Please provide Manual Corrected File path: {RESET}").strip().strip('"')
                selected_file = manual_path
                break

            if os.path.exists(user_choice) or os.path.isabs(user_choice):
                selected_file = user_choice
                break

            if user_choice.isdigit() and 1 <= int(user_choice) <= len(locations):
                chosen_loc = locations[int(user_choice) - 1]
            else:
                chosen_loc = next((l for l in locations if l.lower() == user_choice.lower()), None)

            if chosen_loc:
                loc_files = location_dict[chosen_loc]["files"]
                sorted_files = sorted(
                    loc_files,
                    key=lambda f: 0 if ("_for_manual" in f.lower() or "_corrected" in f.lower()) else 1,
                )
                if len(sorted_files) == 1:
                    selected_file = sorted_files[0]
                    break
                else:
                    print(f"\n{CYAN}Files in '{chosen_loc}':{RESET}")
                    for f_idx, f_path in enumerate(sorted_files, 1):
                        print(f"  {CYAN}[{f_idx}]{RESET} {os.path.basename(f_path)}")
                    while True:
                        f_choice = input(f"\n{YELLOW}Select file (1 to {len(sorted_files)}) [default: 1]: {RESET}").strip()
                        if not f_choice or f_choice == "1":
                            selected_file = sorted_files[0]
                            break
                        if f_choice.isdigit() and 1 <= int(f_choice) <= len(sorted_files):
                            selected_file = sorted_files[int(f_choice) - 1]
                            break
                        print(f"{RED}❌ Invalid selection. Please enter 1 to {len(sorted_files)}.{RESET}")
                    break

            print(f"{RED}❌ Invalid selection '{user_choice}'. Please enter 1 to {len(locations)}, a path, or press Enter for default.{RESET}")
    else:
        default_hint = f" [default: {default_file}]" if default_file else ""
        user_input = input(f"{YELLOW}Please provide Manual Corrected File path{default_hint}: {RESET}").strip().strip('"')
        selected_file = user_input if user_input else (default_file if default_file else "")

    print(f"\n  {CYAN}📖 Loading:{RESET} {selected_file}")
    df = pd.read_excel(selected_file, engine="openpyxl")
    print(f"{GREEN}✓ [STEP 7/20] Loaded {len(df)} rows from manual corrected file.{RESET}")
    return selected_file, df


def get_final_processed_file(
    default_file: str = None,
    drive_url: str = DEFAULT_DRIVE_FOLDER_URL,
) -> str:
    """
    Lists available location folders in Google Drive '4. Final processed file' directory,
    allows selecting a location and file, while keeping default_file as the default on Enter.
    Also supports custom manual file path entry.
    """
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 19/20] Loading Final Processed File for Parquet Conversion...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

    clean_target = str(drive_url).strip() if drive_url else ""
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    final_root = None
    if folder_id:
        base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
        if os.path.exists(base_shortcut_path):
            for d in os.listdir(base_shortcut_path):
                sub = os.path.join(base_shortcut_path, d)
                if os.path.isdir(sub) and "final processed" in d.lower():
                    final_root = sub
                    break
            if not final_root:
                final_root = base_shortcut_path
    elif clean_target and os.path.isdir(clean_target):
        final_root = clean_target

    location_dict = {}
    valid_extensions = (".xlsx", ".xls", ".csv")

    if final_root and os.path.exists(final_root):
        for root, dirs, files in os.walk(final_root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            excel_files = [
                f for f in files
                if f.lower().endswith(valid_extensions) and not f.startswith("~$")
            ]
            if excel_files:
                loc_name = os.path.basename(root)
                if loc_name.lower() != os.path.basename(final_root).lower():
                    location_dict[loc_name] = {
                        "folder_path": root,
                        "files": [os.path.join(root, f) for f in excel_files],
                    }

    selected_file = None

    if location_dict:
        print(f"  {CYAN}🌐 Google Drive Target :{RESET} {drive_url}")
        print(f"  {CYAN}📂 Drive Path          :{RESET} {final_root}")
        print(f"  {CYAN}📂 Available Location Folders in 4. Final processed file:{RESET}")
        print(f"{HEADER}{'-' * 60}{RESET}")

        locations = sorted(list(location_dict.keys()))
        for idx, loc in enumerate(locations, 1):
            file_count = len(location_dict[loc]["files"])
            sample_file = os.path.basename(location_dict[loc]["files"][0])
            print(f"  {CYAN}[{idx}]{RESET} {BOLD}{loc}{RESET} ({file_count} file{'s' if file_count > 1 else ''}: {sample_file})")
        print(f"  {CYAN}[0]{RESET} Enter path manually")
        print(f"{HEADER}{'-' * 60}{RESET}")

        default_candidate = default_file if (default_file and os.path.exists(default_file)) else None
        if not default_candidate and locations:
            # Sort files by modification time (most recent first)
            sorted_init = sorted(
                location_dict[locations[0]]["files"],
                key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
                reverse=True,
            )
            default_candidate = sorted_init[0]

        default_hint = f" [default: {default_candidate}]" if default_candidate else ""

        while True:
            prompt_text = f"\n{YELLOW}Press Enter to use default{default_hint},\nor select location (1 to {len(locations)}) / enter path: {RESET}"
            user_choice = input(prompt_text).strip().strip('"')

            if not user_choice:
                if default_candidate:
                    selected_file = default_candidate
                    break
                else:
                    print(f"{YELLOW}No default available. Please select an option.{RESET}")
                    continue

            if user_choice == "0":
                manual_path = input(f"{YELLOW}Please provide Final Processed File path: {RESET}").strip().strip('"')
                selected_file = manual_path
                break

            if os.path.exists(user_choice) or os.path.isabs(user_choice):
                selected_file = user_choice
                break

            if user_choice.isdigit() and 1 <= int(user_choice) <= len(locations):
                chosen_loc = locations[int(user_choice) - 1]
            else:
                chosen_loc = next((l for l in locations if l.lower() == user_choice.lower()), None)

            if chosen_loc:
                loc_files = location_dict[chosen_loc]["files"]
                sorted_files = sorted(
                    loc_files,
                    key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
                    reverse=True,
                )
                if len(sorted_files) == 1:
                    selected_file = sorted_files[0]
                    break
                else:
                    print(f"\n{CYAN}Files in '{chosen_loc}':{RESET}")
                    for f_idx, f_path in enumerate(sorted_files, 1):
                        print(f"  {CYAN}[{f_idx}]{RESET} {os.path.basename(f_path)}")
                    while True:
                        f_choice = input(f"\n{YELLOW}Select file (1 to {len(sorted_files)}) [default: 1]: {RESET}").strip()
                        if not f_choice or f_choice == "1":
                            selected_file = sorted_files[0]
                            break
                        if f_choice.isdigit() and 1 <= int(f_choice) <= len(sorted_files):
                            selected_file = sorted_files[int(f_choice) - 1]
                            break
                        print(f"{RED}❌ Invalid selection. Please enter 1 to {len(sorted_files)}.{RESET}")
                    break

            print(f"{RED}❌ Invalid selection '{user_choice}'. Please enter 1 to {len(locations)}, a path, or press Enter for default.{RESET}")
    else:
        default_hint = f" [default: {default_file}]" if default_file else ""
        user_input = input(f"{YELLOW}Please provide Final Processed File path{default_hint}: {RESET}").strip().strip('"')
        selected_file = user_input if user_input else (default_file if default_file else "")

    while not selected_file or not os.path.exists(selected_file):
        print(f"{RED}❌ File does not exist: '{selected_file}'{RESET}")
        selected_file = input(f"{YELLOW}Please provide a valid file path: {RESET}").strip().strip('"')

    print(f"\n  {GREEN}✓ Selected Final Processed File:{RESET} {BOLD}{selected_file}{RESET}")
    return selected_file



def prompt_share_correction_file(
    file_path: str,
    location_name: str = None,
    drive_url: str = DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL,
):
    """
    Prompts the user if they wish to share the manual correction file with colleagues.
    Sharing is completely optional. Can send an email with the file attached or provide the Drive link.
    """
    print(f"\n{HEADER}{'-' * 60}{RESET}")
    print(f"{CYAN}📤 [OPTIONAL] SHARE CORRECTION FILE{RESET}")
    print(f"  {CYAN}📄 File      :{RESET} {BOLD}{os.path.basename(file_path)}{RESET}")
    print(f"  {CYAN}🌐 Drive Link:{RESET} {drive_url}")
    print(f"{HEADER}{'-' * 60}{RESET}")

    share_choice = (
        input(
            f"{YELLOW}Would you like to share this correction file with someone? (y/n) [default: n]: {RESET}"
        )
        .strip()
        .lower()
    )

    if share_choice not in ["y", "yes"]:
        print(f"{BLUE}ℹ File sharing skipped.{RESET}")
        return

    contacts = [
        ("Pankaj Binnar", "pankaj@sigmavalue.co.in"),
        ("Sarvesh", "sarvesh@sigmavalue.co.in"),
        ("Aditi", "aditi@sigmavalue.co.in")
    ]

    print(f"\n{CYAN}Quick contacts:{RESET}")
    for i, (name, email) in enumerate(contacts, 1):
        print(f"  {CYAN}[{i}]{RESET} {name} ({email})")
    print(f"  {CYAN}[0]{RESET} Enter custom email address")

    recipient_input = input(
        f"\n{YELLOW}Select recipient number (e.g. 1) or enter email address(es): {RESET}"
    ).strip()

    if not recipient_input:
        print(f"{BLUE}ℹ No recipient specified. Sharing skipped.{RESET}")
        return

    recipient_emails = []
    parts = [p.strip() for p in recipient_input.split(",") if p.strip()]
    for part in parts:
        if part.isdigit() and 1 <= int(part) <= len(contacts):
            recipient_emails.append(contacts[int(part) - 1][1])
        elif "@" in part:
            recipient_emails.append(part)

    if not recipient_emails:
        print(f"{RED}❌ No valid email address provided. Sharing skipped.{RESET}")
        return

    deadline_input = input(
        f"\n{YELLOW}Enter expected deadline (e.g. 'Today 6 PM' / 'Tomorrow 12 PM', or press Enter to skip): {RESET}"
    ).strip()

    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024) if os.path.exists(file_path) else 0

    print(f"\n{CYAN}📧 Preparing email to:{RESET} {', '.join(recipient_emails)}")
    if deadline_input:
        print(f"  {CYAN}⏰ Deadline:{RESET} {deadline_input}")
    print(f"  {CYAN}📎 Attachment size:{RESET} {file_size_mb:.2f} MB")
    print(f"  {YELLOW}⏳ Uploading file over SMTP (may take 1-2 minutes for large files)...{RESET}")

    deadline_str = f"\n⏰ Expected Deadline: {deadline_input}\n" if deadline_input else ""
    deadline_subj = f" [Deadline: {deadline_input}]" if deadline_input else ""

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        sender_email = "nilesh@sigmavalue.co.in"
        sender_password = "nvlf igcl tyxm nnwo"
        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        msg = MIMEMultipart()
        msg["From"] = f"Nilesh <{sender_email}>"
        msg["To"] = ", ".join(recipient_emails)
        loc_str = f" for {location_name}" if location_name else ""
        msg["Subject"] = f"[Manual Correction Required]{deadline_subj} {loc_str.strip()} - {file_name}"

        body = f"""Hello,

The manual correction file{loc_str} is ready for review and manual correction.{deadline_str}
📄 File: {file_name}
🌐 Google Drive Folder: {drive_url}
📂 Local / Drive Path: {file_path}

Please find the file attached with this email.

Best regards,
Nilesh K
"""
        msg.attach(MIMEText(body, "plain"))

        if os.path.exists(file_path):
            with open(file_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {file_name}",
            )
            msg.attach(part)

        # Timeout increased to 300s (5 minutes) for large attachments
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=300)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_emails, msg.as_string())
        server.quit()

        print(f"\n{GREEN}✓ Email sent successfully with attachment to {', '.join(recipient_emails)}!{RESET}")
    except Exception as err:
        print(f"\n{RED}❌ Failed to send attachment ({err}). Sending Drive link notification instead...{RESET}")
        try:
            # Fallback: Send email with Drive link without the large attachment
            fallback_msg = MIMEMultipart()
            fallback_msg["From"] = f"Nilesh <{sender_email}>"
            fallback_msg["To"] = ", ".join(recipient_emails)
            fallback_msg["Subject"] = f"[Manual Correction Required]{deadline_subj} {loc_str.strip()} - {file_name}"
            fallback_body = f"""Hello,

The manual correction file{loc_str} is ready for review.{deadline_str}
📄 File: {file_name}
🌐 Google Drive Folder: {drive_url}
📂 File Path: {file_path}

Please access the file directly from Google Drive using the link above.

Best regards,
Nilesh K
"""
            fallback_msg.attach(MIMEText(fallback_body, "plain"))
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_emails, fallback_msg.as_string())
            server.quit()
            print(f"{GREEN}✓ Drive link notification sent successfully to {', '.join(recipient_emails)}!{RESET}")
        except Exception as fb_err:
            print(f"{RED}❌ Fallback email also failed: {fb_err}{RESET}")
        print(f"  {CYAN}🌐 You can also share the link directly:{RESET} {drive_url}")

def derive_net_carpet_area(df: pd.DataFrame, city: str) -> pd.DataFrame:
    """Fill net_carpet_area_sqmt from whichever area column is available."""
    saleable_divisor = SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get(city.lower())
    if saleable_divisor is None:
        raise ValueError(f"No Saleable->Carpet divisor for city '{city}'.")

    df["net_carpet_area_sqmt"] = np.nan

    mask = df["carpet_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sqmt"] = df.loc[mask, "carpet_area_sqmt"].values

    mask = df["net_carpet_area_sqmt"].isna() & df["builtup_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sqmt"] = (
        df.loc[mask, "builtup_area_sqmt"].values / BUILDUP_TO_CARPET_DIVISOR
    )

    mask = df["net_carpet_area_sqmt"].isna() & df["saleable_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sqmt"] = (
        df.loc[mask, "saleable_area_sqmt"].values / saleable_divisor
    )

    mask = (
        df["net_carpet_area_sqmt"].isna() & df["super_builtup_area_sqmt"].notna()
    )
    df.loc[mask, "net_carpet_area_sqmt"] = (
        df.loc[mask, "super_builtup_area_sqmt"].values / saleable_divisor
    )

    mask = df["net_carpet_area_sqmt"].isna() & df["plot_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sqmt"] = df.loc[mask, "plot_area_sqmt"].values

    mask = df["net_carpet_area_sqmt"].isna() & df["total_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sqmt"] = df.loc[mask, "total_area_sqmt"].values

    df["net_carpet_area_sqmt"] = df["net_carpet_area_sqmt"].round(2)
    return df


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.rename(
        columns={
            "internaldocumentnumber": "internal_document_number",
            "areaname": "village_name_marathi",
            "srocode": "sub_registrar_office_code",
            "sroname": "sub_registrar_office_name",
            "docno": "document_number",
            "consideration_amt": "agreement_price",
            "marketvalue": "guideline_value",
            "Bhumapan": "property_description",
            "registrationdate": "transaction_date",
            "sellerparty": "seller_name",
            "purchaserparty": "buyer_name",
            "property_type": "property_type_raw",
            "dateofexecution": "date_of_agreement_execution",
            "micrno": "micr_number",
            "stampdutypaid": "stamp_duty_paid",
            "registrationfees": "registration_fee",
            "flat_number": "unit_number",
        },
        inplace=True,
    )
    return df


def _map_property_type(value):
    if pd.isna(value) or str(value).strip() == "":
        return "Others"
    value = str(value).strip()
    if value in [
        "Apartment",
        "Flat",
        "Flat/Shop",
        "House",
        "Residential",
        "Residential Building",
        "Residential House",
        "Room",
    ]:
        return "Flat"
    elif value in [
        "Commercial",
        "Commercial Property",
        "Commercial Wing",
        "Office",
        "Office/Shop",
    ]:
        return "Office"
    elif value in [
        "Banquet Hall",
        "Commercial Shop",
        "Restaurant/Bar",
        "Shop",
        "Shop/Office",
    ]:
        return "Shop"
    elif value in ["Bungalow", "Bungalow/Row House", "Row House", "Villa"]:
        return "Villa"
    elif value in [
        "Land",
        "Land and Building",
        "Land/Building/Shed",
        "Land/Shed",
        "Open Land",
        "Plot",
    ]:
        return "Plot"
    return "Others"


def assign_nr_indexes(
    df: pd.DataFrame, target_city_id: int, db_params: dict
) -> pd.DataFrame:
    """Fetches maximum 'nr' index from Postgres DB for target city and fills missing 'index' values."""
    df = df.copy()

    if "index" not in df.columns:
        df["index"] = np.nan

    df["index"] = df["index"].astype(object).replace(r"^\s*$", np.nan, regex=True)

    if "project_name" in df.columns:
        df["project_name"] = (
            df["project_name"].replace(r"^\s*$", np.nan, regex=True)
        )

    # Database lookup for max nr
    conn = psycopg2.connect(**db_params)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT MAX(
            (regexp_match(internal_index_id, '^nr(\\d+)', 'i'))[1]::int
        )
        FROM public.transactions
        WHERE city_id = %s AND internal_index_id ~* '^nr\\d+';
    """,
        (target_city_id,),
    )

    max_nr = cur.fetchone()[0] or 0
    cur.close()
    conn.close()

    next_num = max_nr + 1
    print(f"  {CYAN}Highest NR in DB for City ID {target_city_id}:{RESET} nr{max_nr}")
    print(f"  {CYAN}New NR sequence starts from:{RESET} nr{next_num}")

    existing_indexes = set(
        df["index"].dropna().astype(str).str.strip().str.lower()
    )

    # Filter eligible rows (index is missing & project_name present)
    if "project_name" in df.columns:
        rows_to_assign = df.index[
            df["index"].isna()
            & df["project_name"].notna()
            & df["project_name"].astype("string").str.strip().ne("")
        ]
    else:
        rows_to_assign = df.index[df["index"].isna()]

    print(f"  {CYAN}Rows eligible for new NR:{RESET} {len(rows_to_assign)}")

    for i in rows_to_assign:
        while f"nr{next_num}" in existing_indexes:
            next_num += 1
        new_index = f"nr{next_num}"
        df.at[i, "index"] = new_index
        existing_indexes.add(new_index)
        next_num += 1

    print(f"  {CYAN}New NR assigned:{RESET} {len(rows_to_assign)}")
    if len(rows_to_assign) > 0:
        print(f"  {CYAN}Highest new NR:{RESET} nr{next_num - 1}")
    print(f"  {CYAN}Blank indexes remaining:{RESET} {df['index'].isna().sum()}")

    return df

def populate_location_coords(df, city_id, db_params):
    loc_col = next((c for c in ["location_name", "location"] if c in df.columns), None)
    if not loc_col: return df
    conn = psycopg2.connect(**db_params)
    coords = pd.read_sql_query("SELECT DISTINCT LOWER(TRIM(location_name)) AS loc, location_latitude AS latitude, location_longitude AS longitude FROM public.dim_location WHERE city_id = %s AND location_latitude IS NOT NULL", conn, params=(city_id,))
    conn.close()
    coords = coords.drop_duplicates(subset=["loc"])
    keys = df[loc_col].astype(str).str.strip().str.lower()
    df["location_latitude"] = keys.map(coords.set_index("loc")["latitude"])
    df["location_longitude"] = keys.map(coords.set_index("loc")["longitude"])
    return df

def resolve_city(df: pd.DataFrame, source_file: str, db_params: dict) -> tuple[int, str]:
    """
    Fetches available cities from public.dim_city, auto-detects the city from df / source_file,
    and prompts the user once to confirm or override. Returns (target_city_id, target_city_name).
    """
    cities = {}
    try:
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()
        cur.execute("SELECT city_id, city_name FROM public.dim_city ORDER BY city_id;")
        cities = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        print(f"{YELLOW}⚠️ Error querying public.dim_city: {e}{RESET}")
        cities = {9: "Pune"}

    name_to_id = {str(name).strip().lower(): cid for cid, name in cities.items()}

    detected_id = None
    detected_name = None

    # Check source_file path first
    file_str = str(source_file).lower()
    for name_lower, cid in name_to_id.items():
        clean_name = name_lower.replace("_", " ")
        if re.search(r"\b" + re.escape(clean_name) + r"\b", file_str) or re.search(r"\b" + re.escape(name_lower) + r"\b", file_str):
            detected_id = cid
            detected_name = cities[cid]
            break

    # If not found from file path, check columns in df
    if detected_id is None and df is not None:
        candidate_cols = [
            "city_name", "city", "city_en", "city_original",
            "district_name", "district_en", "district_original",
            "taluka_en", "taluka_original", "areaname", "village_name_marathi"
        ]
        found_cols = [c for c in candidate_cols if c in df.columns]
        for col in found_cols:
            col_series = df[col].iloc[:, 0] if isinstance(df[col], pd.DataFrame) else df[col]
            unique_vals = [str(v).strip().lower() for v in col_series.dropna().unique() if str(v).strip()]
            for val in unique_vals:
                for name_lower, cid in name_to_id.items():
                    clean_name = name_lower.replace("_", " ")
                    if val == name_lower or val == clean_name or name_lower in val:
                        detected_id = cid
                        detected_name = cities[cid]
                        break
                if detected_id is not None:
                    break
            if detected_id is not None:
                break

    # Default fallback to Pune (9) if still undetected
    if detected_id is None:
        detected_id = 9 if 9 in cities else next(iter(cities.keys()), 9)
        detected_name = cities.get(detected_id, "Pune")

    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   🏙️  CITY RESOLUTION (public.dim_city){RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"  {CYAN}Detected City :{RESET} {BOLD}{GREEN}{detected_name}{RESET} (City ID: {BOLD}{CYAN}{detected_id}{RESET})")
    print(f"{HEADER}{'-' * 60}{RESET}")

    while True:
        prompt = (
            f"{YELLOW}Press Enter to confirm [{detected_name} (ID: {detected_id})], "
            f"or enter City ID / Name: {RESET}"
        )
        user_val = input(prompt).strip()

        if not user_val:
            target_city_id = detected_id
            target_city_name = detected_name
            break

        if user_val.isdigit() and int(user_val) in cities:
            target_city_id = int(user_val)
            target_city_name = cities[target_city_id]
            break

        val_lower = user_val.lower().replace(" ", "_")
        if val_lower in name_to_id:
            target_city_id = name_to_id[val_lower]
            target_city_name = cities[target_city_id]
            break

        matched_cid = next((cid for n_l, cid in name_to_id.items() if val_lower in n_l or n_l in val_lower), None)
        if matched_cid:
            target_city_id = matched_cid
            target_city_name = cities[target_city_id]
            break

        print(f"{YELLOW}⚠️ '{user_val}' not recognized in public.dim_city.{RESET}")
        print(f"{BLUE}ℹ Available cities:{RESET} {', '.join([f'{CYAN}{cid}:{RESET} {name}' for cid, name in cities.items()])}")

    print(f"{GREEN}✓ City confirmed: {BOLD}{target_city_name}{RESET}{GREEN} (City ID: {target_city_id}){RESET}")
    set_active_city(target_city_name)
    return target_city_id, target_city_name

def populate_village_mapping(df: pd.DataFrame, city_id: int, db_params: dict) -> pd.DataFrame:
    """Match areaname / village_name_marathi against transactions table and fill location_name & registered_document_village_name."""
    col = (
        "village_name_marathi"
        if "village_name_marathi" in df.columns
        else ("areaname" if "areaname" in df.columns else None)
    )
    if not col:
        return df

    for c in ["location_name", "registered_document_village_name"]:
        if c not in df.columns:
            df[c] = pd.NA

    conn = psycopg2.connect(**db_params)
    lookup = pd.read_sql_query(
        """
        SELECT DISTINCT TRIM(village_name_marathi) AS village_name_marathi,
               location_name,
               registered_document_village_name
        FROM public.transactions
        WHERE city_id = %s AND village_name_marathi IS NOT NULL
        """,
        conn,
        params=(city_id,),
    )
    conn.close()

    lookup = lookup.drop_duplicates(subset=["village_name_marathi"], keep="first")
    lookup = lookup.set_index("village_name_marathi")

    col_series = df[col].iloc[:, 0] if isinstance(df[col], pd.DataFrame) else df[col]
    keys = col_series.astype(str).str.strip()
    df["location_name"] = keys.map(lookup["location_name"])
    df["registered_document_village_name"] = keys.map(lookup["registered_document_village_name"])

    matched_count = df["registered_document_village_name"].notna().sum()
    print(f"  {CYAN}Village mapping matched:{RESET} {matched_count} / {len(df)} rows")
    return df

def keep_db_columns(df, db_sequence):
    existing_cols = [col for col in db_sequence if col in df.columns]
    missing_cols = [col for col in db_sequence if col not in df.columns]

    if missing_cols:
        print(f"  {YELLOW}⚠️ Missing columns:{RESET}")
        print(f"  {YELLOW}{missing_cols}{RESET}")

    return df[existing_cols].copy()


def extract_pincode(text):
    """Extract 6-digit Indian postal pincode from text (e.g. buyer_name / purchaserparty)."""
    if isinstance(text, str):
        match = re.search(r"\b[1-9]\d{5}\b", text)
        return match.group(0) if match else None
    return None


def add_buyer_location(df: pd.DataFrame, postal_csv_path: str | Path = None) -> pd.DataFrame:
    """
    Extracts buyer_pincode from buyer_name and enriches with
    buyer_locality, buyer_district, buyer_state using postal_pincode.csv.
    """
    print(f"  {CYAN}⏳ Extracting buyer pincode & matching postal location...{RESET}")

    df = df.copy()

    # Extract buyer_pincode from buyer_name if available
    if "buyer_name" in df.columns:
        extracted = df["buyer_name"].apply(extract_pincode)
        if "buyer_pincode" in df.columns:
            df["buyer_pincode"] = df["buyer_pincode"].fillna(extracted)
        else:
            df["buyer_pincode"] = extracted
    elif "buyer_pincode" not in df.columns:
        df["buyer_pincode"] = pd.NA

    # Resolve postal CSV path
    if postal_csv_path is None:
        postal_csv_path = Path(__file__).resolve().parent / "postal_pincode.csv"
    else:
        postal_csv_path = Path(postal_csv_path)

    if not postal_csv_path.exists():
        fallback_path = Path(r"D:\Database\DB1_DB2_Uploading_Pipeline\Pune_IGR_Update_Pipeline\required_files\postal_pincode.csv")
        if fallback_path.exists():
            postal_csv_path = fallback_path

    if not postal_csv_path.exists():
        print(f"  {YELLOW}⚠️ Postal pincode CSV not found at: {postal_csv_path}. Skipping postal lookup.{RESET}")
        for col in ["buyer_locality", "buyer_district", "buyer_state"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df

    # Drop existing location columns to prevent _x, _y collisions
    df = df.drop(
        columns=["buyer_locality", "buyer_district", "buyer_state"],
        errors="ignore",
    )

    try:
        postal = pd.read_csv(
            postal_csv_path,
            usecols=["OfficeName_P", "Pincode", "District_P", "StateName_P"],
        ).rename(columns={
            "OfficeName_P": "buyer_locality",
            "District_P": "buyer_district",
            "StateName_P": "buyer_state",
            "Pincode": "buyer_pincode",
        })

        # Ensure numeric conversion safe from invalid strings / types
        postal["buyer_pincode"] = pd.to_numeric(postal["buyer_pincode"], errors="coerce").astype("Int64")
        postal = postal.dropna(subset=["buyer_pincode"]).drop_duplicates(subset=["buyer_pincode"], keep="first")

        df["buyer_pincode"] = pd.to_numeric(df["buyer_pincode"], errors="coerce").astype("Int64")

        orig_len = len(df)
        merged = pd.merge(df, postal, on="buyer_pincode", how="left")
        if len(merged) != orig_len:
            print(f"  {YELLOW}⚠️ Row count mismatch after merge ({len(merged)} vs {orig_len}). Retaining unique records.{RESET}")
            merged = merged.drop_duplicates(keep="first")
        return merged
    except Exception as e:
        print(f"  {RED}❌ Error matching postal data: {e}{RESET}")
        for col in ["buyer_locality", "buyer_district", "buyer_state"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df

# ============================================================
# TARGET CITY SELECTION & PIPELINE MODE
# ============================================================
print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"{HEADER}{BOLD}   🏙️  SELECT TARGET CITY{RESET}")
print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
for idx, (ckey, cval) in enumerate(CITY_CONFIG.items(), start=1):
    div = SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get(ckey, cval.get("saleable_to_carpet_divisor", 1.35))
    print(f"  {CYAN}[{idx}]{RESET} {cval['display_name']:<10} (City ID: {cval['city_id']}, Divisor: {div})")
print(f"{HEADER}{'-' * 60}{RESET}")

selected_city_input = input(f"{YELLOW}Select city (1: Pune, 2: Mumbai, 3: Thane) [default: 1]: {RESET}").strip()
city_idx_map = {str(i): k for i, k in enumerate(CITY_CONFIG.keys(), start=1)}

if selected_city_input in city_idx_map:
    active_city_key = city_idx_map[selected_city_input]
elif selected_city_input.lower() in CITY_CONFIG:
    active_city_key = selected_city_input.lower()
else:
    active_city_key = "pune"

CURRENT_CITY_CONFIG = set_active_city(active_city_key)
target_city_id = CURRENT_CITY_CONFIG["city_id"]
target_city_name = CURRENT_CITY_CONFIG["display_name"]
active_divisor = SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get(active_city_key, 1.35)
print(f"{GREEN}✓ Active City set to: {BOLD}{target_city_name}{RESET}{GREEN} (ID: {target_city_id}, Divisor: {active_divisor}){RESET}")

print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"{HEADER}{BOLD}   🏗️  DATA PROCESSING PIPELINE - {target_city_name.upper()}{RESET}")
print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"  {CYAN}[1]{RESET} Run from START (Step 1 to Step 20)")
print(f"  {CYAN}[2]{RESET} Run from STEP 7 (Load manually corrected file directly, Steps 7 to 20)")
print(f"  {CYAN}[3]{RESET} Run STEP 19 ONLY (Parquet Conversion directly)")
print(f"{HEADER}{'=' * 60}{RESET}")

pipeline_mode = input(f"\n{YELLOW}Select option (1, 2, or 3) [default: 1]: {RESET}").strip()

if pipeline_mode == "3":
    # STEP 19 ONLY - Direct Parquet Conversion
    print(f"\n{BLUE}ℹ ⏩ Skipping Steps 1 to 18. Starting directly from STEP 19 (Parquet Conversion)...{RESET}")
    output_path = get_final_processed_file()
    sample_df = None
    try:
        sample_df = pd.read_excel(output_path, nrows=10, engine="openpyxl")
    except Exception:
        pass
    target_city_id, target_city_name = resolve_city(sample_df, output_path, DB_PARAMS)

elif pipeline_mode == "2":
    # STEP 7 - Manually Corrected File Load From User
    print(f"\n{BLUE}ℹ ⏩ Skipping Steps 1 to 6. Starting directly from STEP 7...{RESET}")
    file_path, df = get_manual_corrected_file()
    target_city_id, target_city_name = resolve_city(df, file_path, DB_PARAMS)

else:
    # ------------------------------------------------------------
    # STEP 1 - INPUT FILE (MANUAL PROMPT HIDDEN)
    # ------------------------------------------------------------
    # print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    # print(f"{HEADER}{BOLD}   ⏳ [STEP 1/20] Getting Input File...{RESET}")
    # print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    # input_file = input(f"{YELLOW}Please provide Input File path: {RESET}").strip().strip('"')
    # print(f"{GREEN}✓ [STEP 1/20] Input file selected: {input_file}{RESET}")

    # ============================================================
    # STEP 1 - GET FILE FROM GOOGLE DRIVE (LOCATION WISE)
    # ============================================================
    def get_file_from_drive(
        drive_url: str = DEFAULT_INPUT_DRIVE_FOLDER_URL,
    ) -> str:
        """
        Scans Google Drive folder (via local Google Drive Desktop sync) for location-wise subfolders,
        allows picking location-wise file, and returns the selected file path.
        """
        print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
        print(f"{HEADER}{BOLD}   📁 [STEP 1/20] Getting Input File from Google Drive...{RESET}")
        print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

        # Extract folder ID from URL or path
        clean_target = str(drive_url).strip() if drive_url else ""
        match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
        folder_id = match.group(1) if match else clean_target

        if not folder_id:
            print(f"  {YELLOW}⚠️ No Google Drive input folder configured for {target_city_name} yet.{RESET}")
            print(f"  {CYAN}ℹ (You can configure Drive URLs in city_config.py once created).{RESET}")
            while True:
                manual_path = input(f"\n{YELLOW}Please provide Input File path manually: {RESET}").strip().strip('"')
                if manual_path and os.path.isfile(manual_path):
                    return manual_path
                print(f"  {RED}❌ File not found: '{manual_path}'. Please enter a valid existing file path.{RESET}")

        # Check Google Drive Desktop shortcut targets
        base_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)

        if not os.path.exists(base_path) and os.path.isdir(clean_target):
            base_path = clean_target

        if not os.path.exists(base_path):
            print(f"  {YELLOW}⚠️ Google Drive folder not detected on G: ({base_path}){RESET}")
            print(f"  {CYAN}🌐 Target Drive URL: {drive_url}{RESET}")
            while True:
                manual_path = input(f"\n{YELLOW}Please provide Input File path manually: {RESET}").strip().strip('"')
                if manual_path and os.path.isfile(manual_path):
                    return manual_path
                print(f"  {RED}❌ File not found: '{manual_path}'. Please enter a valid existing file path.{RESET}")

        # Discover location-wise folders and files
        valid_extensions = (".xlsx", ".xls", ".csv")
        location_dict = {}

        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            excel_files = [
                f for f in files
                if f.lower().endswith(valid_extensions) and not f.startswith("~$")
            ]
            if excel_files:
                loc_name = os.path.basename(root)
                location_dict[loc_name] = {
                    "folder_path": root,
                    "files": [os.path.join(root, f) for f in excel_files],
                }

        if not location_dict:
            print(f"  {YELLOW}⚠️ No location folders or Excel files found in {base_path}{RESET}")
            manual_path = input(f"\n{YELLOW}Please provide Input File path manually: {RESET}").strip().strip('"')
            return manual_path

        print(f"  {CYAN}🌐 Drive Target :{RESET} {drive_url}")
        print(f"  {CYAN}📂 Found {len(location_dict)} location folder(s):{RESET}")
        print(f"{HEADER}{'-' * 60}{RESET}")

        locations = sorted(list(location_dict.keys()))
        for idx, loc in enumerate(locations, 1):
            file_count = len(location_dict[loc]["files"])
            sample_file = os.path.basename(location_dict[loc]["files"][0])
            print(f"  {CYAN}[{idx}]{RESET} {BOLD}{loc}{RESET} ({file_count} file{'s' if file_count > 1 else ''}: {sample_file})")
        print(f"  {CYAN}[0]{RESET} Enter file path manually")
        print(f"{HEADER}{'-' * 60}{RESET}")

        selected_loc = None
        while True:
            prompt_text = f"\n{YELLOW}Select location (1 to {len(locations)}) or name [default: 1 ({locations[0]})]: {RESET}"
            user_choice = input(prompt_text).strip()

            if not user_choice:
                selected_loc = locations[0]
                break

            if user_choice == "0":
                manual_path = input(f"\n{YELLOW}Please provide Input File path manually: {RESET}").strip().strip('"')
                return manual_path

            if user_choice.isdigit() and 1 <= int(user_choice) <= len(locations):
                selected_loc = locations[int(user_choice) - 1]
                break

            matched = next((l for l in locations if l.lower() == user_choice.lower()), None)
            if matched:
                selected_loc = matched
                break

            print(f"{RED}❌ Invalid selection '{user_choice}'. Please enter 1 to {len(locations)} or location name.{RESET}")

        loc_info = location_dict[selected_loc]
        loc_files = loc_info["files"]

        # Select file from chosen location
        if len(loc_files) == 1:
            selected_file = loc_files[0]
            print(f"\n  {GREEN}✓ Selected location:{RESET} {BOLD}{selected_loc}{RESET}")
            print(f"  {GREEN}✓ Selected file    :{RESET} {BOLD}{os.path.basename(selected_file)}{RESET}")
        else:
            print(f"\n{CYAN}Files in '{selected_loc}':{RESET}")
            for f_idx, f_path in enumerate(loc_files, 1):
                print(f"  {CYAN}[{f_idx}]{RESET} {os.path.basename(f_path)}")
            while True:
                file_choice = input(f"\n{YELLOW}Select file (1 to {len(loc_files)}) [default: 1]: {RESET}").strip()
                if not file_choice or file_choice == "1":
                    selected_file = loc_files[0]
                    break
                if file_choice.isdigit() and 1 <= int(file_choice) <= len(loc_files):
                    selected_file = loc_files[int(file_choice) - 1]
                    break
                print(f"{RED}❌ Invalid file choice. Please choose 1 to {len(loc_files)}.{RESET}")

        print(f"\n{GREEN}✓ [STEP 1/20] Input file selected from Drive:{RESET}")
        print(f"  {CYAN}📄 File:{RESET} {BOLD}{os.path.basename(selected_file)}{RESET}")
        print(f"  {CYAN}📂 Path:{RESET} {selected_file}")
        global selected_location
        selected_location = selected_loc
        return selected_file

    input_file = get_file_from_drive(DEFAULT_INPUT_DRIVE_FOLDER_URL)

    

    # STEP 2 - DictToColumn
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 2/20] Running DictToColumn...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from DictToColumn import process_dict_to_column

    df = process_dict_to_column(input_file)
    print(f"{GREEN}✓ [STEP 2/20] DictToColumn completed - {len(df)} rows{RESET}")
    target_city_id, target_city_name = resolve_city(df, input_file, DB_PARAMS)

    # STEP 3 - Create final_project_name
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 3/20] Creating final_project_name...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    project_name_missing = (
        df["project_name_en"].replace(r"^\s*$", pd.NA, regex=True).isna()
    )
    df["final_project_name"] = (
        df["project_name_en"]
        .replace(r"^\s*$", pd.NA, regex=True)
        .fillna(df["building_name_en"])
    )
    df["final_project_name_status"] = project_name_missing.map(
        {True: "Building Name Considered", False: "Project Name Considered"}
    )
    print(f"{GREEN}✓ [STEP 3/20] Final project name created.{RESET}")

    # STEP 4 - Static Dictionary Mapping
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 4/20] Mapping transaction types using static dictionary...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from static import result_dict, word_number_dict

    df["transaction_type"] = df["docname"].map(result_dict.get)
    print(f"{GREEN}✓ [STEP 4/20] Transaction types mapped.{RESET}")

    # STEP 5 - Transaction Categorisation
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 5/20] Categorising transactions (Sale / Lease / Other)...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from transaction_categorizer import categorise

    df = categorise(df)
    print(f"{GREEN}✓ [STEP 5/20] Transaction categorisation completed.{RESET}")

    # STEP 5.5 - Populate village_name_marathi from transactions DB if missing
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 5.5/20] Mapping village_name_marathi -> location_name / registered_document_village_name...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df = populate_village_mapping(df, target_city_id, DB_PARAMS)
    print(f"{GREEN}✓ [STEP 5.5/20] Village mapping completed.{RESET}")


    # STEP 6 - Project Standardization & Area Conversion
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 6/20] Running Project Standardization & Area Conversion...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from project_name_Std_and_area_conversion import process_dataframe

    # Determine location name
    location_name = (
        selected_location
        if ("selected_location" in globals() and selected_location)
        else os.path.basename(os.path.dirname(input_file))
    )

    # Resolve manual correction Google Drive folder
    manual_dir = resolve_manual_correction_directory(
        DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL,
        location_name=location_name,
    )

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    out_file_name = f"{base_name}_for_manual.xlsx" if not base_name.endswith("_for_manual") else f"{base_name}.xlsx"

    if manual_dir and os.path.exists(manual_dir):
        v1_output_path = os.path.join(manual_dir, out_file_name)
        print(f"  {CYAN}🌐 Google Drive Target :{RESET} {DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL}")
        print(f"  {CYAN}📂 Location Save Path  :{RESET} {v1_output_path}")
    else:
        input_dir = os.path.dirname(input_file)
        v1_output_path = os.path.join(input_dir, out_file_name)
        print(f"  {YELLOW}⚠️ Manual correction drive folder not detected. Saving locally: {v1_output_path}{RESET}")

    df = process_dataframe(df, output_path=v1_output_path)
    print(
        f"{GREEN}✓ [STEP 6/20] Standardization completed -> Saved: {v1_output_path}{RESET}"
    )

    # Optional: Share correction file with colleagues
    prompt_share_correction_file(v1_output_path, location_name=location_name)

    # STEP 7 - Manually Corrected File Load
    file_path, df = get_manual_corrected_file(default_file=v1_output_path)


if pipeline_mode in ["1", "2"]:
    # STEP 8 - Calculate Net_carpet_area
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 8/20] Calculating Net Carpet Area...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df = derive_net_carpet_area(df, city=target_city_name.lower())
    print(f"{GREEN}✓ [STEP 8/20] Net Carpet Area calculation completed.{RESET}")

    # STEP 9 - Rename columns
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 9/20] Renaming columns to standard format...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df = rename_columns(df)
    print(f"{GREEN}✓ [STEP 9/20] Columns renamed successfully.{RESET}")

    # STEP 10 - Categorise Property Type
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 10/20] Categorising property types...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df["property_type"] = df["property_type_raw"].apply(_map_property_type)
    print(f"{GREEN}✓ [STEP 10/20] Property types categorised.{RESET}")

    # STEP 11 - Add Buyer location and Pincode
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 11/20] Adding Buyer Location and Pincode...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df = add_buyer_location(df)
    matched_pincodes = df["buyer_pincode"].notna().sum() if "buyer_pincode" in df.columns else 0
    matched_locations = df["buyer_locality"].notna().sum() if "buyer_locality" in df.columns else 0
    print(f"{GREEN}✓ [STEP 11/20] Buyer location and pincode added ({matched_pincodes} pincodes, {matched_locations} locations matched).{RESET}")
    
    # STEP 12 - Matching with RERA
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 12/20] Running RERA matching...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from rera_matching import process_rera_matching

    rera_file = CURRENT_CITY_CONFIG.get("rera_grand_file") if "CURRENT_CITY_CONFIG" in globals() else None
    rera_path = None
    if rera_file:
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), rera_file)
        if os.path.exists(candidate):
            rera_path = candidate

    if rera_path:
        df = process_rera_matching(df, city=target_city_name.title(), rera_grand_path=rera_path)
        print(f"{GREEN}✓ [STEP 12/20] RERA matching completed with {os.path.basename(rera_path)} - {len(df)} rows{RESET}")
    elif target_city_name.lower() == "pune":
        df = process_rera_matching(df, city="Pune")
        print(f"{GREEN}✓ [STEP 12/20] RERA matching completed - {len(df)} rows{RESET}")
    else:
        print(f"  {YELLOW}⚠️ No RERA Grand dataset configured or found for {target_city_name} (can be set in city_config.py).{RESET}")
        for c in ["index", "modified_project_name", "rera_location_v1", "rera_location",
                  "project_lat", "project_lng", "BHK", "Final BHK", "Final Property Type"]:
            if c not in df.columns:
                df[c] = pd.NA
        if "BHK" in df.columns and "property_type" in df.columns:
            df["BHK"] = df["BHK"].fillna(df["property_type"])
        print(f"{GREEN}✓ [STEP 12/20] RERA matching skipped safely for {target_city_name}.{RESET}")


    # ============================================================
    # DB SCHEMA ALIGNMENT & DEFAULTS
    # ============================================================
    for col in ["transaction_date", "date_of_agreement_execution"]:
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    df["quarter"] = (
        "Q"
        + df["transaction_date"].dt.quarter.astype(str)
        + "-"
        + df["transaction_date"].dt.year.astype(str)
    )

    for col in ["transaction_date", "date_of_agreement_execution"]:
        df[col] = df[col].dt.strftime("%d/%m/%Y")

    rename_mapping = {
        "city": "city_name",
        "net_carpet_area_sqmt": "net_carpet_area_sq_m",
        "balcony_area_sqmt": "balcony_sq_m",
        "terrace_area_sqmt": "terrace_sq_m",
        "project_lat": "project_latitude",
        "project_lng": "project_longitude",
        "BHK": "unit_configuration",
        "manual_processed": "is_manual_processed",
        "locality_en": "sub_locality",
        "wing_no": "tower_name",
    }

    df = df.rename(
        columns={k: v for k, v in rename_mapping.items() if k in df.columns}
    )

    defaults = {
        "location_latitude": np.nan,
        "location_longitude": np.nan,
        "is_duplicate": "No",
        "sale_type": pd.NA,
        "state_name": "Maharashtra",
        "country_name": "India",
        "micro_market": pd.NA,
        "data_source": "Igr",
        "parking_count": pd.NA,
        "facing_direction": pd.NA,
        "view_type": pd.NA,
        "furnishing_status": pd.NA,
        "condition_status": pd.NA,
        "source_accessibility": "Easy",
        "source_accessibility_way": "Api",
        "sourcing_cost": np.nan,
        "sourcing_time": np.nan,
        "data_type": "Registered Document",
        "normalized_unit_configuration": df.get("unit_configuration", pd.NA),
        "city_name": target_city_name.title(),
        "project_stage": pd.NA,
        "is_llm_processed": "Yes",
        "is_manual_processed": "No",
        "buyer_pincode": pd.NA,
        "buyer_locality": pd.NA,
        "buyer_district": pd.NA,
        "buyer_state": pd.NA,
    }

    for col, value in defaults.items():
        if col not in df.columns:
            df[col] = value

    # ============================================================
    # STEP 13 - Assign NR Indexes via PostgreSQL
    # ============================================================
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 13/20] Assigning NR Indexes for {target_city_name} (ID: {target_city_id})...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

    df = assign_nr_indexes(
        df, target_city_id=target_city_id, db_params=DB_PARAMS
    )
    print(f"{GREEN}✓ [STEP 13/20] NR assignment complete.{RESET}")

    # ============================================================
    # STEP 14 - Fetch Location Latitude & Longitude from DB
    # ============================================================
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 14/20] Populating Location Coordinates from DB...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    df = populate_location_coords(df, target_city_id, DB_PARAMS)
    print(f"{GREEN}✓ [STEP 14/20] Location LatLong populated.{RESET}")

    # # ============================================================
    # # STEP 15 - Fill remaining project coordinates using Google Places API
    # # ============================================================
    # print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    # print(f"{HEADER}{BOLD}   ⏳ [STEP 15/20] Populating Project Coordinates (Google Places API)...{RESET}")
    # print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    # from project_coordinates import populate_project_coordinates
    # df = populate_project_coordinates(df)
    # print(f"{GREEN}✓ [STEP 15/20] Project Coordinates completed.{RESET}")

    # ============================================================
    # STEP 16 - Filter & Order Selective DB Columns
    # ============================================================
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 16/20] Filtering and ordering columns according to DB schema...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from db_columns import DB_SEQUENCE
    df = keep_db_columns(df, DB_SEQUENCE)
    print(f"{GREEN}✓ [STEP 16/20] DB columns filtering and ordering completed ({len(df.columns)} columns retained).{RESET}")

    # ============================================================
    # STEP 17 - Title Case For all text columns
    # ============================================================
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 17/20] Applying Title Case to text columns...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(lambda x: x.title() if isinstance(x, str) else x)
    print(f"{GREEN}✓ [STEP 17/20] Title Case applied successfully.{RESET}")

    # ============================================================
    # STEP 18 - FINAL OUTPUT SAVE (GOOGLE DRIVE & LOCAL)
    # ============================================================
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   📁 [STEP 18/20] FINAL OUTPUT SAVE{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

    # Derive default output filename based on input or manual corrected file
    source_file = (
        file_path
        if ("file_path" in locals() and file_path)
        else (input_file if ("input_file" in locals() and input_file) else "output.xlsx")
    )
    base_name = os.path.splitext(os.path.basename(source_file))[0]
    for suffix in ["_for_manual", "_processed_v1", "_processed", "_llm_output", "_Merged_File", "_merged_file", "_merged"]:
        base_name = base_name.replace(suffix, "")
    default_filename = f"{base_name}_final_processed.xlsx"

    # Resolve Google Drive target directory
    drive_folder_path = resolve_drive_directory(DEFAULT_DRIVE_FOLDER_URL)

    # Determine location name for folder creation
    location_name = (
        selected_location
        if ("selected_location" in globals() and selected_location)
        else os.path.basename(os.path.dirname(source_file))
    )
    if not location_name or location_name.lower() in ["3. manually corrected", "2. llm processed data", "required_files", "processing"]:
        location_name = base_name

    if drive_folder_path and os.path.exists(drive_folder_path):
        location_drive_path = os.path.join(drive_folder_path, location_name)
        os.makedirs(location_drive_path, exist_ok=True)
        default_output_path = os.path.join(location_drive_path, default_filename)
        print(f"  {CYAN}🌐 Google Drive Target :{RESET} {DEFAULT_DRIVE_FOLDER_URL}")
        print(f"  {CYAN}📂 Location Folder     :{RESET} {location_drive_path}")
    else:
        local_dir = (
            os.path.dirname(os.path.abspath(source_file))
            if os.path.exists(source_file)
            else os.getcwd()
        )
        location_drive_path = os.path.join(local_dir, location_name)
        os.makedirs(location_drive_path, exist_ok=True)
        default_output_path = os.path.join(location_drive_path, default_filename)
        print(f"  {YELLOW}⚠️ Google Drive folder not detected on G:. Defaulting to local path.{RESET}")

    print(f"  {CYAN}📄 Suggested File      :{RESET} {BOLD}{default_filename}{RESET}")
    print(f"  {CYAN}💾 Default Save Path   :{RESET} {BOLD}{default_output_path}{RESET}")
    print(f"{HEADER}{'=' * 60}{RESET}")

    while True:
        print(f"\n{HEADER}{'-' * 50}{RESET}")
        user_input = input(
            f"{YELLOW}Press Enter to save to Drive [{default_filename}], or provide path/filename: {RESET}"
        ).strip().strip('"')

        if not user_input:
            output_path = default_output_path
        elif user_input.startswith("http://") or user_input.startswith("https://"):
            # User provided a Drive URL
            custom_drive_dir = resolve_drive_directory(user_input)
            if custom_drive_dir and os.path.exists(custom_drive_dir):
                custom_loc_dir = os.path.join(custom_drive_dir, location_name)
                os.makedirs(custom_loc_dir, exist_ok=True)
                output_path = os.path.join(custom_loc_dir, default_filename)
            else:
                print(f"{RED}❌ Unable to resolve Drive URL: {user_input}. Please try again.{RESET}")
                continue
        elif os.path.dirname(user_input) == "":
            # User provided only a filename (e.g. "Sogaon_2026.xlsx")
            chosen_name = (
                user_input
                if user_input.lower().endswith((".xlsx", ".xls"))
                else f"{user_input}.xlsx"
            )
            output_path = os.path.join(location_drive_path, chosen_name)
        else:
            # User provided a full or relative path
            output_path = user_input

        # Validate file extension
        if not output_path.lower().endswith((".xlsx", ".xls")):
            print(
                f"{YELLOW}⚠️ Warning: Output file should end with '.xlsx' (you provided: '{output_path}'){RESET}"
            )
            suggested_path = os.path.splitext(output_path)[0] + ".xlsx"
            fix_choice = (
                input(
                    f"{YELLOW}Would you like to use '{suggested_path}' instead? (y/n) [default: y]: {RESET}"
                )
                .strip()
                .lower()
            )
            if fix_choice in ["y", "yes", ""]:
                output_path = suggested_path
            else:
                print(f"{RED}Please re-enter a valid Excel (.xlsx) file path.{RESET}")
                continue

        # Ask user confirmation
        print(f"\n  {CYAN}📁 Selected output path:{RESET} {output_path}")
        confirm = input(f"{YELLOW}Save output to this path? (y/n) [default: y]: {RESET}").strip().lower()
        if confirm not in ["y", "yes", ""]:
            print(f"{YELLOW}Okay, please re-enter the path.{RESET}")
            continue

        # Ensure output directory exists and attempt saving
        try:
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            print(f"\n{CYAN}💾 Saving final dataset ({len(df)} rows) to: {output_path} ...{RESET}")
            df.to_excel(output_path, index=False)
            print(f"{GREEN}✓ Saved successfully to: {output_path}{RESET}")

            # If saved to Google Drive, print cloud sync information
            is_drive = output_path.lower().startswith("g:\\") or (
                drive_folder_path
                and drive_folder_path.lower() in output_path.lower()
            )
            if is_drive:
                print(f"{BLUE}☁️ Google Drive Sync: This file is located in your Google Drive Desktop folder and is syncing to:{RESET}")
                print(f"   {CYAN}{DEFAULT_DRIVE_FOLDER_URL}{RESET}")

                # Also save a local backup copy in processing directory (Commented out - only save to Google Drive)
                # local_backup_dir = (
                #     os.path.dirname(os.path.abspath(source_file))
                #     if os.path.exists(source_file)
                #     else os.getcwd()
                # )
                # local_backup_path = os.path.join(
                #     local_backup_dir, os.path.basename(output_path)
                # )
                # if os.path.abspath(local_backup_path).lower() != os.path.abspath(output_path).lower():
                #     try:
                #         df.to_excel(local_backup_path, index=False)
                #         print(f"{GREEN}✓ Local backup copy saved to: {local_backup_path}{RESET}")
                #     except Exception as backup_err:
                #         print(f"{BLUE}ℹ (Local backup skipped: {backup_err}){RESET}")

            print(f"\n{GREEN}{BOLD}🎉 Pipeline Execution Completed Successfully!{RESET}")
            break
        except PermissionError:
            print(
                f"\n{RED}❌ Permission Error: Unable to save to '{output_path}'. The file may be open in Excel. Please close it or specify a different filename.{RESET}"
            )
        except Exception as e:
            print(f"\n{RED}❌ Error saving file ({e}). Please try entering a different path.{RESET}")

# ============================================================
# VERIFY FINAL PROCESSED FILE BEFORE STEP 19
# ============================================================
print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"{HEADER}{BOLD}   🔍 VERIFICATION: FINAL PROCESSED FILE REVIEW{RESET}")
print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"  {CYAN}📄 Final Processed File:{RESET} {BOLD}{output_path}{RESET}")

proceed_parquet = False
while True:
    is_correct = input(
        f"\n{YELLOW}Is the final processed file correct? (y/n / enter corrected path / 'corrected') [default: y]: {RESET}"
    ).strip().strip('"')

    if not is_correct or is_correct.lower() in ["y", "yes", "correct", "corrected"]:
        print(f"{GREEN}✓ Final processed file confirmed! Proceeding to Parquet conversion...{RESET}")
        proceed_parquet = True
        break
    elif is_correct.lower() in ["skip", "cancel"]:
        print(f"{BLUE}ℹ Parquet conversion skipped.{RESET}")
        proceed_parquet = False
        break
    elif is_correct.lower() in ["n", "no"]:
        corrected_input = input(f"{YELLOW}Please provide the path to the corrected file (or type 'skip' to skip conversion): {RESET}").strip().strip('"')
        if corrected_input.lower() in ["skip", "cancel", "n", "no", ""]:
            print(f"{BLUE}ℹ Parquet conversion skipped.{RESET}")
            proceed_parquet = False
            break
        elif os.path.exists(corrected_input):
            output_path = corrected_input
            print(f"{GREEN}✓ Corrected file accepted: {output_path}. Proceeding to Parquet conversion...{RESET}")
            proceed_parquet = True
            break
        else:
            print(f"{RED}❌ File not found: '{corrected_input}'. Please try again.{RESET}")
    elif os.path.exists(is_correct):
        output_path = is_correct
        print(f"{GREEN}✓ Corrected file accepted: {output_path}. Proceeding to Parquet conversion...{RESET}")
        proceed_parquet = True
        break
    else:
        print(f"{RED}❌ Invalid input '{is_correct}'. Please enter 'y' / 'corrected', 'n', or provide the corrected file path.{RESET}")

# ============================================================
# STEP 19 - Parquet Conversion
# ============================================================

if proceed_parquet:
    print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
    print(f"{HEADER}{BOLD}   ⏳ [STEP 19/20] Converting Final Processed File to Parquet...{RESET}")
    print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")
    from parquet_conersion import convert_csv_to_parquet

    city_folder = target_city_name.title()
    parquet_output_file = (
        rf"G:\.shortcut-targets-by-id\1oGd6xPdp686p0qW-tzZyy5quOpi82hLA\DB1+DB2\converted_feather_parquet\{city_folder}\{city_folder}_db1.parquet"
    )

    try:
        print(f"  {CYAN}📥 Input File (Drive) :{RESET} {output_path}")
        print(f"  {CYAN}📤 Output Parquet     :{RESET} {parquet_output_file}")

        result = convert_csv_to_parquet(
            input_file=output_path,
            output_file=parquet_output_file,
            date_cols=["transaction_date", "date_of_agreement_execution"],
        )

        print(f"{GREEN}✓ [STEP 19/20] Parquet conversion completed successfully!{RESET}")
        print(f"  {CYAN}📊 Parquet Summary:{RESET} {result}")
    except Exception as pe:
        print(f"{RED}❌ [STEP 19/20] Error converting to Parquet: {pe}{RESET}")
else:
    print(f"\n{YELLOW}⚠️ [STEP 19/20] Parquet conversion skipped.{RESET}")

# ============================================================
# STEP 20 - Trigger Database Upload Pipeline (final_code.py)
# ============================================================
import subprocess
from pathlib import Path

print(f"\n{HEADER}{BOLD}{'=' * 60}{RESET}")
print(f"{HEADER}{BOLD}   🚀 [STEP 20/20] Triggering Database Upload Pipeline...{RESET}")
print(f"{HEADER}{BOLD}{'=' * 60}{RESET}")

# Resolve path to DB1_DB2_Uploading_Pipeline root directory
project_root = Path(__file__).resolve().parents[2]
final_code_path = project_root / "final_code.py"

# Fallback to central pipeline repository if executed from a task-specific directory
if not final_code_path.exists():
    central_dir = Path(r"E:\Nilesh\Database\DB1_DB2_Uploading_Pipeline")
    if (central_dir / "final_code.py").exists():
        project_root = central_dir
        final_code_path = central_dir / "final_code.py"

if not final_code_path.exists():
    print(f"{RED}❌ Error: Could not locate final_code.py at: {final_code_path}{RESET}")
else:
    # Optional: Prompt user before triggering upload
    trigger = input(f"\n{YELLOW}Do you want to run final_code.py now? (y/n) [default: y]: {RESET}").strip().lower()
    if trigger in ("", "y", "yes"):
        try:
            # sys.executable ensures the same virtual environment (venv) is used
            subprocess.run([sys.executable, str(final_code_path)], cwd=str(project_root), check=True)
            print(f"\n{GREEN}{BOLD}🎉 final_code.py finished successfully!{RESET}")
        except subprocess.CalledProcessError as e:
            print(f"\n{RED}❌ final_code.py exited with error code: {e.returncode}{RESET}")
        except KeyboardInterrupt:
            print(f"\n{YELLOW}⚠️ final_code.py execution interrupted by user.{RESET}")
    else:
        print(f"{BLUE}ℹ Database upload skipped.{RESET}")



