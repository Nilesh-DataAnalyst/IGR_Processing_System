import os
import sys
import json
import time
import socket
import threading
import traceback
from pathlib import Path
import subprocess
from datetime import datetime
try:
    from http.server import ThreadingHTTPServer as HTTPServerClass
except ImportError:
    from http.server import HTTPServer as HTTPServerClass
from http.server import BaseHTTPRequestHandler
import urllib.parse
import psycopg2
import pandas as pd
import numpy as np

# Change directory to required_files so local module imports work
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(CURR_DIR)
sys.path.insert(0, CURR_DIR)

import pipeline_core as core
from city_config import CITY_CONFIG, get_city_config, extract_folder_id, get_manual_correction_drive_url, LOCATION_DRIVE_CONFIG, render_correction_email_html
from DictToColumn import process_dict_to_column
from static import result_dict
from transaction_categorizer import categorise
from project_name_Std_and_area_conversion import process_dataframe
from rera_matching import process_rera_matching
# from project_coordinates import populate_project_coordinates
from db_columns import DB_SEQUENCE

import re

WEB_DIR = os.path.join(CURR_DIR, "web")

# ============================================================
# GOOGLE DRIVE CONFIGURATION & CONSTANTS
# ============================================================
# Google Drive configuration (initialized to None; resolved dynamically per request / selected city)
DEFAULT_DRIVE_FOLDER_URL = None
DEFAULT_DRIVE_FOLDER_ID = None

DEFAULT_INPUT_DRIVE_FOLDER_URL = None
DEFAULT_INPUT_DRIVE_FOLDER_ID = None

DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL = None
DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_ID = None


def resolve_drive_directory(drive_target: str = None) -> str:
    """Resolves a Google Drive folder URL, folder ID, or local Drive path to a writable local directory on G:."""
    drive_target = drive_target or (DEFAULT_DRIVE_FOLDER_URL if "DEFAULT_DRIVE_FOLDER_URL" in globals() else None)
    if not drive_target or not str(drive_target).strip():
        return None

    if os.path.isdir(str(drive_target).strip()):
        return str(drive_target).strip()

    clean_target = str(drive_target).strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    if not folder_id:
        return None

    base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
    if os.path.exists(base_shortcut_path):
        try:
            sub_items = [
                os.path.join(base_shortcut_path, d)
                for d in os.listdir(base_shortcut_path)
                if os.path.isdir(os.path.join(base_shortcut_path, d))
            ]
            for sub in sub_items:
                if "final processed" in os.path.basename(sub).lower():
                    return sub
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

    if os.path.exists(r"G:\My Drive"):
        return r"G:\My Drive"

    return None


def resolve_manual_correction_directory(
    drive_target: str = None,
    location_name: str = None,
) -> str:
    """
    Resolves the Google Drive folder for Manually Corrected files.
    If location_name is given, ensures a subfolder for that location is created and returned.
    """
    if not drive_target:
        drive_target = get_manual_correction_drive_url(
            location_name=location_name
        ) or (DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL if "DEFAULT_MANUAL_CORRECTION_DRIVE_FOLDER_URL" in globals() else None)

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
    elif os.path.isdir(clean_target):
        manual_root = clean_target

    # Fallback to general city manual correction folder if specific location shortcut ID is not mounted on G:
    if not manual_root or not os.path.exists(manual_root):
        mumbai_mc_id = extract_folder_id(CITY_CONFIG["mumbai"]["manual_correction_drive_url"])
        mumbai_base = os.path.join(r"G:\.shortcut-targets-by-id", mumbai_mc_id)
        if os.path.exists(mumbai_base):
            sub_items = [
                os.path.join(mumbai_base, d)
                for d in os.listdir(mumbai_base)
                if os.path.isdir(os.path.join(mumbai_base, d))
            ]
            for sub in sub_items:
                if "manually corrected" in os.path.basename(sub).lower():
                    manual_root = sub
                    break
            if not manual_root:
                manual_root = sub_items[0] if sub_items else mumbai_base

    if not manual_root or not os.path.exists(manual_root):
        return None

    if location_name:
        loc_str = str(location_name).strip()
        loc_key = loc_str.lower()
        # If the target folder is already the dedicated folder for this location (e.g. Bandra folder)
        is_dedicated_loc_folder = False
        if loc_key in LOCATION_DRIVE_CONFIG:
            dedicated_id = extract_folder_id(LOCATION_DRIVE_CONFIG[loc_key].get("manual_correction_drive_url"))
            if dedicated_id and dedicated_id.lower() == folder_id.lower():
                is_dedicated_loc_folder = True

        if is_dedicated_loc_folder or os.path.basename(manual_root).lower() == loc_key:
            return manual_root

        loc_dir = os.path.join(manual_root, loc_str)
        os.makedirs(loc_dir, exist_ok=True)
        return loc_dir

    return manual_root


def scan_drive_locations(drive_target: str) -> list:
    """
    Scans a Google Drive shortcut target or folder for location-wise subfolders and Excel/CSV files.
    Returns a list of dicts:
    [{ "location": loc_name, "folder_path": path, "drive_url": url, "files": [ { "name": filename, "path": full_path } ] }]
    """
    if not drive_target or not str(drive_target).strip():
        return []

    clean_target = str(drive_target).strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean_target)
    folder_id = match.group(1) if match else clean_target

    if not folder_id:
        return []

    base_shortcut_path = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
    scan_root = None

    if os.path.exists(base_shortcut_path):
        sub_dirs = [
            os.path.join(base_shortcut_path, d)
            for d in os.listdir(base_shortcut_path)
            if os.path.isdir(os.path.join(base_shortcut_path, d))
        ]
        # Look for category subfolders like '3. Manually Corrected' or '2. LLM Processed Data'
        for sub in sub_dirs:
            if any(term in os.path.basename(sub).lower() for term in ["manually corrected", "llm processed", "final processed"]):
                scan_root = sub
                break
        if not scan_root and sub_dirs:
            scan_root = sub_dirs[0]
        elif not scan_root:
            scan_root = base_shortcut_path
    elif os.path.isdir(clean_target):
        scan_root = clean_target

    if not scan_root or not os.path.exists(scan_root):
        return []

    # Check if folder itself is a dedicated location folder (e.g. Bandra)
    dedicated_loc_name = None
    for loc_k, loc_v in LOCATION_DRIVE_CONFIG.items():
        if extract_folder_id(loc_v.get("manual_correction_drive_url")).lower() == folder_id.lower():
            dedicated_loc_name = loc_v.get("display_name", loc_k.title())
            break

    valid_exts = (".xlsx", ".xls", ".csv")
    location_dict = {}

    if dedicated_loc_name:
        excel_files = [
            f for f in os.listdir(scan_root)
            if f.lower().endswith(valid_exts) and not f.startswith("~$")
        ]
        if excel_files:
            return [{
                "location": dedicated_loc_name,
                "folder_path": scan_root,
                "drive_url": drive_target,
                "files": [{"name": f, "path": os.path.join(scan_root, f)} for f in sorted(excel_files)],
            }]

    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        excel_files = [
            f for f in files
            if f.lower().endswith(valid_exts) and not f.startswith("~$")
        ]
        if excel_files:
            loc_name = os.path.basename(root)
            if loc_name.lower() != os.path.basename(scan_root).lower():
                loc_drive_url = get_manual_correction_drive_url(location_name=loc_name)
                location_dict[loc_name] = {
                    "location": loc_name,
                    "folder_path": root,
                    "drive_url": loc_drive_url or drive_target,
                    "files": [{"name": f, "path": os.path.join(root, f)} for f in sorted(excel_files)],
                }

    if not location_dict:
        root_files = [
            f for f in os.listdir(scan_root)
            if f.lower().endswith(valid_exts) and not f.startswith("~$")
        ]
        if root_files:
            loc_name = dedicated_loc_name or "General"
            location_dict[loc_name] = {
                "location": loc_name,
                "folder_path": scan_root,
                "drive_url": drive_target,
                "files": [{"name": f, "path": os.path.join(scan_root, f)} for f in sorted(root_files)],
            }

    return sorted(list(location_dict.values()), key=lambda x: x["location"])


def extract_pincode(text):
    if pd.isna(text):
        return pd.NA
    match = re.search(r"\b(4\d{5})\b", str(text))
    return match.group(1) if match else pd.NA


def add_buyer_location(df: pd.DataFrame, postal_csv_path: str = None) -> pd.DataFrame:
    """Extracts buyer_pincode from buyer_name and enriches with postal location data."""
    df = df.copy()
    if "buyer_name" in df.columns:
        extracted = df["buyer_name"].apply(extract_pincode)
        if "buyer_pincode" in df.columns:
            df["buyer_pincode"] = df["buyer_pincode"].fillna(extracted)
        else:
            df["buyer_pincode"] = extracted
    elif "buyer_pincode" not in df.columns:
        df["buyer_pincode"] = pd.NA

    if postal_csv_path is None:
        postal_csv_path = os.path.join(CURR_DIR, "postal_pincode.csv")

    if not os.path.exists(postal_csv_path):
        for col in ["buyer_locality", "buyer_district", "buyer_state"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df

    df = df.drop(columns=["buyer_locality", "buyer_district", "buyer_state"], errors="ignore")
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
        postal["buyer_pincode"] = pd.to_numeric(postal["buyer_pincode"], errors="coerce").astype("Int64")
        postal = postal.dropna(subset=["buyer_pincode"]).drop_duplicates(subset=["buyer_pincode"], keep="first")
        df["buyer_pincode"] = pd.to_numeric(df["buyer_pincode"], errors="coerce").astype("Int64")
        merged = pd.merge(df, postal, on="buyer_pincode", how="left")
        return merged.drop_duplicates(keep="first") if len(merged) != len(df) else merged
    except Exception:
        for col in ["buyer_locality", "buyer_district", "buyer_state"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df


def format_deadline_text(deadline: str = None) -> tuple:
    """Returns (body_line, subject_tag, formatted_deadline) from deadline string."""
    if not deadline or not str(deadline).strip():
        return "", "", ""
    d_str = str(deadline).strip()
    formatted = d_str
    try:
        if "T" in d_str:
            dt = datetime.fromisoformat(d_str)
            formatted = dt.strftime("%d %b %Y (%a) at %I:%M %p")
    except Exception:
        pass
    body_line = f"\n⏰ Expected Deadline: {formatted}\n"
    subject_tag = f" [Deadline: {formatted}]"
    return body_line, subject_tag, formatted


def build_correction_email_content(
    loc_intro: str,
    file_name: str,
    drive_url: str,
    file_path: str,
    deadline_body: str = "",
    formatted_dl: str = None,
    is_attachment: bool = True,
) -> tuple:
    """Builds both plain-text and HTML versions of the manual correction email with bold formatting."""
    delivery_note_plain = "Please find the file attached with this email." if is_attachment else "Please access the file directly from Google Drive using the link above."
    delivery_note_html = "📎 <strong>Please find the file attached with this email.</strong>" if is_attachment else "🌐 <strong>Please access the file directly from Google Drive using the link above.</strong>"

    deadline_banner_html = ""
    if formatted_dl:
        deadline_banner_html = f"""
        <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin: 14px 0; border-radius: 4px; font-size: 13.5px;">
            <strong style="color: #b45309;">⏰ Expected Deadline:</strong> <span style="color: #92400e; font-weight: 600;">{formatted_dl}</span>
        </div>
        """

    plain_text = f"""Hello,

{loc_intro} is ready for review.{deadline_body}
📄 File: {file_name}
🌐 Google Drive Folder: {drive_url}
📂 Local / Drive Path: {file_path}

{delivery_note_plain}

Please review and correct the following fields:

Project Name :-
• Keep the project name clean and consistent with the original Property Details.
• Remove unnecessary suffixes such as CHS, Building, Phase, etc.
• Do not use English-translated names generated by the LLM. For example, if the Property Details mention “Swapnapoorti”, retain “Swapnapoorti” instead of “Dream Fulfillment.”
• Remove values such as Shop No., Room No., Gat No., Survey No., etc., if they have been incorrectly captured as the project name.

Net Carpet Area :-
• Review net_carpet_area only for Sale transactions.
• Where multiple areas are mentioned, such as Total Land Area, Owner’s Share, or Sold Portion, select the actual transacted/sold area.
• If multiple flats/shops are included in the same transaction, add their individual areas and use the total area.
• Please manually verify records where:
  - the area unit is not mentioned,
  - the mentioned unit appears incorrect, or
  - there is confusion in identifying the correct carpet/transacted area.
  In such cases, refer carefully to the original Property Details before finalizing the area.

Unit Number & Floor Number :-
• Review unit_number and floor_number against the original Property Details.
• unit_number should contain only the actual Flat No., Shop No., Room No., Unit No., etc.
• floor_number should contain only the actual floor information, such as Ground Floor, 1st Floor, 2nd Floor, etc.
• Do not consider project/building names, Gat No., Survey No., road names, or other location details as unit or floor numbers.

Example:
Shop No: Shop No - B 402, Floor No: Prisma L, Building Name: Gat No - 79, Block Sector: Moshi 412105, Road: Borhadewadi, City: Moshi, District: Pune
In this case, B 402 should be captured as the unit_number. Prisma L should not be considered the floor_number if it represents a building/project name. If the actual floor is not mentioned, keep the floor_number blank.

For better understanding and reference, please refer to the following sheet:
https://docs.google.com/spreadsheets/d/1q_HORd89098vHCav494NeFej8zHVWyDHWkvkE-B6mmE/edit?gid=1073436546#gid=1073436546

Please complete the review and corrections accordingly.

Best regards,
Nilesh K.
"""

    html_text = render_correction_email_html(
        loc_intro=loc_intro,
        file_name=file_name,
        drive_url=drive_url,
        file_path=file_path,
        delivery_note_html=delivery_note_html,
        deadline_banner_html=deadline_banner_html,
    )

    return plain_text, html_text


def send_correction_email(
    file_path: str,
    recipient_emails: list,
    location_name: str = None,
    deadline: str = None,
    drive_url: str = None,
    city_id: int = None,
    cc_emails: list = None,
) -> dict:
    """Sends manual correction file via SMTP with attachment, falling back to link notification."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    if cc_emails is None:
        cc_emails = [
            "deeksha@sigmavalue.co.in",
            #"paryushan@sigmavalue.co.in",
            #"anurag@sigmavalue.co.in",
            "nilesh@sigmavalue.co.in",
        ]
    # Clean up email lists
    clean_recipients = [r.strip() for r in recipient_emails if r and r.strip()]
    clean_cc = [c.strip() for c in (cc_emails or []) if c and c.strip()]
    all_recipients = list(dict.fromkeys(clean_recipients + clean_cc))

    sender_email = "nilesh@sigmavalue.co.in"
    sender_password = "nvlf igcl tyxm nnwo"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    # Infer location_name if missing
    if not location_name and file_path:
        parent_candidate = os.path.basename(os.path.dirname(file_path))
        if parent_candidate and parent_candidate.lower() not in ["3. manually corrected", "processing", "required_files", "data"]:
            location_name = parent_candidate
        else:
            location_name = os.path.splitext(os.path.basename(file_path))[0].split("_")[0]

    # Priority 1: Exact location-specific Google Drive link (e.g. Bandra)
    exact_loc_url = get_manual_correction_drive_url(
        city_identifier=city_id or pipeline_state.get("city_id"),
        location_name=location_name,
        file_path=file_path,
    )
    if exact_loc_url:
        drive_url = exact_loc_url
    elif not drive_url:
        cid = city_id or pipeline_state.get("city_id", 9)
        drive_url = get_city_config(cid).get("manual_correction_drive_url") or "Google Drive folder not configured for this city (Local File)"

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Correction file not found: {file_path}")

    file_name = os.path.basename(file_path)
    loc_str = f" for {location_name}" if location_name else ""
    loc_intro = f"The {location_name} manual correction file" if location_name else "The manual correction file"
    deadline_body, deadline_subj, formatted_dl = format_deadline_text(deadline)

    try:
        # Top-level container for mixed content (alternative body parts + attachments)
        msg = MIMEMultipart("mixed")
        msg["From"] = f"Nilesh <{sender_email}>"
        msg["To"] = ", ".join(clean_recipients)
        if clean_cc:
            msg["Cc"] = ", ".join(clean_cc)
        msg["Subject"] = f"[Manual Correction Required]{deadline_subj} {loc_str.strip()} - {file_name}"

        plain_body, html_body = build_correction_email_content(
            loc_intro=loc_intro,
            file_name=file_name,
            drive_url=drive_url,
            file_path=file_path,
            deadline_body=deadline_body,
            formatted_dl=formatted_dl,
            is_attachment=True,
        )

        # Alternative container for plain text and HTML (with bold headers)
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(plain_body, "plain", "utf-8"))
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_part)

        with open(file_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {file_name}")
        msg.attach(part)

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=300)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, all_recipients, msg.as_string())
        server.quit()
        return {
            "status": "sent",
            "mode": "attachment",
            "recipients": clean_recipients,
            "cc": clean_cc,
            "deadline_formatted": formatted_dl,
        }
    except Exception as err:
        # Fallback to link-only multipart/alternative email
        fallback_msg = MIMEMultipart("alternative")
        fallback_msg["From"] = f"Nilesh <{sender_email}>"
        fallback_msg["To"] = ", ".join(clean_recipients)
        if clean_cc:
            fallback_msg["Cc"] = ", ".join(clean_cc)
        fallback_msg["Subject"] = f"[Manual Correction Required]{deadline_subj} {loc_str.strip()} - {file_name}"

        fallback_plain, fallback_html = build_correction_email_content(
            loc_intro=loc_intro,
            file_name=file_name,
            drive_url=drive_url,
            file_path=file_path,
            deadline_body=deadline_body,
            formatted_dl=formatted_dl,
            is_attachment=False,
        )
        fallback_msg.attach(MIMEText(fallback_plain, "plain", "utf-8"))
        fallback_msg.attach(MIMEText(fallback_html, "html", "utf-8"))

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, all_recipients, fallback_msg.as_string())
        server.quit()
        return {
            "status": "sent",
            "mode": "link_fallback",
            "recipients": clean_recipients,
            "cc": clean_cc,
            "deadline_formatted": formatted_dl,
            "note": f"Sent link notification (attachment failed: {err})",
        }


def resolve_upload_pipeline_paths():
    """Resolves project_root and final_code_path for Step 19 and manual launch."""
    project_root = Path(CURR_DIR).resolve().parents[1]
    final_code_path = project_root / "final_code.py"
    if not final_code_path.exists():
        central_dir = Path(r"E:\Nilesh\Database\DB1_DB2_Uploading_Pipeline")
        if (central_dir / "final_code.py").exists():
            return central_dir, central_dir / "final_code.py"
        central_dir_d = Path(r"E:\Nilesh\Database\DB1_DB2_Uploading_Pipeline")
        if (central_dir_d / "final_code.py").exists():
            return central_dir_d, central_dir_d / "final_code.py"
    return project_root, final_code_path


def launch_upload_pipeline_terminal(final_code_path, cwd):
    """Launches final_code.py in an interactive cmd terminal window with proper Windows quote escaping."""
    # In Windows cmd.exe /k, wrapping in an outer pair of double quotes is required
    # when both the python executable and script path contain quotes.
    cmd = f'start "Database Upload Pipeline (final_code.py)" cmd.exe /k ""{sys.executable}" "{final_code_path}""'
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        shell=True
    )


# Global thread-safe state container
pipeline_state = {
    "state": "idle",             # "idle" | "running" | "awaiting_manual_file" | "awaiting_parquet_confirmation" | "completed" | "failed" | "stopped"
    "current_step_id": 0,
    "current_step_name": "",
    "progress": 0,
    "mode": "1",
    "city_id": None,
    "city_name": None,
    "city_key": None,
    "divisor": None,
    "error": None,
    "output_file": None,
    "v1_file": None,
    "manual_file": None,
    "parquet_file": None,
    "final_code_path": None,
    "location_name": None,
    "metrics": {
        "total_rows": 0,
        "rera_matched": 0,
        "nr_assigned": 0
    },
    "logs": [],
    "stop_requested": False,
    "steps": [
        {"id": 1, "name": "Input File Ingestion", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 2, "name": "DictToColumn Processing", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 3, "name": "Project Name Resolution", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 4, "name": "Static Transaction Mapping", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 5, "name": "Transaction Categorization", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 6, "name": "Standardization & Area Conversion", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 7, "name": "Manual Corrected File Load", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 8, "name": "Column Renaming & Standardizing", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 9, "name": "Property Type Categorization", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 10, "name": "Buyer Location & Pincode Lookup", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 11, "name": "RERA Grand Reference Matching", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 12, "name": "PostgreSQL NR Index Assignment", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 13, "name": "Location Coordinates Lookup", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 14, "name": "Project Coordinates (Google Places API)", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 15, "name": "DB Schema Column Alignment", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 16, "name": "Title Casing", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 17, "name": "Final Output Save (Drive & Local)", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 18, "name": "Parquet Conversion", "status": "pending", "detail": "Waiting", "duration": "-"},
        {"id": 19, "name": "Database Upload Pipeline", "status": "pending", "detail": "Waiting", "duration": "-"}
    ]
}

state_lock = threading.Lock()
resume_step7_event = threading.Event()
resume_step18_event = threading.Event()


def add_log(text, level="info"):
    with state_lock:
        timestamp = time.strftime("%H:%M:%S")
        entry = {"time": timestamp, "text": f"[{timestamp}] {text}", "level": level}
        pipeline_state["logs"].append(entry)
        if len(pipeline_state["logs"]) > 500:
            pipeline_state["logs"].pop(0)


def update_step_status(step_id, status, detail=None, duration=None):
    with state_lock:
        for s in pipeline_state["steps"]:
            if s["id"] == step_id:
                s["status"] = status
                if detail: s["detail"] = detail
                if duration: s["duration"] = duration
                break


def run_pipeline_worker(params):
    global pipeline_state

    mode = params.get("mode", "1")
    input_file = params.get("input_file")
    manual_file = params.get("manual_file")

    # Determine or infer location name first
    location_name = params.get("location_name")
    if not location_name and input_file:
        parent_dir = os.path.basename(os.path.dirname(input_file))
        if parent_dir and parent_dir.lower() not in ["2. llm processed data", "processing", "required_files", "data", "uploading_pipeline"]:
            location_name = parent_dir
        else:
            base = os.path.splitext(os.path.basename(input_file))[0]
            location_name = base.split("_")[0]
    if not location_name and manual_file:
        parent_dir = os.path.basename(os.path.dirname(manual_file))
        if parent_dir and parent_dir.lower() not in ["3. manually corrected", "processing", "required_files", "data"]:
            location_name = parent_dir
        else:
            base = os.path.splitext(os.path.basename(manual_file))[0]
            location_name = base.split("_")[0]

    # Auto-detect city from location_name or file path so Mumbai/Bandra/Thane never default to Pune
    city_id_raw = params.get("city_id")
    loc_lower = (location_name or "").lower()
    path_lower = (input_file or manual_file or "").lower()

    if loc_lower == "bandra" or "bandra" in path_lower:
        city_cfg = get_city_config("bandra")
    elif any(pat in loc_lower or pat in path_lower for pat in ["mumbai", "borivali", "andheri", "kurla", "chembur", "dadar", "goregaon", "malad", "powai", "1ywb1-csrdxnv80yc8axym5bgze34txfa", "1rt8pvmus_s03yrsmvk93lumghbe-9rwd"]):
        city_cfg = get_city_config("mumbai")
    elif any(pat in loc_lower or pat in path_lower for pat in ["thane", "kalyan", "dombivli", "navi mumbai", "mira bhayandar"]):
        city_cfg = get_city_config("thane")
    elif city_id_raw:
        city_cfg = get_city_config(city_id_raw)
    else:
        city_cfg = get_city_config("pune")

    city_id = int(city_cfg.get("city_id", 9))
    city_key = city_cfg.get("key", "pune")
    city_name = city_cfg.get("display_name", "Pune")
    active_divisor = city_cfg.get("saleable_to_carpet_divisor", 1.35)
    output_path = params.get("output_path")
    include_geocoding = params.get("include_geocoding", False)

    if not location_name:
        location_name = "Bandra" if "bandra" in path_lower else ("Borivali" if "borivali" in path_lower else ("Mohmadwadi" if city_id == 9 else "General"))

    resume_step7_event.clear()
    resume_step18_event.clear()

    with state_lock:
        pipeline_state["state"] = "running"
        pipeline_state["mode"] = mode
        pipeline_state["city_id"] = city_id
        pipeline_state["city_name"] = city_name
        pipeline_state["city_key"] = city_key
        pipeline_state["divisor"] = active_divisor
        pipeline_state["final_drive_url"] = city_cfg.get("final_drive_url")
        pipeline_state["stop_requested"] = False
        pipeline_state["error"] = None
        pipeline_state["output_file"] = None
        pipeline_state["v1_file"] = None
        pipeline_state["manual_file"] = manual_file
        pipeline_state["location_name"] = location_name
        pipeline_state["progress"] = 0
        pipeline_state["logs"] = []
        for s in pipeline_state["steps"]:
            if mode == "3" and s["id"] < 18:
                s["status"] = "skipped"
                s["detail"] = "Skipped in Mode 3"
            elif mode == "2" and s["id"] < 7:
                s["status"] = "skipped"
                s["detail"] = "Skipped in Mode 2"
            else:
                s["status"] = "pending"
                s["detail"] = "Waiting"
                s["duration"] = "-"

    add_log(f"Starting pipeline in Mode {mode} for {city_name} (City ID: {city_id}, Divisor: {active_divisor}) - Location: '{location_name}'...", "info")
    df = None

    try:
        if mode == "3":
            # RESUME DIRECTLY FROM STEP 18 (PARQUET CONVERSION)
            final_file = output_path or manual_file or input_file
            if not final_file or not os.path.exists(final_file):
                raise FileNotFoundError(f"Final processed file does not exist: {final_file}")
            add_log(f"Step 17: Loading final processed file for Parquet conversion: {final_file}", "info")
            target_out = final_file
            with state_lock:
                pipeline_state["output_file"] = target_out
                pipeline_state["progress"] = 95
        elif mode == "2":
            # RESUME DIRECTLY FROM STEP 7
            if not manual_file or not os.path.exists(manual_file):
                raise FileNotFoundError(f"Manual corrected file does not exist: {manual_file}")

            add_log(f"Loading manual corrected file: {manual_file}", "info")
            t0 = time.time()
            update_step_status(7, "running", "Loading file...")
            with state_lock:
                pipeline_state["current_step_id"] = 7
                pipeline_state["current_step_name"] = "Loading Manual Corrected File"
                pipeline_state["progress"] = 43

            df = pd.read_excel(manual_file, engine="openpyxl")
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(7, "completed", f"{len(df)} rows loaded", dur)
            add_log(f"Step 7: Loaded {len(df)} rows from manual file.", "success")
            with state_lock:
                pipeline_state["metrics"]["total_rows"] = len(df)

        else:
            # MODE 1: RUN STEPS 1 TO 6
            if not input_file or not os.path.exists(input_file):
                raise FileNotFoundError(f"Input file does not exist: {input_file}")

            # STEP 1
            t0 = time.time()
            update_step_status(1, "running", "Verifying file...")
            with state_lock:
                pipeline_state["current_step_id"] = 1
                pipeline_state["current_step_name"] = "Input File Ingestion"
                pipeline_state["progress"] = 6
            add_log(f"Step 1: Input file verified: {input_file} (Location: {location_name})", "info")
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(1, "completed", f"Verified ({location_name})", dur)

            # STEP 2 - DictToColumn
            t0 = time.time()
            update_step_status(2, "running", "Extracting columns...")
            with state_lock:
                pipeline_state["current_step_id"] = 2
                pipeline_state["current_step_name"] = "DictToColumn Processing"
                pipeline_state["progress"] = 12
            add_log("Step 2: Running DictToColumn extraction...", "info")
            df = process_dict_to_column(input_file)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(2, "completed", f"{len(df)} rows", dur)
            add_log(f"Step 2: DictToColumn completed - {len(df)} rows.", "success")
            with state_lock:
                pipeline_state["metrics"]["total_rows"] = len(df)

            # STEP 3 - Final Project Name
            t0 = time.time()
            update_step_status(3, "running", "Resolving names...")
            with state_lock:
                pipeline_state["current_step_id"] = 3
                pipeline_state["current_step_name"] = "Project Name Resolution"
                pipeline_state["progress"] = 18
            project_name_missing = df["project_name_en"].replace(r"^\s*$", pd.NA, regex=True).isna()
            df["final_project_name"] = (
                df["project_name_en"].replace(r"^\s*$", pd.NA, regex=True).fillna(df["building_name_en"])
            )
            df["final_project_name_status"] = project_name_missing.map(
                {True: "Building Name Considered", False: "Project Name Considered"}
            )
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(3, "completed", "Names resolved", dur)
            add_log("Step 3: Final project name created.", "success")

            # STEP 4 - Static Dictionary Mapping
            t0 = time.time()
            update_step_status(4, "running", "Mapping docnames...")
            with state_lock:
                pipeline_state["current_step_id"] = 4
                pipeline_state["current_step_name"] = "Static Transaction Mapping"
                pipeline_state["progress"] = 25
            df["transaction_type"] = df["docname"].map(result_dict.get)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(4, "completed", "Types mapped", dur)
            add_log("Step 4: Static dictionary mapping completed.", "success")

            # STEP 5 - Transaction Categorisation
            t0 = time.time()
            update_step_status(5, "running", "Categorising...")
            with state_lock:
                pipeline_state["current_step_id"] = 5
                pipeline_state["current_step_name"] = "Transaction Categorization"
                pipeline_state["progress"] = 31
            df = categorise(df)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(5, "completed", "Categorised", dur)
            add_log("Step 5: Transaction categorisation completed.", "success")

            # STEP 5.5 - Populate village_name_marathi from DB (matching main.py)
            try:
                df = core.populate_village_mapping(df, city_id, core.DB_PARAMS)
                add_log("Step 5.5: Populated village_name_marathi -> location_name & registered_document_village_name from DB.", "info")
            except Exception as ve:
                add_log(f"Step 5.5: Village mapping note: {ve}", "warning")

            # STEP 6 - Standardization & Area Conversion
            t0 = time.time()
            update_step_status(6, "running", "Standardizing & converting...")
            with state_lock:
                pipeline_state["current_step_id"] = 6
                pipeline_state["current_step_name"] = "Standardization & Area Conversion"
                pipeline_state["progress"] = 37

            # Resolve manual correction Google Drive folder for location
            loc_manual_drive_url = get_manual_correction_drive_url(
                city_identifier=city_id,
                location_name=location_name,
                file_path=input_file,
            )
            manual_drive_url = loc_manual_drive_url or city_cfg.get("manual_correction_drive_url")
            manual_dir = resolve_manual_correction_directory(
                manual_drive_url,
                location_name=location_name,
            )
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            out_file_name = f"{base_name}_for_manual.xlsx" if not base_name.endswith("_for_manual") else f"{base_name}.xlsx"

            if manual_dir and os.path.exists(manual_dir):
                v1_output_path = os.path.join(manual_dir, out_file_name)
                add_log(f"Step 6: Target Google Drive (3. Manually Corrected): {v1_output_path}", "info")
            else:
                input_dir = os.path.dirname(input_file) or CURR_DIR
                v1_output_path = os.path.join(input_dir, out_file_name)
                add_log(f"Step 6: Saving locally: {v1_output_path}", "warning")

            df = process_dataframe(df, output_path=v1_output_path, city=city_key)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(6, "completed", f"Saved manual file ({len(df)} rows)", dur)
            add_log(f"Step 6: Standardization completed -> Saved: {v1_output_path}", "success")

            # ============================================================
            # STEP 7: PAUSE AND WAIT FOR USER MANUAL CORRECTED FILE
            # ============================================================
            with state_lock:
                pipeline_state["state"] = "awaiting_manual_file"
                pipeline_state["current_step_id"] = 7
                pipeline_state["current_step_name"] = "Waiting for Manual Corrected File"
                pipeline_state["v1_file"] = v1_output_path
                pipeline_state["location_name"] = location_name
                pipeline_state["manual_drive_url"] = manual_drive_url

            update_step_status(7, "running", "Waiting for manual review/correction...")
            add_log("=" * 60, "warning")
            add_log(f"⏸️ Step 6 finished! Standardized file saved to: {v1_output_path}", "warning")
            add_log("⏸️ Pipeline PAUSED at Step 7. You can share this file or select a location file to resume.", "warning")
            add_log("=" * 60, "warning")

            # Wait for resume signal from client via /api/resume
            while not resume_step7_event.is_set():
                if pipeline_state.get("stop_requested"):
                    add_log("Pipeline cancelled while waiting for manual file.", "error")
                    with state_lock:
                        pipeline_state["state"] = "stopped"
                    return
                time.sleep(0.5)

            # Once resumed, load the manual corrected file!
            resolved_manual_file = pipeline_state.get("manual_file") or v1_output_path
            if not os.path.exists(resolved_manual_file):
                raise FileNotFoundError(f"Manual corrected file does not exist: {resolved_manual_file}")
            add_log(f"Step 7: Resumed! Loading manual corrected file: {resolved_manual_file}", "info")
            t0 = time.time()
            df = pd.read_excel(resolved_manual_file, engine="openpyxl")
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(7, "completed", f"{len(df)} rows loaded", dur)
            add_log(f"Step 7: Loaded {len(df)} rows from manual file.", "success")
            with state_lock:
                pipeline_state["metrics"]["total_rows"] = len(df)
                pipeline_state["state"] = "running"

        if mode != "3":
            # ============================================================
            # STEPS 8 TO 16
            # ============================================================

            # STEP 8 - Rename Columns
            t0 = time.time()
            update_step_status(8, "running", "Renaming columns...")
            with state_lock:
                pipeline_state["current_step_id"] = 8
                pipeline_state["current_step_name"] = "Column Renaming & Standardizing"
                pipeline_state["progress"] = 52
            df = core.rename_columns(df)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(8, "completed", "Renamed", dur)
            add_log("Step 8: Column renaming completed.", "success")

            # STEP 9 - Property Type Categorization
            t0 = time.time()
            update_step_status(9, "running", "Categorising property type...")
            with state_lock:
                pipeline_state["current_step_id"] = 9
                pipeline_state["current_step_name"] = "Property Type Categorization"
                pipeline_state["progress"] = 58
            df["property_type"] = df["property_type_raw"].apply(core._map_property_type)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(9, "completed", "Categorised", dur)
            add_log("Step 9: Property type categorization completed.", "success")

            # Village Mapping from Transactions DB (Step 5.5 / 10)
            if "location_name" not in df.columns or "registered_document_village_name" not in df.columns or df["registered_document_village_name"].isna().all():
                try:
                    df = core.populate_village_mapping(df, city_id, core.DB_PARAMS)
                    add_log("Step 10: Populated registered_document_village_name and location_name from DB.", "info")
                except Exception as ve:
                    add_log(f"Step 10: Village mapping note: {ve}", "warning")

            # STEP 10 - Adding Buyer Location and Pincode (matching main.py Step 10)
            t0 = time.time()
            update_step_status(10, "running", "Adding buyer location & pincode...")
            with state_lock:
                pipeline_state["current_step_id"] = 10
                pipeline_state["current_step_name"] = "Buyer Location & Pincode Lookup"
                pipeline_state["progress"] = 65
            df = add_buyer_location(df)
            matched_pincodes = int(df["buyer_pincode"].notna().sum()) if "buyer_pincode" in df.columns else 0
            matched_locations = int(df["buyer_locality"].notna().sum()) if "buyer_locality" in df.columns else 0
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(10, "completed", f"{matched_pincodes} pincodes, {matched_locations} locs", dur)
            add_log(f"Step 10: Buyer location and pincode added ({matched_pincodes} pincodes, {matched_locations} locations).", "success")

            # STEP 11 - Matching with RERA
            t0 = time.time()
            update_step_status(11, "running", "Matching RERA reference...")
            with state_lock:
                pipeline_state["current_step_id"] = 11
                pipeline_state["current_step_name"] = "RERA Grand Reference Matching"
                pipeline_state["progress"] = 70

            import importlib
            import city_config
            importlib.reload(city_config)
            from city_config import resolve_rera_grand_path

            rera_path = resolve_rera_grand_path(city_key or city_name)
            if rera_path and os.path.exists(rera_path):
                add_log(f"Step 11: Using RERA dataset {os.path.basename(rera_path)} for {city_name}", "info")
                df = process_rera_matching(df, city=city_name, rera_grand_path=rera_path)
            elif city_key == "pune":
                df = process_rera_matching(df, city="Pune")
            else:
                for c in ["index", "modified_project_name", "rera_location_v1", "rera_location",
                          "project_lat", "project_lng", "BHK", "Final BHK", "Final Property Type"]:
                    if c not in df.columns:
                        df[c] = pd.NA
                if "BHK" in df.columns and "property_type" in df.columns:
                    df["BHK"] = df["BHK"].fillna(df["property_type"])
                add_log(f"Step 11: No RERA dataset configured for {city_name}; skipped safely.", "warning")

            # Alignment defaults
            for col in ["transaction_date", "date_of_agreement_execution"]:
                df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
            df["quarter"] = "Q" + df["transaction_date"].dt.quarter.astype(str) + "-" + df["transaction_date"].dt.year.astype(str)
            for col in ["transaction_date", "date_of_agreement_execution"]:
                df[col] = df[col].dt.strftime("%d/%m/%Y")

            rename_map = {
                "location": "location_name",
                "igr_village": "registered_document_village_name",
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
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

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
                "city_name": city_name,
                "project_stage": pd.NA,
                "is_llm_processed": "No",
                "is_manual_processed": "No",
            }
            for col, val in defaults.items():
                if col not in df.columns:
                    df[col] = val

            rera_matched_count = int(df["index"].notna().sum()) if "index" in df.columns else 0
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(11, "completed", f"{rera_matched_count} matched", dur)
            add_log(f"Step 11: RERA matching completed - {rera_matched_count} matches found.", "success")
            with state_lock:
                pipeline_state["metrics"]["rera_matched"] = rera_matched_count

            # STEP 12 - Assign NR Indexes
            t0 = time.time()
            update_step_status(12, "running", "Querying PostgreSQL...")
            with state_lock:
                pipeline_state["current_step_id"] = 12
                pipeline_state["current_step_name"] = "PostgreSQL NR Index Assignment"
                pipeline_state["progress"] = 75
            df, nr_stats = core.assign_nr_indexes(df, target_city_id=city_id, db_params=core.DB_PARAMS)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(12, "completed", f"{nr_stats['assigned_count']} new NRs", dur)
            add_log(f"Step 12: Assigned {nr_stats['assigned_count']} new NRs. Highest NR: {nr_stats['highest_new_nr']}.", "success")
            with state_lock:
                pipeline_state["metrics"]["nr_assigned"] = nr_stats["assigned_count"]

            # STEP 13 - Populate Location Coordinates
            t0 = time.time()
            update_step_status(13, "running", "Looking up location coords...")
            with state_lock:
                pipeline_state["current_step_id"] = 13
                pipeline_state["current_step_name"] = "Location Coordinates Lookup"
                pipeline_state["progress"] = 80
            df = core.populate_location_coords(df, city_id, core.DB_PARAMS)
            dur = f"{time.time() - t0:.2f}s"
            loc_coords_found = int(df["location_latitude"].notna().sum()) if "location_latitude" in df.columns else 0
            update_step_status(13, "completed", f"{loc_coords_found} populated", dur)
            add_log(f"Step 13: Location LatLong populated ({loc_coords_found} found).", "success")

            # STEP 14 - Fill remaining project coordinates using Google Places API (Temporarily commented in main.py)
            if include_geocoding:
                t0 = time.time()
                update_step_status(14, "running", "Querying Places API...")
                with state_lock:
                    pipeline_state["current_step_id"] = 14
                    pipeline_state["current_step_name"] = "Project Coordinates (Google Places API)"
                    pipeline_state["progress"] = 84
                try:
                    from project_coordinates import populate_project_coordinates
                    df = populate_project_coordinates(df)
                    dur = f"{time.time() - t0:.2f}s"
                    update_step_status(14, "completed", "Populated", dur)
                    add_log("Step 14: Project coordinates enriched via Google Places API.", "success")
                except Exception as pe:
                    dur = f"{time.time() - t0:.2f}s"
                    update_step_status(14, "failed", str(pe), dur)
                    add_log(f"Step 14: Google Places geocoding note: {pe}", "warning")
            else:
                update_step_status(14, "skipped", "Temporarily Commented / Skipped", "-")
                add_log("Step 14: Project Coordinates skipped (temporarily commented in main.py).", "info")

            # STEP 15 - Keep Selective DB Columns
            t0 = time.time()
            update_step_status(15, "running", "Filtering columns...")
            with state_lock:
                pipeline_state["current_step_id"] = 15
                pipeline_state["current_step_name"] = "DB Schema Column Alignment"
                pipeline_state["progress"] = 88
            df = core.keep_db_columns(df, DB_SEQUENCE)
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(15, "completed", f"{len(df.columns)} columns", dur)
            add_log(f"Step 15: Retained {len(df.columns)} columns matching DB schema.", "success")

            # STEP 16 - Title Casing
            t0 = time.time()
            update_step_status(16, "running", "Applying title case...")
            with state_lock:
                pipeline_state["current_step_id"] = 16
                pipeline_state["current_step_name"] = "Title Casing"
                pipeline_state["progress"] = 90

            for col in df.select_dtypes(include=["object"]).columns:
                df[col] = df[col].apply(lambda x: x.title() if isinstance(x, str) else x)

            dur = f"{time.time() - t0:.2f}s"
            update_step_status(16, "completed", f"{len(df)} rows formatted", dur)
            add_log("Step 16: Title casing applied to text columns.", "success")

            # STEP 17 - Final Output Save (Google Drive Primary & Local Backup)
            t0 = time.time()
            update_step_status(17, "running", "Saving output to Drive & local...")
            with state_lock:
                pipeline_state["current_step_id"] = 17
                pipeline_state["current_step_name"] = "Final Output Save (Drive & Local)"
                pipeline_state["progress"] = 95

            src = manual_file or input_file
            base_name = "output"
            if src:
                base_name = os.path.splitext(os.path.basename(src))[0]
                for suffix in ["_for_manual", "_processed_v1", "_processed", "_llm_output"]:
                    base_name = base_name.replace(suffix, "")
            default_filename = f"{base_name}_final_processed.xlsx"

            final_drive_url = city_cfg.get("final_drive_url")
            drive_dir = resolve_drive_directory(final_drive_url)
            location_drive_path = os.path.join(drive_dir, location_name) if (drive_dir and location_name) else drive_dir

            raw_out = (output_path or "").strip()
            if raw_out.lower().startswith("g:\\"):
                drive_out = raw_out
                local_out = os.path.join(CURR_DIR, os.path.basename(raw_out))
            elif raw_out and os.path.dirname(raw_out):
                # User provided a local path like D:\Nilesh\...\file.xlsx
                filename = os.path.basename(raw_out)
                drive_out = os.path.join(location_drive_path, filename) if location_drive_path else None
                local_out = raw_out
            else:
                filename = raw_out if raw_out else default_filename
                if not filename.lower().endswith(".xlsx"):
                    filename = f"{filename}.xlsx"
                drive_out = os.path.join(location_drive_path, filename) if location_drive_path else None
                local_out = os.path.join(CURR_DIR, filename)

            # 1. Save to Google Drive (if configured)
            drive_saved = False
            if drive_out:
                try:
                    os.makedirs(os.path.dirname(drive_out), exist_ok=True)
                    df.to_excel(drive_out, index=False)
                    add_log(f"Step 17: ☁️ Saved final output to Google Drive ({city_name}): {drive_out}", "success")
                    drive_saved = True
                except Exception as de:
                    add_log(f"Step 17: ⚠️ Note saving to Google Drive ({drive_out}): {de}", "warning")

            # 2. Save local copy (Fallback if drive save failed or Drive not configured)
            if not drive_saved and local_out:
                try:
                    os.makedirs(os.path.dirname(local_out), exist_ok=True)
                    df.to_excel(local_out, index=False)
                    add_log(f"Step 17: 📁 Local copy saved ({city_name}): {local_out}", "info")
                except Exception as le:
                    add_log(f"Step 17: ⚠️ Note saving local copy ({local_out}): {le}", "warning")

            # Target file for parquet input and display (prefer Drive path if saved)
            target_out = drive_out if (drive_saved and drive_out) else (local_out or drive_out)

            dur = f"{time.time() - t0:.2f}s"
            update_step_status(17, "completed", f"Saved {len(df)} rows", dur)
            with state_lock:
                pipeline_state["output_file"] = target_out

        # ============================================================
        # STEP 18 VERIFICATION: PAUSE AND WAIT FOR USER CONFIRMATION
        # ============================================================
        candidate_parquet_file = (drive_out if (locals().get("drive_saved") and locals().get("drive_out") and os.path.exists(drive_out)) else target_out)
        resume_step18_event.clear()
        with state_lock:
            pipeline_state["state"] = "awaiting_parquet_confirmation"
            pipeline_state["current_step_id"] = 18
            pipeline_state["current_step_name"] = "Waiting for Parquet Confirmation"
            pipeline_state["output_file"] = candidate_parquet_file
            pipeline_state["final_drive_url"] = final_drive_url or city_cfg.get("final_drive_url")
            pipeline_state["proceed_parquet"] = True

        update_step_status(18, "running", "Waiting for user confirmation...")
        add_log("=" * 60, "warning")
        add_log(f"⏸️ Step 17 finished! Final dataset: {candidate_parquet_file}", "warning")
        add_log("⏸️ Pipeline PAUSED: Please verify if final processed file is correct before Parquet conversion.", "warning")
        add_log("=" * 60, "warning")

        while not resume_step18_event.is_set():
            if pipeline_state.get("stop_requested"):
                add_log("Pipeline cancelled while waiting for Parquet confirmation.", "error")
                with state_lock:
                    pipeline_state["state"] = "stopped"
                return
            time.sleep(0.5)

        with state_lock:
            pipeline_state["state"] = "running"
            proceed_parquet = pipeline_state.get("proceed_parquet", True)
            target_out = pipeline_state.get("output_file") or candidate_parquet_file

        if proceed_parquet:
            # STEP 18 - Parquet Conversion
            t0 = time.time()
            update_step_status(18, "running", "Converting to Parquet...")
            with state_lock:
                pipeline_state["current_step_id"] = 18
                pipeline_state["current_step_name"] = "Parquet Conversion"
                pipeline_state["progress"] = 96

            from parquet_conersion import convert_csv_to_parquet

            # Resolve city name dynamically from city_id or dataframe
            city_name = "Pune"
            try:
                conn = psycopg2.connect(**core.DB_PARAMS)
                cur = conn.cursor()
                cur.execute("SELECT city_name FROM public.dim_city WHERE city_id = %s;", (city_id,))
                row = cur.fetchone()
                if row and row[0]:
                    city_name = str(row[0]).strip().title()
                cur.close()
                conn.close()
            except Exception:
                pass

            if df is not None and "city_name" in df.columns:
                first_val = df["city_name"].dropna().iloc[0] if len(df["city_name"].dropna()) > 0 else ""
                if first_val:
                    city_name = str(first_val).strip().title()

            parquet_base_dir = r"G:\.shortcut-targets-by-id\1oGd6xPdp686p0qW-tzZyy5quOpi82hLA\DB1+DB2\converted_feather_parquet"
            if not os.path.exists(parquet_base_dir):
                parquet_base_dir = os.path.join(CURR_DIR, "converted_feather_parquet")

            city_parquet_dir = os.path.join(parquet_base_dir, city_name)
            os.makedirs(city_parquet_dir, exist_ok=True)
            parquet_target = os.path.join(city_parquet_dir, f"{city_name}_db1.parquet")

            parquet_input = target_out
            add_log(f"Step 18: Converting {parquet_input} -> {parquet_target} ...", "info")
            pq_res = convert_csv_to_parquet(
                input_file=parquet_input,
                output_file=parquet_target,
                date_cols=["transaction_date", "date_of_agreement_execution"],
            )

            dur = f"{time.time() - t0:.2f}s"
            row_count = pq_res.get('rows', len(df) if df is not None else 0)
            update_step_status(18, "completed", f"Converted {row_count:,} rows", dur)
            add_log(f"Step 18: Parquet conversion completed successfully -> {parquet_target}", "success")
            with state_lock:
                pipeline_state["parquet_file"] = parquet_target
        else:
            update_step_status(18, "skipped", "Skipped by user", "-")
            add_log("Step 18: Parquet conversion skipped by user.", "warning")

        # STEP 19 - Trigger Database Upload Pipeline (final_code.py)
        t0 = time.time()
        update_step_status(19, "running", "Triggering Database Upload Pipeline...")
        with state_lock:
            pipeline_state["current_step_id"] = 19
            pipeline_state["current_step_name"] = "Database Upload Pipeline"
            pipeline_state["progress"] = 99

        project_root, final_code_path = resolve_upload_pipeline_paths()

        add_log(f"Step 19: Locating upload pipeline at: {final_code_path}", "info")
        auto_upload = params.get("auto_upload", True)

        if not final_code_path.exists():
            add_log(f"Step 19: ⚠️ Could not locate final_code.py at: {final_code_path}", "warning")
            dur = f"{time.time() - t0:.2f}s"
            update_step_status(19, "completed", "final_code.py not found", dur)
        else:
            if auto_upload:
                try:
                    add_log("Step 19: 🚀 Launching final_code.py in interactive terminal window...", "info")
                    launch_upload_pipeline_terminal(final_code_path, project_root)
                    dur = f"{time.time() - t0:.2f}s"
                    update_step_status(19, "completed", "Launched in Terminal", dur)
                    add_log(f"Step 19: ✓ final_code.py launched successfully ({final_code_path})! Proceed with database upload in the terminal window.", "success")
                except Exception as fe:
                    add_log(f"Step 19: ⚠️ Error launching final_code.py: {fe}", "warning")
                    dur = f"{time.time() - t0:.2f}s"
                    update_step_status(19, "completed", "Launch Error", dur)
            else:
                dur = f"{time.time() - t0:.2f}s"
                update_step_status(19, "completed", "Ready to Launch", dur)
                add_log("Step 19: Auto-upload skipped. You can trigger final_code.py anytime from the dashboard.", "info")

        with state_lock:
            pipeline_state["state"] = "completed"
            pipeline_state["progress"] = 100
            pipeline_state["current_step_name"] = "Pipeline Finished Successfully!"
            pipeline_state["output_file"] = target_out
            pipeline_state["parquet_file"] = parquet_target
            pipeline_state["final_code_path"] = str(final_code_path) if final_code_path.exists() else None

    except Exception as e:
        err_msg = str(e)
        add_log(f"ERROR: {err_msg}", "error")
        add_log(traceback.format_exc(), "error")
        with state_lock:
            pipeline_state["state"] = "failed"
            pipeline_state["error"] = err_msg
            curr_id = pipeline_state["current_step_id"]
            if curr_id > 0:
                update_step_status(curr_id, "failed", "Failed with error", "-")


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default server access noise in stdout

    def get_query_param(self, name: str, default=None):
        if "?" not in self.path:
            return default
        query_str = self.path.split("?", 1)[1]
        params = urllib.parse.parse_qs(query_str)
        vals = params.get(name, [])
        return vals[0] if vals else default

    def do_GET(self):
        url_path = self.path.split("?")[0]

        if url_path in ["/", "/index.html"]:
            self.serve_file(os.path.join(WEB_DIR, "index.html"), "text/html")
        elif url_path == "/style.css":
            self.serve_file(os.path.join(WEB_DIR, "style.css"), "text/css")
        elif url_path == "/app.js":
            self.serve_file(os.path.join(WEB_DIR, "app.js"), "application/javascript")
        elif url_path == "/api/status":
            self.send_json(pipeline_state)
        elif url_path == "/api/cities":
            self.send_json(CITY_CONFIG)
        elif url_path == "/api/drive/input-locations":
            city_param = self.get_query_param("city") or self.get_query_param("city_id")
            cfg = get_city_config(city_param) if city_param else {}
            drive_url = cfg.get("input_drive_url") if cfg else None
            locations = scan_drive_locations(drive_url) if drive_url else []
            self.send_json({
                "city": cfg.get("display_name", ""),
                "city_id": cfg.get("city_id"),
                "drive_url": drive_url,
                "locations": locations
            })
        elif url_path == "/api/drive/manual-locations":
            city_param = self.get_query_param("city") or self.get_query_param("city_id")
            cfg = get_city_config(city_param) if city_param else {}
            drive_url = cfg.get("manual_correction_drive_url") if cfg else None
            locations = scan_drive_locations(drive_url) if drive_url else []
            for loc in locations:
                loc_name = loc.get("location", "")
                loc_drive = get_manual_correction_drive_url(cfg.get("city_id"), loc_name)
                if loc_drive:
                    loc["drive_url"] = loc_drive
            self.send_json({
                "city": cfg.get("display_name", ""),
                "city_id": cfg.get("city_id"),
                "drive_url": drive_url,
                "locations": locations
            })
        elif url_path == "/api/drive/final-locations":
            city_param = self.get_query_param("city") or self.get_query_param("city_id")
            cfg = get_city_config(city_param) if city_param else {}
            drive_url = cfg.get("final_drive_url") if cfg else None
            locations = scan_drive_locations(drive_url) if drive_url else []
            self.send_json({
                "city": cfg.get("display_name", ""),
                "city_id": cfg.get("city_id"),
                "drive_url": drive_url,
                "locations": locations
            })
        elif url_path == "/email_template.html":
            self.serve_file(os.path.join(WEB_DIR, "email_template.html"), "text/html")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if self.path == "/api/run":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                params = json.loads(body)
            except Exception:
                self.send_json({"error": "Invalid JSON"}, status=400)
                return

            if pipeline_state["state"] == "running":
                self.send_json({"error": "A pipeline run is already in progress."}, status=409)
                return

            thread = threading.Thread(target=run_pipeline_worker, args=(params,), daemon=True)
            thread.start()
            self.send_json({"status": "started"})

        elif self.path == "/api/resume":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                manual_file = data.get("manual_file")
                output_path = data.get("output_path")
                city_id = data.get("city_id") or pipeline_state.get("city_id", 9)
                include_geocoding = data.get("include_geocoding", False)
                auto_upload = data.get("auto_upload", True)
            except Exception:
                data = {}
                manual_file = None
                output_path = None
                city_id = pipeline_state.get("city_id", 9)
                include_geocoding = False
                auto_upload = True

            with state_lock:
                current_state = pipeline_state.get("state")
                if manual_file:
                    pipeline_state["manual_file"] = manual_file

            if current_state == "awaiting_manual_file":
                add_log(f"Resuming pipeline at Step 7 with: {manual_file}", "info")
                resume_step7_event.set()
                self.send_json({"status": "resumed", "state": "running"})
            else:
                if not manual_file:
                    self.send_json({"error": "Manual file path is required to resume."}, status=400)
                    return
                add_log(f"Launching pipeline in Mode 2 (Step 7 -> 20) with: {manual_file}", "info")
                params = {
                    "mode": "2",
                    "manual_file": manual_file,
                    "location_name": data.get("location_name"),
                    "output_path": output_path,
                    "city_id": city_id,
                    "include_geocoding": include_geocoding,
                    "auto_upload": auto_upload,
                }
                thread = threading.Thread(target=run_pipeline_worker, args=(params,), daemon=True)
                thread.start()
                self.send_json({"status": "started", "state": "running"})

        elif self.path == "/api/share-email":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                file_path = data.get("file_path")
                recipients = data.get("recipients", [])
                location_name = data.get("location_name")
                deadline = data.get("deadline")
                city_id = data.get("city_id") or pipeline_state.get("city_id", 9)
                drive_url = data.get("drive_url")
                if isinstance(recipients, str):
                    recipients = [r.strip() for r in recipients.split(",") if r.strip()]
                if not file_path or not recipients:
                    self.send_json({"error": "file_path and recipients are required"}, status=400)
                    return

                # If location_name is missing, try inferring from file_path
                if not location_name and file_path:
                    parent_c = os.path.basename(os.path.dirname(file_path))
                    if parent_c and parent_c.lower() not in ["3. manually corrected", "processing", "required_files", "data"]:
                        location_name = parent_c
                    else:
                        location_name = os.path.splitext(os.path.basename(file_path))[0].split("_")[0]

                # Priority: enforce accurate location drive url (Bandra, etc.)
                resolved_url = get_manual_correction_drive_url(
                    city_identifier=city_id,
                    location_name=location_name,
                    file_path=file_path,
                )
                if resolved_url:
                    drive_url = resolved_url

                cc_param = data.get("cc_emails") or data.get("cc")
                if isinstance(cc_param, str):
                    cc_emails = [c.strip() for c in cc_param.split(",") if c.strip()]
                elif isinstance(cc_param, list):
                    cc_emails = cc_param
                else:
                    cc_emails = None

                result = send_correction_email(
                    file_path,
                    recipients,
                    location_name,
                    deadline=deadline,
                    city_id=city_id,
                    drive_url=drive_url,
                    cc_emails=cc_emails,
                )
                cc_sent = result.get("cc", [])
                cc_log = f" (CC: {', '.join(cc_sent)})" if cc_sent else ""
                log_dl = f" (Deadline: {result.get('deadline_formatted') or deadline})" if deadline else ""
                add_log(f"📧 Manual correction file shared with: {', '.join(recipients)}{cc_log}{log_dl}", "success")
                self.send_json(result)
            except Exception as e:
                add_log(f"⚠️ Email sharing error: {e}", "warning")
                self.send_json({"error": str(e)}, status=500)

        elif self.path == "/api/launch-upload":
            project_root, final_code_path = resolve_upload_pipeline_paths()

            if not final_code_path.exists():
                self.send_json({"error": f"final_code.py not found at: {final_code_path}"}, status=404)
                return

            try:
                launch_upload_pipeline_terminal(final_code_path, project_root)
                add_log(f"🚀 Manual action: final_code.py launched in terminal window ({final_code_path}).", "success")
                self.send_json({"status": "launched", "path": str(final_code_path)})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)

        elif self.path == "/api/confirm-parquet":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            action = data.get("action", "proceed")  # "proceed" | "skip"
            file_path = data.get("file_path")

            with state_lock:
                current_state = pipeline_state.get("state")
                if file_path:
                    pipeline_state["output_file"] = file_path
                pipeline_state["proceed_parquet"] = (action != "skip")

            if current_state == "awaiting_parquet_confirmation":
                if action == "skip":
                    add_log("User choice: Skip Parquet conversion (Step 18).", "warning")
                else:
                    chosen = file_path or pipeline_state.get("output_file")
                    add_log(f"User confirmed final processed file: {chosen}. Proceeding to Step 18 Parquet conversion...", "success")
                resume_step18_event.set()
                self.send_json({"status": "resumed", "state": "running"})
            else:
                self.send_json({"error": "Pipeline is not currently awaiting Parquet confirmation."}, status=400)

        elif self.path == "/api/stop":
            with state_lock:
                pipeline_state["stop_requested"] = True
                pipeline_state["state"] = "stopped"
            resume_step7_event.set()
            resume_step18_event.set()
            add_log("Stop requested by user.", "warning")
            self.send_json({"status": "stopped"})
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data, status=200):
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def find_available_port(start_port=8000, max_tries=10):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    return start_port


def start_server():
    port = find_available_port(8000)
    server = HTTPServerClass(("localhost", port), DashboardHandler)
    url = f"http://localhost:{port}"
    print("\n" + "=" * 60)
    print(f"🚀 Sogaon Pipeline Web Dashboard Running!")
    print(f"👉 Open in browser: {url}")
    print("=" * 60 + "\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    start_server()
