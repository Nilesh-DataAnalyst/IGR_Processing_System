"""
End-to-end standalone pipeline for Abu Dhabi Real Estate (ADREC) transaction data processing.

Matches the architecture and execution style of Dubai's dld_pipeline.py and Pune processing:
  Step 1 (UI/Scraper): Ingest from ADREC portal via adrec_downloader.py (skippable)
  Step 2: Load raw CSV (dtype=str, utf-8-sig)
  Step 3: Drop duplicate transactions
  Step 4: Parse Sale Application Date -> transaction_date / year / quarter / date_of_agreement_execution
  Step 5: Map Property Type -> property_type
  Step 6: Map Asset Class -> project_type
  Step 7: Map Property Layout -> normalized_unit_configuration
  Step 8: Enrich location details from Abudhabi_location_coordinates.csv:
          location_id, location_latitude, location_longitude (with Jabal Hafeet fallback)
  Step 9: Match against Abudhabi_project_coordinates.csv:
          project_latitude, project_longitude, internal_index_id via composite key
  Step 10: Geocode missing commercial projects via Google Places API & ArcGIS fallback (Private project lat/long kept blank)
  Step 11: Assign Non-RERA index (internal_index_id):
          - Master table highest NR is Nr467__abu_dhabi -> starts strictly from nr468
          - Reuses existing NR indexes for matched master projects
          - Assigns sequential nr468, nr469, etc. for all unlisted commercial and private projects [project_name + location_name]
  Step 12: DB schema column alignment (internal_index_id as primary field, project_id removed) & Title Case
  Step 13: Save final .xlsx and .csv output files directly to Google Drive Processed Data folder

Can be run via CLI or invoked automatically via server.py web interface.
"""

import os
import sys
import re
import time
import tempfile
import shutil
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
import numpy as np
import pandas as pd
import requests

# Windows console UTF-8 safety & unbuffered stream
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

# Ensure print flushes immediately by default for real-time UI responsiveness
_orig_print = print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    return _orig_print(*args, **kwargs)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if any(h in sys.argv for h in ["-h", "--help"]):
    print("""
Usage: python adrec_pipeline.py [OPTIONS]

Abu Dhabi Real Estate (ADREC) Transaction Data Processing Pipeline.

Options:
  --input, --input-file <PATH>   Specify custom raw CSV input file path or Drive file ID.
  --auto-confirm, -y             Automatically confirm the latest detected input file.
  --non-interactive              Run in non-interactive mode without terminal prompts.
  --skip-geocoding, --no-geocoding Skip Google Places & ArcGIS geocoding for new projects.
  --db, -d <DB>                  Target database name [Default: nilesh].
  --raw-folder-id <ID>           Google Drive folder ID for raw data.
  --processed-folder-id <ID>     Google Drive folder ID for processed data.
  -h, --help                     Show this help message and exit.
""")
    sys.exit(0)

# ============================== CONFIGURATION & PATH RESOLUTION ==============================
CITY_ID = 1
CITY_NAME = "Abu Dhabi"
ABU_DHABI_PARENT_FOLDER_ID = "1h_cUque4NqERMGvE__LaJgLuanXu1Ov2"
RAW_FOLDER_ID = "1F5Wau7ePRd90JI2nKaUDqa6kJLiWvqjG"
PROCESSED_FOLDER_ID = "126uTbJ8Sp4mHUuhgR6Q18W6k6qtgEu0s"
GOOGLE_MAPS_API_KEY = "AIzaSyBS63yAQTYMnYAKDv5gQ7G1Qw2ngup15-w"

PROJ_COORDS_FILE = os.path.join(SCRIPT_DIR, "Abudhabi_project_coordinates.csv")
LOC_COORDS_FILE = os.path.join(SCRIPT_DIR, "Abudhabi_location_coordinates.csv")

# Parse CLI overrides
for _idx, _arg in enumerate(sys.argv):
    if _arg == "--raw-folder-id" and _idx + 1 < len(sys.argv):
        RAW_FOLDER_ID = sys.argv[_idx + 1].strip()
    elif _arg == "--processed-folder-id" and _idx + 1 < len(sys.argv):
        PROCESSED_FOLDER_ID = sys.argv[_idx + 1].strip()

# Staging directory in system temp to guarantee NO local repository clutter
STAGING_DIR = tempfile.mkdtemp(prefix="adrec_pipe_")
IS_TEMP_STAGING = True


def fetch_raw_files_from_drive(folder_id: str = RAW_FOLDER_ID) -> List[Dict[str, Any]]:
    """Returns a list of raw transaction CSV files from Google Drive Raw Data folder (with fallback to parent if empty)."""
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        import adrec_downloader
        service = adrec_downloader.get_google_drive_service()
        if not service:
            return []

        # 1. Check designated Raw Data folder
        q = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
        res = service.files().list(
            q=q,
            fields="files(id, name, modifiedTime, size)",
            orderBy="modifiedTime desc",
            pageSize=50
        ).execute()
        files = res.get("files", [])
        raw_files = [
            f for f in files
            if f.get("name", "").lower().endswith(".csv")
            and not any(ign in f.get("name", "").lower() for ign in ["_processed", "cleaned", "coordinates", "master", "reference"])
        ]

        # 2. Fallback to parent folder if raw data folder is currently empty
        if not raw_files and folder_id != ABU_DHABI_PARENT_FOLDER_ID:
            q_parent = f"'{ABU_DHABI_PARENT_FOLDER_ID}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
            res_parent = service.files().list(
                q=q_parent,
                fields="files(id, name, modifiedTime, size)",
                orderBy="modifiedTime desc",
                pageSize=50
            ).execute()
            parent_files = res_parent.get("files", [])
            raw_files = [
                f for f in parent_files
                if f.get("name", "").lower().endswith(".csv")
                and not any(ign in f.get("name", "").lower() for ign in ["_processed", "cleaned", "coordinates", "master", "reference"])
            ]

        return raw_files
    except Exception as e:
        print(f"⚠️ [Drive] Error fetching files from Raw Data folder: {e}")
        return []


def download_drive_file_if_needed(file_identifier: str, dest_dir: str) -> Optional[str]:
    """
    If file_identifier is a local path that exists, returns it.
    Otherwise downloads it from Google Drive into dest_dir using Google Drive API.
    """
    if os.path.isfile(file_identifier):
        return file_identifier

    local_cand = os.path.join(dest_dir, os.path.basename(file_identifier))
    if os.path.isfile(local_cand):
        return local_cand

    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        import adrec_downloader
        service = adrec_downloader.get_google_drive_service()
        if not service:
            return None

        # 1. Try treating file_identifier as Drive file ID
        try:
            meta = service.files().get(fileId=file_identifier, fields="id, name").execute()
            fname = meta.get("name", "downloaded_adrec.csv")
            out_path = os.path.join(dest_dir, fname)
            print(f"[Drive] Downloading '{fname}' (ID: {file_identifier}) from Google Drive...")
            req = service.files().get_media(fileId=file_identifier)
            with open(out_path, "wb") as f:
                f.write(req.execute())
            print(f"✔ [Drive] Download complete: {out_path}")
            return out_path
        except Exception:
            pass

        # 2. Try treating file_identifier as filename query
        q = f"name = '{file_identifier}' and trashed = false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            fid = files[0]["id"]
            fname = files[0]["name"]
            out_path = os.path.join(dest_dir, fname)
            print(f"[Drive] Downloading '{fname}' by name from Google Drive...")
            req = service.files().get_media(fileId=fid)
            with open(out_path, "wb") as f:
                f.write(req.execute())
            print(f"✔ [Drive] Download complete: {out_path}")
            return out_path
    except Exception as e:
        print(f"⚠️ [Drive] Could not download file '{file_identifier}': {e}")

    return None


def select_or_confirm_input_file(dest_dir: str, raw_folder_id: str) -> str:
    """
    Confirms or selects raw transaction CSV file directly from Google Drive Raw Data folder.
    """
    auto_confirm = any(arg in sys.argv for arg in ["--auto-confirm", "-y", "--non-interactive"])

    # 1. Check CLI specified input file
    for idx, arg in enumerate(sys.argv):
        if arg in ["--input", "--input-file"] and idx + 1 < len(sys.argv):
            candidate = sys.argv[idx + 1].strip().strip('"').strip("'")
            if os.path.isfile(candidate):
                print(f"[Input] Using specified local file: {candidate}")
                return candidate
            downloaded = download_drive_file_if_needed(candidate, dest_dir)
            if downloaded and os.path.exists(downloaded):
                return downloaded
            raise FileNotFoundError(f"Specified input file/ID '{candidate}' not found.")

    # 2. Query Google Drive Raw Data folder
    drive_files = fetch_raw_files_from_drive(raw_folder_id)
    if not drive_files:
        raise FileNotFoundError(
            f"No raw transaction CSV files found in Google Drive Raw Data folder (ID: {raw_folder_id})."
        )

    latest_file = drive_files[0]
    if auto_confirm:
        print(f"[Input] Auto-confirmed latest Drive file: {latest_file['name']}")
        downloaded = download_drive_file_if_needed(latest_file["id"], dest_dir)
        if downloaded:
            return downloaded
        raise RuntimeError(f"Failed to download {latest_file['name']} from Google Drive.")

    print(f"\n[Detected Latest Raw CSV in Google Drive Raw Data Folder]:")
    print(f"  • Name    : {latest_file['name']}")
    print(f"  • File ID : {latest_file['id']}")
    print(f"  • Modified: {latest_file.get('modifiedTime', 'N/A')}")

    try:
        ans = input("👉 Use this file? [Y/n] or enter 'c' to choose another file: ").strip().lower()
    except EOFError:
        ans = "y"

    if ans in ["", "y", "yes"]:
        downloaded = download_drive_file_if_needed(latest_file["id"], dest_dir)
        if downloaded:
            return downloaded

    print(f"\n[Available Raw CSV Files in Google Drive Raw Data Folder]:")
    for idx, f in enumerate(drive_files, 1):
        sz_mb = int(f.get("size", 0)) / (1024 * 1024) if f.get("size") else 0
        mod = f.get("modifiedTime", "")[:19].replace("T", " ")
        print(f"  [{idx}] {f['name']} ({sz_mb:.2f} MB, {mod})")
    print("  [0] Specify a custom local file path")

    while True:
        try:
            sel = input(f"👉 Select file number (1-{len(drive_files)}) [Default 1]: ").strip()
        except EOFError:
            sel = "1"
        if sel == "":
            sel = "1"
        if sel.isdigit():
            val = int(sel)
            if 1 <= val <= len(drive_files):
                chosen = drive_files[val - 1]
                print(f"   ✔ Selected Drive file: {chosen['name']}\n")
                downloaded = download_drive_file_if_needed(chosen["id"], dest_dir)
                if downloaded:
                    return downloaded
                raise RuntimeError(f"Failed to download {chosen['name']}")
            elif val == 0:
                custom_p = input("👉 Enter custom CSV file path: ").strip().strip('"').strip("'")
                if os.path.isfile(custom_p):
                    print(f"   ✔ Selected custom input file: {os.path.basename(custom_p)}\n")
                    return custom_p
                print(f"   ❌ File does not exist: {custom_p}")
        elif os.path.isfile(sel.strip('"').strip("'")):
            clean_sel = sel.strip('"').strip("'")
            print(f"   ✔ Selected custom input file: {os.path.basename(clean_sel)}\n")
            return clean_sel
        else:
            print("   ❌ Invalid selection! Please enter a valid number or path.")


RAW_CSV_PATH = select_or_confirm_input_file(STAGING_DIR, RAW_FOLDER_ID)

_raw_basename = os.path.basename(RAW_CSV_PATH)
_raw_stem, _ = os.path.splitext(_raw_basename)

cli_db = "nilesh"
for i, arg in enumerate(sys.argv):
    if arg in ["--db", "-d"] and i + 1 < len(sys.argv):
        cli_db = sys.argv[i + 1].strip()

print("=" * 75)
print(f"📁 ABU DHABI DATA PROCESSING PIPELINE")
print(f"   • Raw Drive Folder ID : {RAW_FOLDER_ID}")
print(f"   • Selected CSV File   : {_raw_basename}")
print(f"   • Processed Folder ID : {PROCESSED_FOLDER_ID}")
print(f"   • Runtime City ID     : {CITY_ID} ({CITY_NAME})")
print("=" * 75)

# ============================== STEP 2: LOAD RAW CSV ==============================
print("[STEP:2:START] Loading raw transaction CSV...")
time.sleep(0.35)
t_step = time.time()
if not os.path.exists(RAW_CSV_PATH):
    raise FileNotFoundError(f"'{RAW_CSV_PATH}' does not exist.")

df = pd.read_csv(RAW_CSV_PATH, dtype=str, encoding="utf-8-sig")
df.columns = df.columns.str.strip()
print(f"[step2] loaded raw file: {df.shape}")
time.sleep(0.15)
print(f"[STEP:2:DONE] Loaded {len(df):,} rows and {len(df.columns)} columns from {_raw_basename}")

# ============================== STEP 3: DROP DUPLICATES ==============================
print("[STEP:3:START] Identifying and removing duplicate transaction rows...")
time.sleep(0.35)
t_step = time.time()
before_dedup = len(df)
df = df.drop_duplicates().reset_index(drop=True)
dropped_count = before_dedup - len(df)
print(f"[step3] before={before_dedup}, after={len(df)}, removed={dropped_count}")
time.sleep(0.15)
print(f"[STEP:3:DONE] Removed {dropped_count:,} duplicate rows ({len(df):,} remaining)")

# ============================== STEP 4: PARSE DATES & EXTRACT QUARTERS ==============================
print("[STEP:4:START] Parsing transaction dates and extracting quarters...")
time.sleep(0.35)
t_step = time.time()
_date_series = pd.to_datetime(df["Sale Application Date"], format="%Y-%m-%d", errors="coerce")
for _fmt in ["%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"]:
    if _date_series.isna().any():
        _date_series = _date_series.fillna(pd.to_datetime(df["Sale Application Date"], format=_fmt, errors="coerce"))
if _date_series.isna().any():
    _date_series = _date_series.fillna(pd.to_datetime(df["Sale Application Date"], dayfirst=True, errors="coerce"))

df["transaction_date"] = _date_series
df["date_of_agreement_execution"] = _date_series
df["year"] = df["transaction_date"].dt.year.astype("Int64")
df["quarter"] = "Q" + df["transaction_date"].dt.quarter.astype("Int64").astype(str) + "-" + df["year"].astype(str)
df.loc[df["transaction_date"].isna(), "quarter"] = None

# Format dates to standard DD-MM-YYYY strings
df["transaction_date"] = df["transaction_date"].dt.strftime("%d-%m-%Y")
df["date_of_agreement_execution"] = df["date_of_agreement_execution"].dt.strftime("%d-%m-%Y")
unparsed_count = int(_date_series.isna().sum())
print(f"[step4] unparseable dates: {unparsed_count}")
time.sleep(0.15)
print(f"[STEP:4:DONE] Normalized dates: {df['transaction_date'].min()} to {df['transaction_date'].max()} ({df['quarter'].nunique()} quarters)")

# ============================== STEP 5: PROPERTY TYPE MAPPING ==============================
print("[STEP:5:START] Categorizing raw property types into standard taxonomy...")
time.sleep(0.35)
t_step = time.time()
PROPERTY_TYPE_MAP = {
    "apartment": "Flat",
    "duplex": "Flat",
    "residential complex": "Flat",
    "residential complex (staff accommodation)": "Flat",
    "villa": "Villa",
    "townhouse / attached villa": "Villa",
    "palace": "Villa",
    "office": "Office",
    "office complex": "Office",
    "retail": "Shop",
    "mall / market / retail center": "Shop",
    "other commercial plot": "Plot",
    "other industrial plot": "Plot",
    "other mixed-use plot": "Plot",
    "other plot": "Plot",
    "other residential plot": "Plot",
    "other temporary plot": "Plot",
    "plot for clinic / hospital": "Plot",
    "plot for cooling utility": "Plot",
    "plot for farm": "Plot",
    "plot for hotel / resort / serviced apartments": "Plot",
    "plot for mall / market / retail center": "Plot",
    "plot for office complex": "Plot",
    "plot for palace": "Plot",
    "plot for park": "Plot",
    "plot for parking": "Plot",
    "plot for petrol station": "Plot",
    "plot for residential complex": "Plot",
    "plot for residential complex (staff accommodation)": "Plot",
    "plot for school": "Plot",
    "plot for townhouse / attached villa": "Plot",
    "plot for villa": "Plot",
    "clinic / hospital": "Others",
    "cooling utility": "Others",
    "factory": "Others",
    "farm": "Others",
    "hotel / resort / serviced apartments": "Others",
    "mosque": "Others",
    "other": "Others",
    "penthouse": "Others",
    "petrol station": "Others",
    "school": "Others",
    "workshop": "Others"
}
df["property_type_raw"] = df["Property Type"].fillna("").astype(str).str.strip().str.lower()
df["property_type"] = df["property_type_raw"].map(PROPERTY_TYPE_MAP).fillna("Others")
print("[step5] property_type distribution:\n", df["property_type"].value_counts())
time.sleep(0.15)
print(f"[STEP:5:DONE] Categorized into {df['property_type'].nunique()} standard types (Flats: {(df['property_type'] == 'Flat').sum():,}, Villas: {(df['property_type'] == 'Villa').sum():,})")

# ============================== STEP 6: PROJECT TYPE & ASSET CLASS MAPPING ==============================
print("[STEP:6:START] Classifying asset classes into project types...")
time.sleep(0.35)
t_step = time.time()
PROJECT_TYPE_MAP = {
    "agricultural": "Agricultural",
    "commercial": "Commercial",
    "educational": "Educational",
    "healthcare": "Healthcare",
    "industrial & storage": "Industrial",
    "infrastructural": "Infrastructure",
    "other": "Others",
    "recreational": "Recreational",
    "religious": "Religious",
    "residential": "Residential"
}
df["project_type"] = (
    df["Asset Class"].fillna("").astype(str).str.strip().str.lower().map(PROJECT_TYPE_MAP).fillna("Others")
)
print("[step6] project_type distribution:\n", df["project_type"].value_counts())
time.sleep(0.15)
print(f"[STEP:6:DONE] Mapped {df['project_type'].nunique()} project types (Residential: {(df['project_type'] == 'Residential').sum():,}, Commercial: {(df['project_type'] == 'Commercial').sum():,})")

# ============================== STEP 7: UNIT CONFIGURATION NORMALIZATION ==============================
print("[STEP:7:START] Normalizing unit configurations and property layouts...")
time.sleep(0.35)
t_step = time.time()
NORMALIZED_UNIT_CONFIG_MAP = {
    "1 bed": "1Bhk",
    "2 beds": "2Bhk",
    "3 beds": "3Bhk",
    "4 beds": ">3Bhk",
    "5 beds": ">3Bhk",
    "5+ beds": ">3Bhk",
    "6+ beds": ">3Bhk",
    "anchor store": "Shop",
    "large (500 to 1000 sqm)": "Office",
    "line store": "Shop",
    "maxi (over 1000 sqm)": "Office",
    "medium (50 to 500 sqm)": "Office",
    "small (up to 50 sqm)": "Office",
    "studio": "Flat",
    "unclassified": "Others"
}
df["unit_configuration"] = df["Property Layout"].fillna("").astype(str).str.strip().str.lower()
df["property_layout"] = df["Property Layout"]
df["normalized_unit_configuration"] = df["unit_configuration"].map(NORMALIZED_UNIT_CONFIG_MAP).fillna("Others")
print("[step7] normalized_unit_configuration counts:\n", df["normalized_unit_configuration"].value_counts())
time.sleep(0.15)
print(f"[STEP:7:DONE] Normalized unit configurations ({df['normalized_unit_configuration'].nunique()} classes)")

# Direct Mappings & Defaults
df["project_name"] = df["Project Name"]
df["location_name"] = df["District"]
df["agreement_price"] = pd.to_numeric(df["Property Sale Price (AED)"], errors="coerce")
df["net_carpet_area_sq_m"] = pd.to_numeric(df["Property Sold Area (SQM)"], errors="coerce")
df["project_stage"] = df["Sale Application Type"]
df["sale_type"] = df.get("Sale Sequence", None)
df["sub_locality"] = df.get("Community", None)
# Keep micro_market and property_description completely blank (no mapping)
df["micro_market"] = None
df["property_description"] = None

# Static defaults for Abu Dhabi
df["city_id"] = CITY_ID
df["city_name"] = CITY_NAME
df["state_name"] = "Abu Dhabi"
df["country_name"] = "UAE"
df["transaction_category"] = "Sale"
df["data_source"] = "Adrec"
df["data_type"] = "Registered Document"
df["source_accessibility"] = "Download"
df["source_accessibility_way"] = "Easy"
df["is_llm_processed"] = "No"
df["is_manual_processed"] = "No"

# Placeholder columns for full schema compliance (internal_index_id replacing index)
default_blank_cols = [
    "registered_document_village_name", "sub_registrar_office_code", "sub_registrar_office_name",
    "document_number", "guideline_value", "floor_number", "unit_number", "balcony_sq_m",
    "terrace_sq_m", "seller_name", "buyer_name", "internal_document_number", "micr_number",
    "bank_type", "party_code", "stamp_duty_paid", "registration_fee", "project_latitude",
    "project_longitude", "location_latitude", "location_longitude", "location_id",
    "internal_index_id", "buyer_pincode", "buyer_locality", "buyer_district", "buyer_state", "tower_name",
    "is_duplicate", "pincode", "parking_count", "facing_direction", "view_type", "furnishing_status",
    "condition_status", "sourcing_cost", "sourcing_time"
]
for col in default_blank_cols:
    if col not in df.columns:
        df[col] = None

# Helpers
def norm(s):
    if isinstance(s, pd.Series):
        return s.astype(str).str.strip().str.lower()
    return str(s).strip().lower()

def clean_nr_index(x):
    if pd.isna(x):
        return None
    x = str(x).strip()
    x = re.sub(r"__.*$", "", x)
    m = re.match(r"(?i)^nr(\d+)", x)
    return f"nr{m.group(1)}" if m else x

# ============================== STEP 8: LOCATION COORDINATES & LOCATION ID ==============================
print("[STEP:8:START] Looking up location IDs and coordinates from master reference...")
time.sleep(0.35)
t_step = time.time()
print(f"[step8] Loading master location coordinates from: {LOC_COORDS_FILE}")
if not os.path.exists(LOC_COORDS_FILE):
    raise FileNotFoundError(f"Missing master location coordinates file: {LOC_COORDS_FILE}")

df_loc = pd.read_csv(LOC_COORDS_FILE)
df_loc["norm_loc"] = norm(df_loc["location_name"])

loc_id_map = df_loc.drop_duplicates("norm_loc").set_index("norm_loc")["location_id"].to_dict()
loc_lat_map = df_loc.drop_duplicates("norm_loc").set_index("norm_loc")["location_latitude"].to_dict()
loc_lng_map = df_loc.drop_duplicates("norm_loc").set_index("norm_loc")["location_longitude"].to_dict()

df["norm_loc"] = norm(df["location_name"])
df["location_id"] = df["norm_loc"].map(loc_id_map)
df["location_latitude"] = pd.to_numeric(df["norm_loc"].map(loc_lat_map), errors="coerce")
df["location_longitude"] = pd.to_numeric(df["norm_loc"].map(loc_lng_map), errors="coerce")

# Known fallback for Jabal Hafeet
jabal_mask = df["norm_loc"] == "jabal hafeet"
df.loc[jabal_mask, ["location_latitude", "location_longitude"]] = [24.0716702, 55.7985914]

loc_lat_count = int(df["location_latitude"].notna().sum())
print(f"[step8] Location coordinates mapped: {loc_lat_count}/{len(df)} rows")
print(f"[step8] Location IDs mapped: {df['location_id'].notna().sum()}/{len(df)} rows")
time.sleep(0.15)
print(f"[STEP:8:DONE] Mapped {loc_lat_count:,}/{len(df):,} rows to master locations ({df['location_id'].nunique()} distinct locations)")

# ============================== STEP 9: PROJECT MASTER REFERENCE MATCHING ==============================
print("[STEP:9:START] Matching projects against master reference (Abudhabi_project_coordinates.csv)...")
time.sleep(0.35)
t_step = time.time()
print(f"[step9] Loading master project coordinates from: {PROJ_COORDS_FILE}")
if not os.path.exists(PROJ_COORDS_FILE):
    raise FileNotFoundError(f"Missing master project coordinates file: {PROJ_COORDS_FILE}")

df_proj = pd.read_csv(PROJ_COORDS_FILE)

# Enrich project master with location_name via location_id
df_proj_ref = df_proj.merge(
    df_loc[["location_id", "location_name"]], on="location_id", how="left"
)
df_proj_ref["city_name"] = CITY_NAME
df_proj_ref["norm_proj"] = norm(df_proj_ref["project_name"])
df_proj_ref["norm_loc"] = norm(df_proj_ref["location_name"])
df_proj_ref["norm_city"] = norm(df_proj_ref["city_name"])
df_proj_ref["clean_index"] = df_proj_ref["internal_index_id"].map(clean_nr_index)

# Composite keys: (location_name | project_name | city_name)
master_lat_map = {}
master_lng_map = {}
master_index_map = {}

for _, r in df_proj_ref.iterrows():
    k = (r["norm_loc"], r["norm_proj"], r["norm_city"])
    master_lat_map[k] = r["project_latitude"]
    master_lng_map[k] = r["project_longitude"]
    master_index_map[k] = r["clean_index"]

# Normalize project_name: ensure empty, whitespace, or missing project names become 'Private'
df["project_name"] = df["project_name"].fillna("Private")
blank_mask = df["project_name"].astype(str).str.strip().isin(["", "nan", "<NA>", "None"])
df.loc[blank_mask, "project_name"] = "Private"

df["norm_proj"] = norm(df["project_name"])
df["norm_city"] = norm(df["city_name"])

# Populate from master table
for i in df.index:
    k = (df.at[i, "norm_loc"], df.at[i, "norm_proj"], df.at[i, "norm_city"])
    if k in master_lat_map:
        df.at[i, "project_latitude"] = master_lat_map[k]
        df.at[i, "project_longitude"] = master_lng_map[k]
        df.at[i, "internal_index_id"] = master_index_map[k]

master_matched_rows = int(df["project_latitude"].notna().sum())
print(f"[step9] Master table project match: {master_matched_rows}/{len(df)} rows")
time.sleep(0.15)
print(f"[STEP:9:DONE] Master reference matched {master_matched_rows:,}/{len(df):,} rows ({len(master_lat_map)} master projects)")

# ============================== STEP 10: GOOGLE PLACES & GEOCODING ENRICHMENT ==============================
print("[STEP:10:START] Running Google Places & ArcGIS geocoding...")
time.sleep(0.35)
t_step = time.time()
skip_geocoding = any(arg in sys.argv for arg in ["--skip-geocoding", "--no-geocoding"])

found_geo = 0
if skip_geocoding:
    print("[step10] Geocoding skipped via flag (--skip-geocoding).")
else:
    df["project_latitude"] = pd.to_numeric(df["project_latitude"], errors="coerce")
    df["project_longitude"] = pd.to_numeric(df["project_longitude"], errors="coerce")

    needs_geo_mask = (
        df["project_latitude"].isna()
        & df["norm_proj"].notna()
        & (df["norm_proj"] != "private")
        & (df["norm_proj"] != "")
        & (df["norm_proj"] != "nan")
    )
    unmatched_projects = df.loc[needs_geo_mask, ["project_name", "location_name"]].drop_duplicates()
    print(f"[step10] Distinct newly launched commercial projects needing geocoding: {len(unmatched_projects)}")

    if len(unmatched_projects) > 0:
        def geocode_places(query: str):
            url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            params = {
                "input": query,
                "inputtype": "textquery",
                "fields": "geometry,name,formatted_address",
                "key": GOOGLE_MAPS_API_KEY
            }
            try:
                r = requests.get(url, params=params, timeout=8).json()
                if r.get("status") == "OK" and r.get("candidates"):
                    loc = r["candidates"][0].get("geometry", {}).get("location", {})
                    return loc.get("lat"), loc.get("lng")
            except Exception:
                pass
            return None, None

        arcgis_geolocator = None
        try:
            from geopy.geocoders import ArcGIS
            arcgis_geolocator = ArcGIS(timeout=8)
        except Exception:
            pass

        for idx, row in enumerate(unmatched_projects.iterrows(), 1):
            _, r_data = row
            p_name = str(r_data["project_name"]).strip()
            l_name = str(r_data["location_name"]).strip()
            query = f"{p_name}, {l_name}, Abu Dhabi, UAE"

            lat, lng = geocode_places(query)
            if lat is None and arcgis_geolocator:
                try:
                    res = arcgis_geolocator.geocode(query)
                    if res:
                        lat, lng = res.latitude, res.longitude
                except Exception:
                    pass

            if lat is not None and lng is not None:
                mask = (df["project_name"] == p_name) & (df["location_name"] == l_name)
                df.loc[mask, "project_latitude"] = lat
                df.loc[mask, "project_longitude"] = lng
                found_geo += 1
                print(f"   [{idx}/{len(unmatched_projects)}] 🔍 {query} -> ✔ Found ({lat:.5f}, {lng:.5f})")
            else:
                # Fallback to location coordinates only for named commercial projects if project coords not found
                mask = (df["project_name"] == p_name) & (df["location_name"] == l_name)
                df.loc[mask & df["project_latitude"].isna(), "project_latitude"] = df.loc[mask, "location_latitude"]
                df.loc[mask & df["project_longitude"].isna(), "project_longitude"] = df.loc[mask, "location_longitude"]
                print(f"   [{idx}/{len(unmatched_projects)}] 🔍 {query} -> ⚠️ Fallback to location coordinates")
            time.sleep(0.05)

# For commercial projects not found in geocoding, fallback to location coordinates.
# Private projects that are not present in project coordinates remain blank (do not copy location coordinates).
comm_missing_mask = (df["norm_proj"] != "private") & df["project_latitude"].isna()
df.loc[comm_missing_mask, "project_latitude"] = df.loc[comm_missing_mask, "location_latitude"]
df.loc[comm_missing_mask, "project_longitude"] = df.loc[comm_missing_mask, "location_longitude"]

valid_coords = int(df["project_latitude"].notna().sum())
print(f"[step10] Geocoding complete: {found_geo} newly resolved via API. Total records with project coords: {valid_coords}/{len(df)}")
time.sleep(0.15)
print(f"[STEP:10:DONE] Resolved project coordinates for {valid_coords:,}/{len(df):,} records")

# ============================== STEP 11: ASSIGN NON-RERA INDEX (internal_index_id) ==============================
print("[STEP:11:START] Assigning PostgreSQL NR indexes (internal_index_id) starting from nr468...")
time.sleep(0.35)
t_step = time.time()
master_nr_numbers = df_proj["internal_index_id"].dropna().str.extract(r"(?i)^nr(\d+)")[0].dropna().astype(int)
max_nr = int(master_nr_numbers.max())  # 467
next_num = max_nr + 1                 # 468
print(f"[step11] Master table highest NR = Nr{max_nr}__abu_dhabi")
print(f"[step11] New projects will start strictly from = nr{next_num}")

# Normalize project_name: ensure empty, whitespace, or missing project names become 'Private'
df["project_name"] = df["project_name"].fillna("Private")
blank_mask = df["project_name"].astype(str).str.strip().isin(["", "nan", "<NA>", "None"])
df.loc[blank_mask, "project_name"] = "Private"
df["norm_proj"] = norm(df["project_name"])

existing_indexes = set(master_index_map.values())
file_mapping = {}
new_nr_count = 0

for i in df.index:
    if pd.isna(df.at[i, "internal_index_id"]):
        p_name = df.at[i, "project_name"]
        l_name = df.at[i, "location_name"]
        p_norm = df.at[i, "norm_proj"]

        if pd.isna(l_name) or norm(l_name) in ["", "nan"]:
            l_name = "Unknown Location"

        # Shared composite key: [ project name + location ]
        # Both commercial AND 'Private' projects sharing same project name and location receive the EXACT SAME internal_index_id
        key = (norm(l_name), p_norm, norm(df.at[i, "city_name"]))
        if key in file_mapping:
            df.at[i, "internal_index_id"] = file_mapping[key]
        else:
            while f"nr{next_num}" in existing_indexes:
                next_num += 1
            new_index = f"nr{next_num}"
            df.at[i, "internal_index_id"] = new_index
            file_mapping[key] = new_index
            existing_indexes.add(new_index)
            next_num += 1
            new_nr_count += 1

# Enforce clean index format
df["internal_index_id"] = df["internal_index_id"].map(clean_nr_index)
total_with_internal_index = int(df["internal_index_id"].notna().sum())

print(f"[step11] New NR indexes assigned: {new_nr_count} distinct projects (ending at nr{next_num - 1})")
print(f"[step11] Total records with internal_index_id: {total_with_internal_index}/{len(df)} rows")
time.sleep(0.15)
print(f"[STEP:11:DONE] Assigned internal_index_id to all {total_with_internal_index:,}/{len(df):,} records ({new_nr_count} new NRs allocated from nr468 to nr{next_num - 1})")

# ============================== STEP 12: FINAL SCHEMA REORDER & TITLE CASE ==============================
print("[STEP:12:START] Aligning columns strictly to Abu Dhabi schema (project_id completely removed) and applying Title Case...")
time.sleep(0.35)
t_step = time.time()
final_schema_order = [
    "internal_index_id", "project_name", "location_id", "location_name",
    "registered_document_village_name", "agreement_price", "transaction_date",
    "net_carpet_area_sq_m", "sub_registrar_office_code", "sub_registrar_office_name",
    "document_number", "transaction_type", "city_id", "city_name",
    "guideline_value", "property_description", "floor_number", "unit_number",
    "property_type_raw", "property_type", "year", "balcony_sq_m", "terrace_sq_m",
    "seller_name", "buyer_name", "transaction_category", "internal_document_number",
    "micr_number", "bank_type", "party_code", "date_of_agreement_execution",
    "stamp_duty_paid", "registration_fee", "project_latitude", "project_longitude",
    "location_latitude", "location_longitude", "quarter", "unit_configuration",
    "property_layout", "buyer_pincode", "buyer_locality", "buyer_district",
    "buyer_state", "is_llm_processed", "is_manual_processed", "tower_name",
    "is_duplicate", "sale_type", "project_type", "country_name", "state_name",
    "micro_market", "sub_locality", "pincode", "parking_count", "facing_direction",
    "view_type", "furnishing_status", "condition_status", "source_accessibility",
    "source_accessibility_way", "sourcing_cost", "sourcing_time", "data_type",
    "data_source", "normalized_unit_configuration", "project_stage"
]

# Ensure project_id is purged from DataFrame
if "project_id" in df.columns:
    df = df.drop(columns=["project_id"])

# Ensure all schema columns exist
for col in final_schema_order:
    if col not in df.columns:
        df[col] = None

final_columns = [c for c in final_schema_order if c != "project_id"]
df = df[final_columns]

# Apply Title Case to all object/text columns EXCEPT 'internal_index_id'
for col in df.select_dtypes(include=["object", "string"]).columns:
    if col != "internal_index_id":
        df[col] = df[col].apply(lambda x: x.title() if isinstance(x, str) and x.lower() not in ["none", "nan", "<na>"] else x)

# Guarantee property_description and micro_market remain strictly blank (no mapping applied)
df["property_description"] = None
df["micro_market"] = None

print(f"[step12] Applied Title Case and organized {len(final_columns)} schema columns (project_id purged, property_description & micro_market blank)")
time.sleep(0.15)
print(f"[STEP:12:DONE] Formatted {len(final_columns)} schema columns with internal_index_id at position 0")

# ============================== STEP 13: SAVE OUTPUT & UPLOAD TO GOOGLE DRIVE ==============================
print("[STEP:13:START] Saving and uploading database-ready files (Excel & CSV) to Google Drive Processed Data folder...")
time.sleep(0.35)
t_step = time.time()

staging_csv = os.path.join(STAGING_DIR, f"{_raw_stem}_processed.csv")
staging_xlsx = os.path.join(STAGING_DIR, f"{_raw_stem}_processed.xlsx")

# Save CSV to temp staging
try:
    df.to_csv(staging_csv, index=False, encoding="utf-8-sig")
except Exception as e:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_csv = os.path.join(STAGING_DIR, f"{_raw_stem}_processed_{ts}.csv")
    df.to_csv(staging_csv, index=False, encoding="utf-8-sig")

# Save Excel to temp staging
try:
    df.to_excel(staging_xlsx, index=False)
except Exception as e:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_xlsx = os.path.join(STAGING_DIR, f"{_raw_stem}_processed_{ts}.xlsx")
    df.to_excel(staging_xlsx, index=False)

# Upload both files to Google Drive Processed Data folder
print(f"[Drive] Uploading final processed files to Google Drive Processed Data folder ({PROCESSED_FOLDER_ID})...")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import adrec_downloader

csv_drive_id = adrec_downloader.upload_file_to_google_drive(
    file_path=staging_csv,
    folder_id=PROCESSED_FOLDER_ID,
)

xlsx_drive_id = adrec_downloader.upload_file_to_google_drive(
    file_path=staging_xlsx,
    folder_id=PROCESSED_FOLDER_ID,
)

if csv_drive_id:
    print(f"✔ [Drive] Uploaded CSV to Processed Data: {os.path.basename(staging_csv)} (ID: {csv_drive_id})")
if xlsx_drive_id:
    print(f"✔ [Drive] Uploaded Excel to Processed Data: {os.path.basename(staging_xlsx)} (ID: {xlsx_drive_id})")

# Clean up temp staging directory so no local files remain
if IS_TEMP_STAGING and os.path.exists(STAGING_DIR):
    try:
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
        print("✔ [Local] Staging files cleaned up. No files saved locally.")
    except Exception as e:
        print(f"⚠️ [Local] Warning cleaning staging directory: {e}")

print(f"[STEP:13:DONE] Uploaded database-ready Excel & CSV to Google Drive Processed Data folder ({PROCESSED_FOLDER_ID})")

print("\n" + "=" * 75)
print(f"🎉 PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
print(f"   • Uploaded to Drive Processed Folder: {PROCESSED_FOLDER_ID}")
if xlsx_drive_id:
    print(f"   • Processed Excel File Drive ID    : {xlsx_drive_id}")
if csv_drive_id:
    print(f"   • Processed CSV File Drive ID      : {csv_drive_id}")
print(f"   • Total Records Processed          : {len(df):,}")
print(f"   • Total with internal_index_id     : {df['internal_index_id'].notna().sum():,}")
print(f"   • Private Records Processed        : {(df['project_name'].str.lower() == 'private').sum():,}")
print("=" * 75)
