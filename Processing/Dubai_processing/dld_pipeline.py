"""
End-to-end pipeline for the Dubai DLD monthly download — COMBINED SCRIPT.

This file merges two previously separate scripts into one, so it can be run
top to bottom in a single pass:

    PART 1 — Build the final output dataframe from the raw CSV
      1. Load raw CSV (dtype=str, utf-8-sig)
      1b. Drop duplicate transactions
      2. Parse INSTANCE_DATE -> year / quarter
      3. Map property_type_raw -> property_type
      4. Rename raw DLD columns to internal schema names
      4a. transaction_category mapping
      4b. normalized_unit_configuration mapping
      5. Add any missing required columns as blank
      6. Set static/default columns (city_name, country_name, etc.)
      7. Enrich from Postgres: pull project_latitude/longitude, location_latitude/
         longitude, and internal_index_id from dim_project / dim_location,
         matched on project_name / location_name (scoped to CITY_ID).
         NOTE: 'index' is only pulled in when BOTH project_name AND
         location_name matched on the same row -- dim_project has no
         location field, so a project-only match could otherwise reuse an
         index that isn't really tied to that location. Coordinates and
         *_id fields still fill independently from their own match.
         A blank/NaN project_name (or location_name) is also force-blanked
         regardless of any stale value already in the file.
      8. Title-case all text columns (final cosmetic step)
      9. Reorder/rename columns to match the target DB schema exactly
      9b. Clean internal_index_id (strip any trailing "__something" suffix,
          e.g. "__dubai", "__pune") and rename it to 'index'
      10. Save final .csv (df_final)

    PART 2 — Assign Non-RERA (NR) index & Coordinates from DB Transactions, then Highest NR
      0. Interactive input file selection (choose from available scraped CSV files or custom path)
      1. Calculate starting NR sequence number (MAX(nr) from public.transactions + 1)
      2. DB lookup from public.transactions for (location, project, city) -> internal_index_id & coordinates
      3. Existing project + location + city -> index and coordinates mapping (from df itself)
      4. Assign NR index:
         - Reuse matching index from current file
         - Reuse matching index from DB transactions lookup (project + location match)
         - If unmatched, assign sequential new index after highest NR (nr{next_num})
      5. Get project coordinates:
         - Populate project_latitude and project_longitude from matching transactions records
         - Unify in-file project coordinates across same project + location
      6. Convert numeric indexes: 1001.0 -> 1001, keep nrXXXX unchanged
      6b. Final safety pass: blank index/coordinates if project_name is blank
      7. Verification / logging
      8. Location coordinate fallback (STEP C) & Google Places Geocoding (STEP D)
      9. Save to processed Excel (.xlsx)

Run top to bottom as a script. All configurable paths/values are in the
CONFIG section below.

-----------------------------------------------------------------------------
FIXES APPLIED IN THIS VERSION (vs the earlier combined draft):
  1. Removed TARGET_CITY_ID entirely -- it was never defined in CONFIG and
     was only referenced later in STEP B, which would have raised a
     NameError. Both STEP B call sites now use CITY_ID (the single city-id
     variable used consistently everywhere else in the script).
  2. Added TEST_MERGE_PATH to CONFIG -- it was referenced in STEP A
     (df.to_excel(TEST_MERGE_PATH, ...)) but never defined -> NameError.
  3. Replaced the undefined OUTPUT_FILE_PATH in the final save step with the
     already-defined FINAL_OUTPUT_PATH from CONFIG -- these were two
     different names for what should be the same path.
  4. Removed the stray "internal_index_id" column reference in the second
     "Safety again" blanking block. By that point in the script the column
     had already been renamed to "index" (per STEP 9b in the docstring), so
     df["internal_index_id"] does not exist -> KeyError. The block now only
     blanks ["index", "project_latitude", "project_longitude"].
-----------------------------------------------------------------------------
"""

import os, re, sys
from datetime import datetime
import numpy as np
import pandas as pd
import psycopg2
from sqlalchemy import create_engine

# Windows console UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if any(h in sys.argv for h in ["-h", "--help"]):
    print("""
Usage: python dld_pipeline.py [OPTIONS]

Dubai Land Department (DLD) Transaction Data Processing Pipeline.

Options:
  --input, --input-file <PATH>   Specify custom raw CSV input file path.
  --auto-confirm, -y             Automatically confirm the latest detected input file.
  --non-interactive              Run in non-interactive mode without terminal prompts.
  -h, --help                     Show this help message and exit.
""")
    sys.exit(0)

# ============================== CONFIG & DYNAMIC DRIVE PATH RESOLUTION ==============================
DUBAI_PARENT_DRIVE_URL = "https://drive.google.com/drive/folders/1q-rgFMUS5gyZq9ngoIozgzDwb-cSguim?usp=drive_link"
PARENT_FOLDER_ID = "1q-rgFMUS5gyZq9ngoIozgzDwb-cSguim"

def resolve_dubai_drive_paths(folder_id: str = PARENT_FOLDER_ID):
    """
    Locates the input '1. Download Files(Row)' and output '2.Processed Files'
    directories from Google Drive Desktop on G:.
    """
    input_dir = None
    output_dir = None

    # 1. Primary: Check G:\.shortcut-targets-by-id\<parent_folder_id>
    parent_shortcut = os.path.join(r"G:\.shortcut-targets-by-id", folder_id)
    candidates = [parent_shortcut]
    if os.path.exists(parent_shortcut):
        try:
            for sub in os.listdir(parent_shortcut):
                sub_path = os.path.join(parent_shortcut, sub)
                if os.path.isdir(sub_path):
                    candidates.append(sub_path)
        except Exception:
            pass

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            for item in os.listdir(candidate):
                item_path = os.path.join(candidate, item)
                if not os.path.isdir(item_path):
                    continue
                item_lower = item.lower()
                if "download" in item_lower or "row" in item_lower:
                    input_dir = item_path
                elif "processed" in item_lower:
                    output_dir = item_path
        except Exception:
            pass

    # 2. Secondary: Fallback to direct shortcut folder IDs if not found above
    if not input_dir:
        direct_input = os.path.join(r"G:\.shortcut-targets-by-id", "1CyL3ecimjHLcpUv2AfP8d6fJXNbOcVVE", "1. Download Files(Row)")
        if os.path.exists(direct_input):
            input_dir = direct_input

    if not output_dir:
        direct_output = os.path.join(r"G:\.shortcut-targets-by-id", "1TvDEGGW5dahnxRO4JfxJ8TUinK3DKXO8", "2.Processed Files")
        if os.path.exists(direct_output):
            output_dir = direct_output
            
    if not output_dir:
        output_dir = input_dir

    return input_dir, output_dir


def get_available_csv_files(input_dir: str) -> list[str]:
    """
    Scans both the Google Drive input directory and the local 'downloads'
    fallback directory for available CSV files, sorted newest first.
    """
    search_dirs = []
    if input_dir and os.path.exists(input_dir):
        search_dirs.append(input_dir)

    local_dl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    if os.path.exists(local_dl) and local_dl not in search_dirs:
        search_dirs.append(local_dl)

    seen_files = set()
    csv_files = []
    for d in search_dirs:
        try:
            for f in os.listdir(d):
                if (
                    f.lower().endswith(".csv")
                    and not f.startswith(".")
                    and not f.endswith(".tmp")
                    and not f.endswith(".crdownload")
                    and f.lower() != "desktop.ini"
                ):
                    full_p = os.path.join(d, f)
                    if os.path.isfile(full_p) and f.lower() not in seen_files:
                        seen_files.add(f.lower())
                        csv_files.append(full_p)
        except Exception:
            pass

    csv_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return csv_files


def select_input_file(input_dir: str, explicit_file: str = None) -> str:
    """
    Provides an interactive menu for the user to choose which scraped CSV file to process,
    with the newest scraped file as default. Supports custom file path entry and non-interactive flags.
    """
    all_csvs = get_available_csv_files(input_dir)

    if explicit_file:
        if str(explicit_file).lower().endswith(".gsheet"):
            stem = os.path.splitext(os.path.basename(explicit_file))[0]
            stem = re.sub(r"\s*\(\d+\)$", "", stem)
            matched_real = None
            for f in all_csvs:
                if stem.lower() in os.path.basename(f).lower():
                    matched_real = f
                    break
            if matched_real:
                print(f"\n⚠️ Notice: '{os.path.basename(explicit_file)}' is a Google Sheet cloud shortcut.")
                print(f"✔ Automatically redirected to actual CSV data file: {os.path.basename(matched_real)}")
                print(f"   Full Path: {matched_real}\n")
                return matched_real
            raise ValueError(f"'{os.path.basename(explicit_file)}' is a Google Sheet cloud pointer (*.gsheet). Please select a valid CSV (*.csv) or Excel (*.xlsx) file.")

        if os.path.isfile(explicit_file):
            print(f"\n✔ Using explicitly specified input file: {os.path.basename(explicit_file)}")
            print(f"   Full Path: {explicit_file}\n")
            return explicit_file
        for f in all_csvs:
            if os.path.basename(f).lower() == os.path.basename(explicit_file).lower() or os.path.basename(f).lower() == explicit_file.strip().lower():
                print(f"\n✔ Matched explicitly specified input file: {os.path.basename(f)}")
                print(f"   Full Path: {f}\n")
                return f
    if not all_csvs:
        raise FileNotFoundError(f"No valid CSV files found in '{input_dir}' or local downloads.")

    latest_file = all_csvs[0]

    # Non-interactive / headless auto-confirm
    if "--auto-confirm" in sys.argv or "--non-interactive" in sys.argv or not sys.stdin.isatty():
        print("\n" + "=" * 75)
        print(f"📄 AUTO-CONFIRMED LATEST INPUT FILE:")
        print(f"   • File Name : {os.path.basename(latest_file)}")
        print(f"   • Full Path : {latest_file}")
        print("=" * 75 + "\n")
        return latest_file

    # Interactive Menu
    print("\n" + "=" * 75)
    print("📋 AVAILABLE DUBAI SCRAPED CSV FILES:")
    print("=" * 75)
    for idx, filepath in enumerate(all_csvs, 1):
        mtime_str = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%d/%m/%Y %H:%M")
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        tag = "  [Latest Scraped]" if idx == 1 else ""
        print(f"   [{idx}] {os.path.basename(filepath)}  (Modified: {mtime_str}, {size_mb:.1f} MB){tag}")
    print(f"   [0] Enter a custom file path")
    print("=" * 75)

    while True:
        sel = input(f"\n👉 Select file number to process [1-{len(all_csvs)}] or [0] [Default: 1]: ").strip()
        if not sel or sel == "1":
            chosen = all_csvs[0]
            print(f"   ✔ Selected input file: {os.path.basename(chosen)}\n")
            return chosen
        if sel.isdigit():
            val = int(sel)
            if 1 <= val <= len(all_csvs):
                chosen = all_csvs[val - 1]
                print(f"   ✔ Selected input file: {os.path.basename(chosen)}\n")
                return chosen
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
            print(f"   ❌ Invalid selection! Please enter 1 to {len(all_csvs)}, 0, or press Enter for default.")


# Resolve paths automatically from Google Drive
INPUT_DIR, OUTPUT_DIR = resolve_dubai_drive_paths(PARENT_FOLDER_ID)
_detected_csv = None
for _idx, _arg in enumerate(sys.argv):
    if _arg in ["--input", "--input-file"] and _idx + 1 < len(sys.argv):
        if os.path.exists(sys.argv[_idx + 1]):
            _detected_csv = sys.argv[_idx + 1]
            break

RAW_CSV_PATH = select_input_file(INPUT_DIR, _detected_csv)

# Generate output paths: same filename as input, with '_processed.xlsx' and '_test_merge.xlsx'
_raw_basename = os.path.basename(RAW_CSV_PATH)
_raw_stem, _ = os.path.splitext(_raw_basename)
FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"{_raw_stem}_processed.xlsx")
TEST_MERGE_PATH = os.path.join(OUTPUT_DIR, f"{_raw_stem}_test_merge.xlsx")

# Database Configuration & Runtime City ID
CITY_NAME = "Dubai"

cli_db = "nilesh"
for i, arg in enumerate(sys.argv):
    if arg in ["--db", "-d"] and i + 1 < len(sys.argv):
        cli_db = sys.argv[i + 1].strip()

db_params = {
    "host": "localhost", "port": "5432", "database": cli_db,
    "user": "postgres", "password": "nilesh"
}

def get_runtime_city_id(city_name: str = "Dubai", params: dict = None) -> int:
    try:
        with psycopg2.connect(**(params or db_params), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT city_id FROM public.dim_city WHERE lower(city_name) = lower(%s) LIMIT 1;", (city_name,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception:
        pass
    return 15

CITY_ID = get_runtime_city_id(CITY_NAME, db_params)

print("=" * 75)
print(f"📁 DUBAI DATA PROCESSING PIPELINE")
print(f"   • Raw Input Dir  : {INPUT_DIR}")
print(f"   • Latest CSV File: {RAW_CSV_PATH}")
print(f"   • Output Dir     : {OUTPUT_DIR}")
print(f"   • Final Excel    : {FINAL_OUTPUT_PATH}")
print(f"   • Runtime City ID: {CITY_ID} ({CITY_NAME})")
print("=" * 75)

# ============================== STEP 1: LOAD ==============================
if not os.path.exists(RAW_CSV_PATH):
    raise FileNotFoundError(f"'{RAW_CSV_PATH}' does not exist.")

df = pd.read_csv(RAW_CSV_PATH, dtype=str, encoding="utf-8-sig")
df.columns = df.columns.str.strip()
print(f"[step1] loaded raw file: {df.shape}")
print("[step1] raw columns:", list(df.columns))

# ============================== STEP 1b: DEDUP ==============================
dedup_columns = [
    "TRANSACTION_NUMBER", "INSTANCE_DATE", "GROUP_EN", "PROCEDURE_EN",
    "IS_OFFPLAN_EN", "IS_FREE_HOLD_EN", "USAGE_EN", "AREA_EN", "PROP_TYPE_EN",
    "PROP_SB_TYPE_EN", "TRANS_VALUE", "PROCEDURE_AREA", "ACTUAL_AREA", "ROOMS_EN",
    "PARKING", "NEAREST_METRO_EN", "NEAREST_MALL_EN", "NEAREST_LANDMARK_EN",
    "TOTAL_BUYER", "TOTAL_SELLER", "MASTER_PROJECT_EN", "PROJECT_EN"
]
missing = [c for c in dedup_columns if c not in df.columns]
if missing:
    raise KeyError(f"Missing raw dedup columns: {missing}")
before = len(df)
df = df.drop_duplicates(subset=dedup_columns, keep="first").reset_index(drop=True)
print(f"[step1b] before={before}, after={len(df)}, removed={before-len(df)}")

# ============================== STEP 2: DATE ==============================
# Robust multi-format parsing covering ISO (%Y-%m-%d %H:%M:%S), European (%d-%m-%Y %H:%M), and slash formats
_date_series = pd.to_datetime(df["INSTANCE_DATE"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
for _fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"]:
    if _date_series.isna().any():
        _date_series = _date_series.fillna(pd.to_datetime(df["INSTANCE_DATE"], format=_fmt, errors="coerce"))
if _date_series.isna().any():
    _date_series = _date_series.fillna(pd.to_datetime(df["INSTANCE_DATE"], dayfirst=True, errors="coerce"))
df["INSTANCE_DATE"] = _date_series
df["year"] = df["INSTANCE_DATE"].dt.year.astype("Int64")
df["quarter"] = "Q" + df["INSTANCE_DATE"].dt.quarter.astype("Int64").astype(str) + "-" + df["year"].astype(str)
df.loc[df["INSTANCE_DATE"].isna(), "quarter"] = None
print(f"[step2] unparseable dates: {df['INSTANCE_DATE'].isna().sum()}")

# ============================== STEP 3: PROPERTY TYPE ==============================
property_type_mapping = {
    "Agricultural":"Plot", "Airport":"Others", "Building":"Others", "Commercial":"Others",
    "Commercial / Offices / Residential":"Others", "Exhbition Center":"Others", "Flat":"Flat",
    "General Use":"Others", "Government Housing":"Flat", "Health Club":"Others", "Hospital":"Others",
    "Hotel":"Others", "Hotel Apartment":"Flat", "Hotel Rooms":"Others", "Industrial":"Others",
    "Labor Camp":"Others", "Land":"Plot", "Office":"Office", "Petrol Station":"Others",
    "Residential":"Flat", "Residential / Attached Villas":"Villa",
    "Residential / Residential Villa":"Villa", "Residential / Villas":"Villa",
    "Residential Flats":"Flat", "School":"Others", "Shop":"Shop", "Shopping Mall":"Shop",
    "Show Rooms":"Shop", "Sports Club":"Others", "Stacked Townhouses":"Villa", "Unit":"Others",
    "Villa":"Villa", "Warehouse":"Others", "Workshop":"Others"
}
df.rename(columns={"PROP_SB_TYPE_EN":"property_type_raw"}, inplace=True)
df["property_type_raw"] = df["property_type_raw"].fillna("").astype(str).str.strip()
df["property_type"] = df["property_type_raw"].map(property_type_mapping).fillna("Others")
print("[step3] property_type counts:\n", df["property_type"].value_counts())
print("[step3] unmapped:", sorted(set(df["property_type_raw"]) - set(property_type_mapping) - {""}))

# ============================== STEP 4: RENAME ==============================
mapping = {
    "TRANSACTION_NUMBER":"document_number", "INSTANCE_DATE":"transaction_date",
    "GROUP_EN":"transaction_category", "PROCEDURE_EN":"transaction_type",
    "TRANS_VALUE":"agreement_price", "PROCEDURE_AREA":"net_carpet_area_sq_m",
    "ACTUAL_AREA":"gross_carpet_area_sq_ft", "AREA_EN":"location_name",
    "PROJECT_EN":"project_name", "MASTER_PROJECT_EN":"tower_name",
    "PROP_SB_TYPE_EN":"property_type_raw", "PROP_TYPE_EN":"property_type_en",
    "USAGE_EN":"project_type", "ROOMS_EN":"unit_configuration", "PARKING":"parking_count",
    "IS_OFFPLAN_EN":"project_stage", "IS_FREE_HOLD_EN":"free_hold",
    "NEAREST_METRO_EN":"nearest_metro_en", "NEAREST_MALL_EN":"nearest_mall_en",
    "NEAREST_LANDMARK_EN":"nearest_landmark_en", "TOTAL_BUYER":"total_buyer",
    "TOTAL_SELLER":"total_seller", "project_latitude":"project_latitude",
    "project_longitude":"project_longitude", "location_latitude":"location_latitude",
    "location_longitude":"location_longitude"
}
df.rename(columns=mapping, inplace=True)
print("[step4] mapped columns:", [c for c in mapping.values() if c in df.columns])

# ============================== STEP 4a: CATEGORY ==============================
transaction_category_mapping = {"Mortgage":"Mortgages", "Sales":"Sale", "Gifts":"Gifts"}
df["transaction_category"] = df["transaction_category"].fillna("").astype(str).str.strip().replace(transaction_category_mapping)
print("[step4a] transaction_category counts:\n", df["transaction_category"].value_counts())

# ============================== STEP 4b: UNIT CONFIG ==============================
normalized_unit_configuration_mapping = {
    "1 B/R":"1Bhk", "2 B/R":"2Bhk", "3 B/R":"3Bhk", "4 B/R":">3Bhk",
    "5 B/R":">3Bhk", "6 B/R":">3Bhk", "7 B/R":">3Bhk", "8 B/R":">3Bhk",
    "9 B/R":">3Bhk", "10 B/R":">3Bhk", "Gym":"Others", "Hotel":"Others",
    "Office":"Office", "Penthouse":"Others", "Shop":"Shop", "Single Room":"Flat",
    "Store":"Others", "Studio":"Flat"
}
df["unit_configuration"] = df["unit_configuration"].fillna("").astype(str).str.strip()
df["normalized_unit_configuration"] = df["unit_configuration"].map(normalized_unit_configuration_mapping).fillna("Others")
print("[step4b] normalized counts:\n", df["normalized_unit_configuration"].value_counts())
print("[step4b] unmapped:", sorted(set(df["unit_configuration"]) - set(normalized_unit_configuration_mapping) - {""}))

# ============================== STEP 5: REQUIRED COLUMNS ==============================
required_columns = [
    "project_id", "index", "project_name", "village_name_marathi", "location_id", "location_name",
    "registered_document_village_name", "year", "quarter", "city_id", "city_name", "document_number",
    "sub_registrar_office_code", "sub_registrar_office_name", "transaction_type", "agreement_price",
    "guideline_value", "property_description", "transaction_date", "floor_number", "unit_number",
    "net_carpet_area_sq_m", "balcony_sq_m", "terrace_sq_m", "seller_name", "buyer_name",
    "transaction_category", "project_latitude", "project_longitude", "location_latitude",
    "location_longitude", "property_type_raw", "property_type", "unit_configuration", "tower_name",
    "project_type", "sale_type", "free_hold", "nearest_metro_en", "nearest_mall_en",
    "nearest_landmark_en", "total_buyer", "total_seller", "country_name", "state_name", "micro_market",
    "sub_locality", "pincode", "parking_count", "facing_direction", "view_type", "furnishing_status",
    "condition_status", "source_accessibility", "source_accessibility_way", "sourcing_cost", "sourcing_time",
    "data_type", "data_source", "is_llm_processed", "is_manual_processed"
]
added = []
for c in required_columns:
    if c not in df.columns:
        df[c] = None; added.append(c)
print(f"[step5] added blank columns ({len(added)}): {added}")

# ============================== STEP 6: DEFAULTS ==============================
df["city_name"], df["state_name"], df["country_name"] = "Dubai", "Dubai", "United Arab Emirates"
df["is_llm_processed"], df["is_manual_processed"] = "No", "No"
df["source_accessibility"], df["source_accessibility_way"] = "Easy", "Download"
df["data_type"], df["data_source"] = "Registered Document", "Dld"

# ============================== HELPERS ==============================
def norm(s):
    s = s.astype("string").str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    return s.mask(s == "", pd.NA)

def strip_any_suffix(x):
    return x if pd.isna(x) else re.sub(r"__.*$", "", str(x).strip())

def strip_nr_suffix(x):
    if pd.isna(x): return x
    x = str(x).strip()
    m = re.match(r"(?i)^nr[\s_-]*(\d+)", x)
    return f"Nr{m.group(1)}" if m else x

def clean_index(x):
    if pd.isna(x): return None
    x = str(x).strip()
    x = re.sub(r"__.*$", "", x)
    x = re.sub(r"_dubai$", "", x, flags=re.IGNORECASE)
    m = re.match(r"(?i)^nr[\s_-]*(\d+)", x)
    if m:
        return f"Nr{m.group(1)}"
    try:
        n = float(x); return int(n) if n.is_integer() else x
    except ValueError:
        return x

def make_key(location, project, city):
    return tuple(str(v).strip().lower() for v in (location, project, city))

def is_blank(s):
    return s.isna() | (s.astype("string").str.strip() == "")

# ============================== CLEAN INDEX ==============================
df["index"] = df["index"].astype("string").map(strip_any_suffix)
blank_project = is_blank(df["project_name"])
df.loc[blank_project, ["index", "project_latitude", "project_longitude"]] = pd.NA
print(f"[safety] blank project rows: {blank_project.sum()}")

# ============================== STEP A: PROJECT + LOCATION MATCH ==============================
engine = create_engine(
    f"postgresql+psycopg2://{db_params['user']}:{db_params['password']}@"
    f"{db_params['host']}:{db_params['port']}/{db_params['database']}"
)
if CITY_NAME is not None:
    df = df[(norm(df["city_name"]) == CITY_NAME.strip().lower()).fillna(False)].copy()
print(f"[stepA] after city filter: {df.shape}")

sql = """
SELECT dp.project_name, dp.internal_index_id, dp.project_latitude, dp.project_longitude,
       dp.city_id, dp.location_id, dl.location_name, dl.location_latitude, dl.location_longitude
FROM public.dim_project dp
LEFT JOIN public.dim_location dl
  ON dp.location_id = dl.location_id AND dp.city_id = dl.city_id
WHERE dp.city_id = %(city_id)s;
"""
lookup = pd.read_sql(sql, engine, params={"city_id": CITY_ID})
print(f"[stepA] DB rows: {len(lookup)}")
lookup["_project_key"], lookup["_location_key"] = norm(lookup["project_name"]), norm(lookup["location_name"])
lookup = lookup.drop_duplicates(["_project_key", "_location_key"], keep="last").rename(columns={
    "internal_index_id":"_db_index", "project_latitude":"_db_project_latitude",
    "project_longitude":"_db_project_longitude", "city_id":"_db_city_id",
    "location_id":"_db_location_id", "location_latitude":"_db_location_latitude",
    "location_longitude":"_db_location_longitude"
})
df["_project_key"], df["_location_key"] = norm(df["project_name"]), norm(df["location_name"])
tmp_cols = [
    "_project_key", "_location_key", "_db_index", "_db_project_latitude", "_db_project_longitude",
    "_db_city_id", "_db_location_id", "_db_location_latitude", "_db_location_longitude"
]
df = df.merge(lookup[tmp_cols], how="left", on=["_project_key", "_location_key"], validate="m:1")

# Preserve the configured Dubai city_id even for new/unmatched projects.
df["city_id"] = pd.to_numeric(df["_db_city_id"], errors="coerce").fillna(CITY_ID).astype("Int64")
df["location_id"] = df["_db_location_id"]
print("[stepA] project+location matched:", df["_db_location_id"].notna().sum())

for col, db_col in {
    "index":"_db_index", "project_latitude":"_db_project_latitude",
    "project_longitude":"_db_project_longitude", "location_latitude":"_db_location_latitude",
    "location_longitude":"_db_location_longitude"
}.items():
    blank = is_blank(df[col])
    df.loc[blank, col] = df.loc[blank, db_col]

blank_project = is_blank(df["project_name"])
df.loc[blank_project, ["index", "project_latitude", "project_longitude"]] = pd.NA

df.to_excel(TEST_MERGE_PATH, index=False)
print("[stepA] test_merge saved")
df.drop(columns=tmp_cols, inplace=True)
print("[stepA] missing index:", df["index"].isna().sum())
engine.dispose()

# ============================== STEP B: MAX NR ==============================
def get_max_nr_number(params, city_id):
    with psycopg2.connect(**params) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX((regexp_match(internal_index_id, '^nr(\\d+)', 'i'))[1]::int)
                FROM public.transactions
                WHERE internal_index_id ~* '^nr\\d+' AND city_id = %s;
            """, (city_id,))
            return cur.fetchone()[0] or 0

max_nr = get_max_nr_number(db_params, CITY_ID)
next_num = max_nr + 1
print(f"[stepB] DB max = nr{max_nr}, new index starts = nr{next_num}")

# ============================== STEP B: DB TRANSACTIONS PROJECT+LOCATION MAP (INDEX & COORDS) ==============================
def get_db_mapping(params, city_id):
    """
    Fetches (lower(location), lower(project), lower(city)) -> internal_index_id
    and coordinates (project_latitude, project_longitude) from public.transactions for the target city.
    """
    with psycopg2.connect(**params) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lower(trim(location_name)), lower(trim(project_name)), lower(trim(city_name)), 
                       internal_index_id, project_latitude, project_longitude
                FROM public.transactions
                WHERE city_id = %s
                  AND project_name IS NOT NULL AND location_name IS NOT NULL AND city_name IS NOT NULL
                  AND (internal_index_id IS NOT NULL OR project_latitude IS NOT NULL);
            """, (city_id,))
            rows = cur.fetchall()

    index_map = {}
    coords_map = {}
    for location, project, city, idx, lat, lon in rows:
        key = make_key(location, project, city)
        if idx is not None and key not in index_map:
            c_idx = clean_index(idx)
            if c_idx is not None:
                index_map[key] = c_idx
        if key not in coords_map:
            try:
                plat = None if (lat is None or pd.isna(lat)) else float(lat)
                plon = None if (lon is None or pd.isna(lon)) else float(lon)
                if plat is not None and plon is not None:
                    coords_map[key] = (plat, plon)
            except (ValueError, TypeError):
                pass
    return index_map, coords_map

db_index_mapping, db_coords_mapping = get_db_mapping(db_params, CITY_ID)
print(f"[stepB] DB mappings loaded: {len(db_index_mapping)} index mappings, {len(db_coords_mapping)} coordinate pairs")

# ============================== CLEAN BLANKS ==============================
cols = ["index", "project_name", "location_name", "city_name"]
df[cols] = df[cols].replace(r"^\s*$", np.nan, regex=True)
df["index"] = df["index"].astype("string").map(strip_nr_suffix)
df["project_latitude"] = pd.to_numeric(df["project_latitude"], errors="coerce")
df["project_longitude"] = pd.to_numeric(df["project_longitude"], errors="coerce")

# ============================== CURRENT FILE MAP ==============================
file_index_mapping = {}
file_coords_mapping = {}

for _, row in df.dropna(subset=["location_name", "project_name", "city_name"]).iterrows():
    key = make_key(row["location_name"], row["project_name"], row["city_name"])
    if pd.notna(row.get("index")) and str(row["index"]).strip():
        file_index_mapping.setdefault(key, clean_index(row["index"]))
    plat_val = row.get("project_latitude")
    plon_val = row.get("project_longitude")
    if pd.notna(plat_val) and pd.notna(plon_val):
        try:
            plat, plon = float(plat_val), float(plon_val)
            file_coords_mapping.setdefault(key, (plat, plon))
        except (ValueError, TypeError):
            pass

existing_indexes = set(df["index"].dropna().astype("string").str.strip().str.lower())

# ============================== STEP 2: ASSIGN INDEX FROM TRANSACTIONS & HIGHEST NR ==============================
new_count = 0
reused_from_file = 0
reused_from_db = 0

for i in df.index[df["index"].isna()]:
    project, location, city = df.at[i, "project_name"], df.at[i, "location_name"], df.at[i, "city_name"]
    if pd.isna(project) or pd.isna(location) or pd.isna(city):
        continue
    key = make_key(location, project, city)

    # 1. Match from current file
    if key in file_index_mapping:
        df.at[i, "index"] = file_index_mapping[key]
        reused_from_file += 1
    # 2. Match from transactions table lookup (project + location match)
    elif key in db_index_mapping:
        idx = db_index_mapping[key]
        df.at[i, "index"] = idx
        file_index_mapping[key] = idx
        existing_indexes.add(str(idx).strip().lower())
        reused_from_db += 1
    # 3. Then assign index after highest nr
    else:
        while f"Nr{next_num}" in existing_indexes or f"nr{next_num}" in existing_indexes:
            next_num += 1
        new_index = f"Nr{next_num}"
        df.at[i, "index"] = new_index
        file_index_mapping[key] = db_index_mapping[key] = new_index
        existing_indexes.add(new_index)
        next_num += 1
        new_count += 1

# ============================== STEP 2 (cont): GET CO-ORDINATES FOR MATCH RECORDS ==============================
coords_filled_from_db = 0
coords_filled_from_file = 0

for i in df.index:
    project, location, city = df.at[i, "project_name"], df.at[i, "location_name"], df.at[i, "city_name"]
    if pd.isna(project) or pd.isna(location) or pd.isna(city):
        continue
    key = make_key(location, project, city)

    lat_blank = pd.isna(df.at[i, "project_latitude"])
    lon_blank = pd.isna(df.at[i, "project_longitude"])

    if lat_blank or lon_blank:
        # Check coordinates from transaction table lookup (project + location match)
        if key in db_coords_mapping:
            db_lat, db_lon = db_coords_mapping[key]
            if lat_blank and db_lat is not None:
                df.at[i, "project_latitude"] = db_lat
            if lon_blank and db_lon is not None:
                df.at[i, "project_longitude"] = db_lon
            coords_filled_from_db += 1
            file_coords_mapping.setdefault(key, (db_lat, db_lon))
        # Check in-file coordinates (unify coordinates across same project+location in file)
        elif key in file_coords_mapping:
            f_lat, f_lon = file_coords_mapping[key]
            if lat_blank and f_lat is not None:
                df.at[i, "project_latitude"] = f_lat
            if lon_blank and f_lon is not None:
                df.at[i, "project_longitude"] = f_lon
            coords_filled_from_file += 1

# ============================== FINAL INDEX CLEANING & SAFETY ==============================
df["index"] = df["index"].astype(object).map(clean_index)
df["index"] = df["index"].map(lambda x: strip_nr_suffix(x) if isinstance(x, str) else x)

blank_project = is_blank(df["project_name"])
df.loc[blank_project, ["index", "project_latitude", "project_longitude"]] = pd.NA

print(f"[stepB] Index reused from file: {reused_from_file}")
print(f"[stepB] Index matched & reused from DB transactions: {reused_from_db}")
print(f"[stepB] Brand new NR assigned: {new_count}")
if new_count:
    print(f"[stepB] Sequence start: nr{max_nr + 1} -> Highest new NR: nr{next_num - 1}")
print(f"[stepB] Project coords filled from DB transactions: {coords_filled_from_db}")
print(f"[stepB] Project coords unified across in-file rows: {coords_filled_from_file}")
print("[stepB] remaining null index:", df["index"].isna().sum())
print("[stepB] remaining blank project_latitude:", df["project_latitude"].isna().sum())
print("[stepB] remaining blank project_longitude:", df["project_longitude"].isna().sum())
nr_numbers = df["index"].astype("string").str.extract(r"(?i)^nr(\d+)$")[0].dropna().astype(int)
if not nr_numbers.empty:
    print("[stepB] highest nr in final file:", f"nr{nr_numbers.max()}")

# ============================== STEP C: LOCATION COORD FALLBACK ==============================
engine = create_engine(
    f"postgresql+psycopg2://{db_params['user']}:{db_params['password']}@"
    f"{db_params['host']}:{db_params['port']}/{db_params['database']}"
)
loc_sql = """
SELECT location_name, location_latitude, location_longitude
FROM public.dim_location
WHERE city_id = %(city_id)s AND location_name IS NOT NULL;
"""
dim_location_lookup = pd.read_sql(loc_sql, engine, params={"city_id": CITY_ID})
engine.dispose()
print(f"[stepC] dim_location rows loaded: {len(dim_location_lookup)}")

dim_location_lookup["_loc_key"] = norm(dim_location_lookup["location_name"])
dim_location_lookup = dim_location_lookup.drop_duplicates("_loc_key", keep="last")
loc_coord_map = {
    row["_loc_key"]:(row["location_latitude"], row["location_longitude"])
    for _, row in dim_location_lookup.iterrows() if pd.notna(row["_loc_key"])
}
df["location_latitude"] = pd.to_numeric(df["location_latitude"], errors="coerce")
df["location_longitude"] = pd.to_numeric(df["location_longitude"], errors="coerce")
needs_fill = (df["location_latitude"].isna() | df["location_longitude"].isna()) & ~is_blank(df["location_name"])
print(f"[stepC] rows needing location coord fallback: {needs_fill.sum()}")

filled_count = 0
for i in df.index[needs_fill]:
    loc_key = re.sub(r"\s+", " ", str(df.at[i,"location_name"]).strip().lower())
    if loc_key not in loc_coord_map:
        continue
    db_lat, db_lon = loc_coord_map[loc_key]
    changed = False
    if pd.isna(df.at[i,"location_latitude"]) and pd.notna(db_lat):
        df.at[i,"location_latitude"] = db_lat; changed = True
    if pd.isna(df.at[i,"location_longitude"]) and pd.notna(db_lon):
        df.at[i,"location_longitude"] = db_lon; changed = True
    filled_count += int(changed)

print(f"[stepC] location coords filled from dim_location: {filled_count}")
print("[stepC] remaining blank location_latitude:", df["location_latitude"].isna().sum())
print("[stepC] remaining blank location_longitude:", df["location_longitude"].isna().sum())

# ============================== COLUMN ORDER ==============================
# =========================================================
# FINAL COLUMN ORDER + TITLE CASE + SAVE
# =========================================================
column_order = [
    "index","project_name",
    "village_name_marathi","location_id","location_name",
    "registered_document_village_name","year","quarter","city_id","city_name",
    "sub_registrar_office_code",
    "sub_registrar_office_name","document_number","transaction_type",
    "agreement_price","guideline_value","property_description","transaction_date",
    "floor_number","unit_number","property_type_raw","net_carpet_area_sq_m",
    "balcony_sq_m","terrace_sq_m","seller_name","buyer_name",
    "transaction_category","internal_document_number","micr_number","bank_type",
    "party_code","date_of_agreement_execution","stamp_duty_paid",
    "registration_fee","project_latitude","project_longitude",
    "location_latitude","location_longitude","property_type","unit_configuration",
    "buyer_pincode","buyer_locality","buyer_district","buyer_state",
    "is_llm_processed","is_manual_processed","tower_name","is_duplicate",
    "sale_type","project_type","country_name","state_name","micro_market",
    "sub_locality","pincode","parking_count","facing_direction","view_type",
    "furnishing_status","condition_status","source_accessibility",
    "source_accessibility_way","sourcing_cost","sourcing_time","data_type",
    "data_source","normalized_unit_configuration","project_stage"
]

# ============================== FINAL SCHEMA REORDER & SAVE ==============================
# Ensure all column_order columns are present
for col in column_order:
    if col not in df.columns:
        df[col] = None

# column_order first, rest of columns kept at the last
final_columns = column_order + [c for c in df.columns if c not in column_order]
df = df[final_columns]


# =============================================================================
# FINAL TITLE CASE
# =============================================================================

for col in df.select_dtypes(include=["object", "string"]).columns:
    df[col] = df[col].apply(
        lambda x: x.title() if isinstance(x, str) else x
    )
# =============================================================================
# STEP D: FILL PROJECT COORDINATES USING GOOGLE PLACES API
# =============================================================================
import time
import requests

GOOGLE_MAPS_API_KEY = "AIzaSyBS63yAQTYMnYAKDv5gQ7G1Qw2ngup15-w"

skip_geocoding = any(arg in sys.argv for arg in ["--skip-geocoding", "--no-geocoding"])

if skip_geocoding:
    print("[stepD] Google Places geocoding skipped via CLI flag (--skip-geocoding).")
else:
    print(f"\n{'=' * 60}")
    print("📍 [stepD] Enriching Project Coordinates via Google Places API...")
    print(f"{'=' * 60}")

    def build_query(row):
        """
        Build the Google Places search query using project_name for ALL cities
        (including Dubai). location_name and city_name are added as context only.
        """
        city = str(row.get("city_name", "") or "").strip()
        city_lower = city.lower()
        project_name = str(row.get("project_name", "") or "").strip()
        location_name = str(row.get("location_name", "") or "").strip()

        if not project_name or project_name.lower() in ["nan", "none", "<na>", "null", ""]:
            return None

        parts = [project_name]

        if location_name and location_name.lower() not in ["nan", "none", "<na>", "null", ""]:
            parts.append(location_name)

        if city_lower == "dubai":
            parts.append("Dubai, UAE")
        else:
            if city and city_lower not in ["nan", "none", "<na>", "null", ""]:
                parts.append(city)
            parts.append("India")

        return ", ".join(parts)


    def get_coordinates(query):
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "geometry,name,formatted_address,place_id",
            "key": GOOGLE_MAPS_API_KEY
        }
        base_res = {
            "google_latitude": None,
            "google_longitude": None,
            "google_project_name": None,
            "google_address": None,
            "google_place_id": None,
            "searched_query": query,
            "coordinate_status": "NOT_FOUND"
        }
        try:
            data = requests.get(url, params=params, timeout=10).json()
            if data.get("status") == "OK" and data.get("candidates"):
                result = data["candidates"][0]
                location = result.get("geometry", {}).get("location", {})
                base_res["google_latitude"] = location.get("lat")
                base_res["google_longitude"] = location.get("lng")
                base_res["google_project_name"] = result.get("name")
                base_res["google_address"] = result.get("formatted_address")
                base_res["google_place_id"] = result.get("place_id")
                base_res["coordinate_status"] = "FOUND"
            elif data.get("error_message"):
                base_res["coordinate_status"] = "FAILED"
                base_res["coordinate_error"] = data.get("error_message")
            return base_res
        except Exception as error:
            base_res["coordinate_status"] = "FAILED"
            base_res["coordinate_error"] = str(error)
            return base_res


    df = df.copy()

    df["project_name"] = df["project_name"].astype("string").str.strip()
    if "location_name" in df.columns:
        df["location_name"] = df["location_name"].astype("string").str.strip()
    if "city_name" in df.columns:
        df["city_name"] = df["city_name"].astype("string").str.strip()

    for col in ["project_latitude", "project_longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Every row (Dubai included) now requires project_name to be geocoded if coordinates are missing
    mask = (
        df["project_name"].notna()
        & df["project_name"].astype(str).str.strip().ne("")
        & ~df["project_name"].astype(str).str.strip().str.lower().isin(["nan", "none", "<na>", "null"])
        & (df["project_latitude"].isna() | df["project_longitude"].isna())
    )

    # Geocode key: city + project_name, so same project name in different cities doesn't collide
    df["_geocode_key"] = (
        df["city_name"].astype("string").str.strip().str.lower().fillna("")
        + "|" + df["project_name"].astype("string").str.strip().str.lower().fillna("")
    )

    subset = df.loc[mask, ["city_name", "project_name", "location_name", "_geocode_key"]].drop_duplicates(
        subset=["_geocode_key"]
    )

    print(f"[stepD] Distinct projects needing Google geocoding: {len(subset)}")

    results = []
    found_count = 0
    for i, row_dict in enumerate(subset.to_dict("records"), 1):
        query = build_query(row_dict)
        if query is None:
            print(f"[{i}/{len(subset)}] SKIPPED (no valid project_name)")
            continue

        result = get_coordinates(query)
        result["_geocode_key"] = row_dict["_geocode_key"]
        results.append(result)
        if result.get("coordinate_status") == "FOUND":
            found_count += 1
            print(f"[{i}/{len(subset)}] 🔍 {query} -> ✔ Found ({result['google_latitude']}, {result['google_longitude']})")
        else:
            print(f"[{i}/{len(subset)}] 🔍 {query} -> ⚠️ {result.get('coordinate_status')}")
        time.sleep(0.1)

    if results:
        lookup = pd.DataFrame(results)
        df = df.merge(lookup, on="_geocode_key", how="left", validate="many_to_one")
        if "google_latitude" in df.columns:
            df["project_latitude"] = df["project_latitude"].fillna(df["google_latitude"])
            df.drop(columns=["google_latitude"], errors="ignore", inplace=True)
        if "google_longitude" in df.columns:
            df["project_longitude"] = df["project_longitude"].fillna(df["google_longitude"])
            df.drop(columns=["google_longitude"], errors="ignore", inplace=True)

    df.drop(columns=["_geocode_key"], errors="ignore", inplace=True)
    print(f"[stepD] Geocoding complete: {found_count} / {len(subset)} projects found coordinates.")
    print(f"[stepD] Remaining blank project_latitude: {df['project_latitude'].isna().sum()}")
    print(f"[stepD] Remaining blank project_longitude: {df['project_longitude'].isna().sum()}")

# ============================== FINAL SCHEMA REORDER & SAVE ==============================
# 1. Clean 'index' column to remove '__Dubai' or '__.*' suffix
if "index" in df.columns:
    df["index"] = df["index"].map(clean_index)

# 2. Exclude unwanted columns explicitly requested to be removed
exclude_columns = [
    "project_id",
    "transaction_category_id",
    "google_project_name",
    "google_address",
    "google_place_id",
    "searched_query",
    "coordinate_status",
    "coordinate_error",
]
df.drop(columns=[c for c in exclude_columns if c in df.columns], errors="ignore", inplace=True)

# 3. Filter column_order to exclude removed columns
final_column_order = [c for c in column_order if c not in exclude_columns]

# Ensure all final_column_order columns are present
for col in final_column_order:
    if col not in df.columns:
        df[col] = None

# final_column_order first, rest of columns kept at the end
final_columns = final_column_order + [c for c in df.columns if c not in final_column_order and c not in exclude_columns]
df = df[final_columns]

# ============================== SAVE FINAL ==============================
df.to_excel(FINAL_OUTPUT_PATH, index=False)
print("\nSaved:", FINAL_OUTPUT_PATH)