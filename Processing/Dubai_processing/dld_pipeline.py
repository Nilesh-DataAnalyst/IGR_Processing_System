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

    PART 2 — Assign nr-style indexes to any rows still missing an index
      0. Starting number + DB mapping (scoped to CITY_ID)
      1. Show indexes containing numbers
      2. Clean blanks; normalize any existing nr values already in df
      3. Existing project + location + city -> index mapping (from df itself)
      4. Existing indexes for collision checking
      5. Fill only null indexes (reuse from this run, reuse from DB, or assign new nr)
         Rows with a blank project_name / location_name / city_name are
         skipped here too -- there's no valid key to assign an index against,
         so those rows end the run with a null index by design.
      6. Convert numeric indexes: 1001.0 -> 1001, keep nrXXXX unchanged
      6b. Final safety pass: strip any lingering suffix on nr-style values
      7. Verification / logging
      8. Save to CSV (with nr indexes)

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

import os, re
import numpy as np
import pandas as pd
import psycopg2
from sqlalchemy import create_engine

# ============================== CONFIG ==============================
RAW_CSV_PATH = r"D:\Database\Dubai_update\13aug_to_14sept\13aug_14sept.csv"
FINAL_OUTPUT_PATH = r"D:\Database\Dubai_update\13aug_to_14sept\13aug_14sept_processed.xlsx"
TEST_MERGE_PATH = r"D:\Database\Dubai_update\13aug_to_14sept\13aug_14sept_test_merge.xlsx"
CITY_ID, CITY_NAME = 15, "Dubai"

db_params = {
    "host": "localhost", "port": "5432", "database": "nilesh",
    "user": "postgres", "password": "nilesh"
}

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
df["INSTANCE_DATE"] = pd.to_datetime(df["INSTANCE_DATE"], format="%d-%m-%Y %H:%M", errors="coerce")
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
    x = str(x).strip(); m = re.match(r"(?i)^nr(\d+)", x)
    return f"nr{m.group(1)}" if m else x

def clean_index(x):
    if pd.isna(x): return None
    x = str(x).strip()
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

# ============================== STEP B: DB PROJECT+LOCATION MAP ==============================
def get_db_mapping(params, city_id):
    with psycopg2.connect(**params) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lower(trim(location_name)), lower(trim(project_name)), lower(trim(city_name)), internal_index_id
                FROM public.transactions
                WHERE city_id = %s AND internal_index_id IS NOT NULL
                  AND project_name IS NOT NULL AND location_name IS NOT NULL AND city_name IS NOT NULL;
            """, (city_id,))
            rows = cur.fetchall()
    out = {}
    for location, project, city, idx in rows:
        out.setdefault((location, project, city), strip_nr_suffix(idx))
    return out

db_mapping = get_db_mapping(db_params, CITY_ID)
print(f"[stepB] DB mappings loaded: {len(db_mapping)}")

# ============================== CLEAN BLANKS ==============================
cols = ["index", "project_name", "location_name", "city_name"]
df[cols] = df[cols].replace(r"^\s*$", np.nan, regex=True)
df["index"] = df["index"].astype("string").map(strip_nr_suffix)

# ============================== CURRENT FILE MAP ==============================
file_mapping = {}
for _, row in df.dropna(subset=cols).iterrows():
    file_mapping.setdefault(make_key(row["location_name"], row["project_name"], row["city_name"]), row["index"])
existing_indexes = set(df["index"].dropna().astype("string").str.strip().str.lower())

# ============================== ASSIGN INDEX ==============================
new_count = 0
for i in df.index[df["index"].isna()]:
    project, location, city = df.at[i,"project_name"], df.at[i,"location_name"], df.at[i,"city_name"]
    if pd.isna(project) or pd.isna(location) or pd.isna(city):
        continue
    key = make_key(location, project, city)
    if key in file_mapping:
        df.at[i,"index"] = file_mapping[key]
    elif key in db_mapping:
        idx = db_mapping[key]
        df.at[i,"index"] = idx; file_mapping[key] = idx; existing_indexes.add(str(idx).strip().lower())
    else:
        while f"nr{next_num}" in existing_indexes:
            next_num += 1
        new_index = f"nr{next_num}"
        df.at[i,"index"] = new_index
        file_mapping[key] = db_mapping[key] = new_index
        existing_indexes.add(new_index)
        next_num += 1; new_count += 1

# ============================== FINAL INDEX CLEANING ==============================
df["index"] = df["index"].astype(object).map(clean_index)
df["index"] = df["index"].map(lambda x: strip_nr_suffix(x) if isinstance(x, str) else x)
print(f"[stepB] new nr assigned: {new_count}")
if new_count: print(f"[stepB] highest new nr: nr{next_num-1}")
print("[stepB] remaining null index:", df["index"].isna().sum())
nr_numbers = df["index"].astype("string").str.extract(r"(?i)^nr(\d+)$")[0].dropna().astype(int)
if not nr_numbers.empty: print("[stepB] highest nr in final file:", f"nr{nr_numbers.max()}")

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
    "project_id","index","project_name",
    "village_name_marathi","location_id","location_name",
    "registered_document_village_name","year","quarter","city_id","city_name",
    "transaction_category_id","sub_registrar_office_code",
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

# Add missing columns
for col in column_order:
    if col not in df.columns:
        df[col] = None

# Required columns first, remaining columns after project_stage
df = df[column_order + [c for c in df.columns if c not in column_order]]

# =============================================================================
# FINAL TITLE CASE
# =============================================================================

for col in df.select_dtypes(include=["object", "string"]).columns:
    df[col] = df[col].apply(
        lambda x: x.title() if isinstance(x, str) else x
    )

# ============================== SAVE FINAL ==============================
df.to_excel(FINAL_OUTPUT_PATH, index=False)
print("\nSaved:", FINAL_OUTPUT_PATH)