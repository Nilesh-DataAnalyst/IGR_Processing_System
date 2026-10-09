import os
import re
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION & CONSTANTS
# ============================================================

from divisor import SALEABLE_TO_CARPET_DIVISOR_BY_CITY
BUILDUP_TO_CARPET_DIVISOR = 1.2

DEFAULT_DATABASE = "nilesh"

DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "database": DEFAULT_DATABASE,
    "user": "postgres",
    "password": "nilesh",
}


def get_db_params(override_db: str = None) -> dict:
    """Returns a copy of DB_PARAMS with an optional database override."""
    params = DB_PARAMS.copy()
    if override_db and str(override_db).strip():
        params["database"] = str(override_db).strip()
    return params


def set_active_db(db_name: str) -> dict:
    """Sets the active database globally in DB_PARAMS."""
    global DB_PARAMS
    if db_name and str(db_name).strip():
        DB_PARAMS["database"] = str(db_name).strip()
    return DB_PARAMS

DEFAULT_DRIVE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/1l-HFh36Yk8pSs-NmoSK60if6cP2cjztM"
)
DEFAULT_DRIVE_FOLDER_ID = "1l-HFh36Yk8pSs-NmoSK60if6cP2cjztM"


def resolve_drive_directory(drive_target: str = DEFAULT_DRIVE_FOLDER_URL) -> str:
    """Resolves a Google Drive folder URL, folder ID, or local Drive path to a writable local directory on G:."""
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


def derive_net_carpet_area(df: pd.DataFrame, city: str | int = None) -> pd.DataFrame:
    """Fill net_carpet_area_sqmt from whichever area column is available using city-specific divisor."""
    from project_name_Std_and_area_conversion import resolve_city_and_divisor
    city_key, saleable_divisor = resolve_city_and_divisor(city=city)

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
    df = df.copy()
    if "property_type_raw" in df.columns and "property_type" in df.columns:
        df = df.drop(columns=["property_type_raw"])
    df = df.rename(
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
        }
    )
    return df.loc[:, ~df.columns.duplicated()].copy()


def _map_property_type(value):
    if isinstance(value, (pd.Series, np.ndarray, list)):
        valid = [v for v in value if pd.notna(v) and str(v).strip() != ""]
        value = valid[0] if valid else None
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


def map_unit(x):
    if pd.isna(x) or str(x).strip() in ("", "nan", "None", "<NA>", "nan"):
        return "Others"
    x_str = str(x).lower().replace(" ", "")
    if "office" in x_str:
        return "Office"
    if "shop" in x_str:
        return "Shop"
    if "flat" in x_str:
        return "Flat"
    m = re.search(r'(\d+(?:\.\d+)?)bhk', x_str)
    if not m:
        return "Others"
    n = float(m.group(1))
    if n < 1:
        return "<1Bhk"
    if n > 3:
        return ">3Bhk"
    return {1: "1Bhk", 1.5: "1.5Bhk", 2: "2Bhk", 2.25: "2.25Bhk", 2.5: "2.5Bhk", 2.75: "2.75Bhk", 3: "3Bhk"}.get(n, "Others")


def assign_nr_indexes(
    df: pd.DataFrame, target_city_id: int, db_params: dict
) -> tuple[pd.DataFrame, dict]:
    """Fetches maximum 'nr' index from Postgres DB for target city and fills missing 'index' values."""
    df = df.copy()

    if "index" not in df.columns:
        df["index"] = np.nan

    df["index"] = df["index"].astype(object).replace(r"^\s*$", np.nan, regex=True)

    if "project_name" in df.columns:
        df["project_name"] = (
            df["project_name"].replace(r"^\s*$", np.nan, regex=True)
        )

    if "project_latitude" not in df.columns:
        df["project_latitude"] = np.nan
    else:
        df["project_latitude"] = pd.to_numeric(df["project_latitude"], errors="coerce")

    if "project_longitude" not in df.columns:
        df["project_longitude"] = np.nan
    else:
        df["project_longitude"] = pd.to_numeric(df["project_longitude"], errors="coerce")

    def _to_float(v):
        if v is None or pd.isna(v):
            return None
        try:
            val = float(v)
            return val if not np.isnan(val) else None
        except (ValueError, TypeError):
            return None

    loc_col = next((c for c in ["location_name", "registered_document_village_name"] if c in df.columns), None)

    # 1. Load existing DB index & coordinates mappings for (location_name, project_name)
    db_mapping = {}
    db_coords_mapping = {}
    try:
        conn = psycopg2.connect(**db_params)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lower(trim(location_name)), lower(trim(project_name)), internal_index_id, project_latitude, project_longitude
                FROM public.transactions
                WHERE city_id = %s
                  AND project_name IS NOT NULL AND location_name IS NOT NULL;
            """, (target_city_id,))
            for loc, proj, idx, lat, lon in cur.fetchall():
                if loc and proj:
                    key = (loc, proj)
                    if idx and str(idx).strip() and key not in db_mapping:
                        db_mapping[key] = str(idx).strip()
                    plat, plon = _to_float(lat), _to_float(lon)
                    if plat is not None and plon is not None and key not in db_coords_mapping:
                        db_coords_mapping[key] = (plat, plon)
        conn.close()
    except Exception:
        pass

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

    # 2. Build current file mapping for (location_name, project_name) -> index & coordinates
    file_mapping = {}
    file_coords_mapping = {}
    if loc_col and "project_name" in df.columns:
        valid_rows = df.dropna(subset=[loc_col, "project_name"])
        for _, row in valid_rows.iterrows():
            l_key = str(row[loc_col]).strip().lower()
            p_key = str(row["project_name"]).strip().lower()
            if l_key and p_key:
                k = (l_key, p_key)
                if pd.notna(row.get("index")) and str(row["index"]).strip():
                    file_mapping.setdefault(k, str(row["index"]).strip())
                plat, plon = _to_float(row.get("project_latitude")), _to_float(row.get("project_longitude"))
                if plat is not None and plon is not None:
                    file_coords_mapping.setdefault(k, (plat, plon))

    existing_indexes = set(
        df["index"].dropna().astype(str).str.strip().str.lower()
    )

    if "project_name" in df.columns:
        rows_to_assign = df.index[
            df["index"].isna()
            & df["project_name"].notna()
            & df["project_name"].astype("string").str.strip().ne("")
        ]
    else:
        rows_to_assign = df.index[df["index"].isna()]

    new_count = 0
    reused_count = 0

    for i in rows_to_assign:
        proj = str(df.at[i, "project_name"]).strip().lower() if "project_name" in df.columns and pd.notna(df.at[i, "project_name"]) else ""
        loc = str(df.at[i, loc_col]).strip().lower() if loc_col and pd.notna(df.at[i, loc_col]) else ""
        key = (loc, proj) if (loc and proj) else None

        if key and key in file_mapping:
            df.at[i, "index"] = file_mapping[key]
            reused_count += 1
        elif key and key in db_mapping:
            existing_idx = db_mapping[key]
            df.at[i, "index"] = existing_idx
            file_mapping[key] = existing_idx
            existing_indexes.add(str(existing_idx).strip().lower())
            reused_count += 1
        else:
            while f"nr{next_num}" in existing_indexes:
                next_num += 1
            new_index = f"nr{next_num}"
            df.at[i, "index"] = new_index
            if key:
                file_mapping[key] = new_index
                db_mapping[key] = new_index
            existing_indexes.add(new_index.lower())
            next_num += 1
            new_count += 1

    # Populate project coordinates for matching (location_name, project_name)
    coords_reused = 0
    if loc_col and "project_name" in df.columns:
        for i in df.index:
            p_val = df.at[i, "project_name"]
            l_val = df.at[i, loc_col]
            if pd.notna(p_val) and pd.notna(l_val):
                p_key = str(p_val).strip().lower()
                l_key = str(l_val).strip().lower()
                if p_key and l_key:
                    k = (l_key, p_key)
                    lat_blank = pd.isna(df.at[i, "project_latitude"])
                    lon_blank = pd.isna(df.at[i, "project_longitude"])
                    if lat_blank or lon_blank:
                        coords = file_coords_mapping.get(k) or db_coords_mapping.get(k)
                        if coords:
                            lat, lon = coords
                            if lat_blank and lat is not None:
                                df.at[i, "project_latitude"] = float(lat)
                            if lon_blank and lon is not None:
                                df.at[i, "project_longitude"] = float(lon)
                            coords_reused += 1

    stats = {
        "highest_db_nr": max_nr,
        "eligible_rows": len(rows_to_assign),
        "reused_count": reused_count,
        "new_nr_assigned": new_count,
        "highest_new_nr": f"nr{next_num - 1}" if new_count > 0 else f"nr{max_nr}",
        "blank_remaining": int(df["index"].isna().sum()),
        "coords_reused": coords_reused
    }
    return df, stats


def populate_location_coords(df: pd.DataFrame, city_id: int, db_params: dict) -> pd.DataFrame:
    loc_col = next((c for c in ["location_name", "location"] if c in df.columns), None)
    if not loc_col:
        return df

    conn = psycopg2.connect(**db_params)
    try:
        coords = pd.read_sql_query(
            "SELECT DISTINCT LOWER(TRIM(location_name)) AS loc, location_latitude AS latitude, location_longitude AS longitude FROM public.dim_location WHERE city_id = %s AND location_latitude IS NOT NULL",
            conn,
            params=(city_id,),
        )
    finally:
        conn.close()

    coords = coords.drop_duplicates(subset=["loc"])
    keys = df[loc_col].astype(str).str.strip().str.lower()
    df["location_latitude"] = keys.map(coords.set_index("loc")["latitude"])
    df["location_longitude"] = keys.map(coords.set_index("loc")["longitude"])
    return df


def keep_db_columns(df: pd.DataFrame, db_sequence: list) -> pd.DataFrame:
    existing_cols = [col for col in db_sequence if col in df.columns]
    return df[existing_cols].copy()


def populate_village_mapping(df: pd.DataFrame, city_id: int, db_params: dict) -> pd.DataFrame:
    col = next((c for c in ["village_name_marathi", "areaname"] if c in df.columns), None)
    if col:
        keys = (df[col].iloc[:, 0] if isinstance(df[col], pd.DataFrame) else df[col]).astype(str).str.strip()
        try:
            conn = psycopg2.connect(**db_params)
            q = "SELECT DISTINCT TRIM(village_name_marathi) AS v, registered_document_village_name AS r FROM public.transactions WHERE city_id = %s AND village_name_marathi = ANY(%s)"
            lookup = pd.read_sql_query(q, conn, params=(city_id, list(keys.unique()))).drop_duplicates("v").set_index("v")["r"]
            mapped = keys.map(lookup)
            if "registered_document_village_name" in df.columns:
                df["registered_document_village_name"] = df["registered_document_village_name"].fillna(mapped)
            else:
                df["registered_document_village_name"] = mapped
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    if "registered_document_village_name" in df.columns:
        df["location_name"] = df["registered_document_village_name"]
    return df


def load_and_merge_step7_files(file_inputs: list | str, log_callback=None) -> tuple[pd.DataFrame, dict]:
    """
    Loads one or multiple manual corrected files (Excel/CSV), computes column counts per file,
    detects missing columns per file vs union of all columns, logs merging status, and merges all dataframes.

    :param file_inputs: A single path, comma/newline/pipe-separated path string, or list of file paths.
    :param log_callback: Optional callable for logging messages: log_callback(msg, level)
    :return: Tuple of (merged_df, report_dict)
    """
    def _log(msg: str, level: str = "info"):
        if log_callback:
            try:
                log_callback(msg, level)
                return
            except Exception:
                pass
        try:
            print(f"[{level.upper()}] {msg}")
        except UnicodeEncodeError:
            safe_msg = msg.encode("ascii", "replace").decode("ascii")
            print(f"[{level.upper()}] {safe_msg}")

    raw_paths = []
    if isinstance(file_inputs, list):
        for item in file_inputs:
            if isinstance(item, str):
                parts = [p.strip().strip('"').strip("'") for p in re.split(r'[,\n|;]', item) if p.strip()]
                raw_paths.extend(parts)
            elif item:
                raw_paths.append(str(item).strip())
    elif isinstance(file_inputs, str):
        parts = [p.strip().strip('"').strip("'") for p in re.split(r'[,\n|;]', file_inputs) if p.strip()]
        raw_paths.extend(parts)

    valid_paths = []
    seen = set()
    for p in raw_paths:
        if p and p not in seen:
            seen.add(p)
            if os.path.exists(p):
                valid_paths.append(p)
            else:
                _log(f"⚠️ Step 7 Merge warning: File path does not exist: {p}", "warning")

    if not valid_paths:
        raise FileNotFoundError(f"No valid existing file paths provided for Step 7 merge. Input: {file_inputs}")

    if len(valid_paths) == 1:
        _log(f"📖 [Step 7 Load] Loading single manual corrected file: '{os.path.basename(valid_paths[0])}'...", "info")
    else:
        _log(f"🔄 [Step 7 Multi-File Merge] Initializing merge operation for {len(valid_paths)} files...", "info")

    dfs = []
    file_info_list = []
    all_columns_order = []

    for idx, fpath in enumerate(valid_paths, 1):
        fname = os.path.basename(fpath)
        _log(f"📂 Reading file [{idx}/{len(valid_paths)}]: {fname}", "info")
        try:
            if fpath.lower().endswith(".csv"):
                df_i = pd.read_csv(fpath, low_memory=False)
            else:
                df_i = pd.read_excel(fpath, engine="openpyxl")
        except Exception as err:
            _log(f"❌ Error reading '{fname}': {err}", "error")
            raise err

        cols_list = [str(c).strip() if (c is not None and not pd.isna(c)) else f"Unnamed_{i}" for i, c in enumerate(df_i.columns)]
        df_i.columns = cols_list

        # Standardize flat_no -> flat_no_raw and floor_no -> floor_no_raw per file before merging
        rename_map = {}
        if "flat_no" in df_i.columns and "flat_no_raw" not in df_i.columns:
            rename_map["flat_no"] = "flat_no_raw"
        if "floor_no" in df_i.columns and "floor_no_raw" not in df_i.columns:
            rename_map["floor_no"] = "floor_no_raw"
        if rename_map:
            df_i.rename(columns=rename_map, inplace=True)
            cols_list = list(df_i.columns)

        if "flat_no" in df_i.columns and "flat_no_raw" in df_i.columns:
            df_i["flat_no_raw"] = df_i["flat_no_raw"].fillna(df_i["flat_no"])
        if "floor_no" in df_i.columns and "floor_no_raw" in df_i.columns:
            df_i["floor_no_raw"] = df_i["floor_no_raw"].fillna(df_i["floor_no"])

        for col in cols_list:
            if col not in all_columns_order:
                all_columns_order.append(col)

        dfs.append(df_i)
        file_info_list.append({
            "index": idx,
            "filename": fname,
            "path": fpath,
            "row_count": len(df_i),
            "column_count": len(cols_list),
            "columns": cols_list,
            "columns_set": set(cols_list)
        })

    any_missing = False

    for info in file_info_list:
        missing = [col for col in all_columns_order if col not in info["columns_set"]]
        info["missing_columns"] = missing
        info["missing_count"] = len(missing)
        if missing:
            any_missing = True

        _log(f"📄 File {info['index']}: '{info['filename']}' | Rows: {info['row_count']:,} | Columns: {info['column_count']}", "info")
        if missing:
            missing_sample = missing[:8]
            more_str = f" (+{len(missing)-8} more)" if len(missing) > 8 else ""
            _log(f"   ⚠️ Missing {len(missing)} column(s) vs other files: {missing_sample}{more_str}", "warning")
        else:
            _log("   ✓ All union columns present in this file.", "success")

    if len(valid_paths) == 1:
        status_type = "SINGLE_FILE"
        status_msg = f"✓ Single file loaded ({file_info_list[0]['column_count']} columns, {file_info_list[0]['row_count']:,} rows)."
        _log(status_msg, "success")
    elif not any_missing:
        status_type = "PERFECT_MATCH"
        status_msg = f"✓ Merge Status: PERFECT MATCH across all {len(valid_paths)} files ({len(all_columns_order)} uniform columns, total {sum(i['row_count'] for i in file_info_list):,} rows)."
        _log(status_msg, "success")
    else:
        status_type = "COLUMN_MISMATCH"
        mismatched_files_count = sum(1 for i in file_info_list if i["missing_count"] > 0)
        status_msg = f"⚠️ Merge Status: COLUMN MISMATCH detected! {mismatched_files_count} of {len(valid_paths)} files missing columns (Total unique columns: {len(all_columns_order)}). Missing fields filled with empty values."
        _log(status_msg, "warning")

    if len(dfs) == 1:
        merged_df = dfs[0]
    else:
        merged_df = pd.concat(dfs, ignore_index=True)

    # Standardize final merged target columns flat_no_raw & floor_no_raw
    if "flat_no" in merged_df.columns:
        if "flat_no_raw" not in merged_df.columns:
            merged_df["flat_no_raw"] = merged_df["flat_no"]
        else:
            merged_df["flat_no_raw"] = merged_df["flat_no_raw"].fillna(merged_df["flat_no"])
    if "floor_no" in merged_df.columns:
        if "floor_no_raw" not in merged_df.columns:
            merged_df["floor_no_raw"] = merged_df["floor_no"]
        else:
            merged_df["floor_no_raw"] = merged_df["floor_no_raw"].fillna(merged_df["floor_no"])

    if "net_carpet_area_sqmt" in merged_df.columns and "net_carpet_area_sq_m" not in merged_df.columns:
        merged_df["net_carpet_area_sq_m"] = merged_df["net_carpet_area_sqmt"]
    if "net_carpet_area_sq_m" in merged_df.columns:
        if "net_carpet_area_sqft" not in merged_df.columns:
            merged_df["net_carpet_area_sqft"] = (pd.to_numeric(merged_df["net_carpet_area_sq_m"], errors="coerce") * 10.7639).round(2)
        if "rate_in_sqft" not in merged_df.columns and "consideration_amt" in merged_df.columns:
            merged_df["rate_in_sqft"] = (pd.to_numeric(merged_df["consideration_amt"], errors="coerce") / merged_df["net_carpet_area_sqft"]).round(2)

    # Exclude user-specified unwanted columns from final merged DataFrame
    exclude_set = {
        "society_name", "society_name_en", "society_name_original", "full_address_en", "full_address_original",
        "road_name_en", "road_name_original", "city_en", "city_original", "taluka_en", "taluka_original",
        "district_en", "district_original", "state_en", "state_original", "AREA DETAILS_basement_area",
        "final_project_name", "project_name_list", "project_name_text", "Modified_Project_Name_1",
        "project_count", "project_comparison_key", "is_generic_project_name", "project_match_confidence_label",
        "project_match_reason", "cluster_min_confidence_score", "requires_manual_review",
        "carpet_area_conversion_done", "builtup_area_conversion_done", "super_builtup_area_conversion_done",
        "saleable_area_conversion_done", "terrace_area_sqmt", "terrace_area_conversion_source",
        "terrace_area_conversion_status", "terrace_area_conversion_done", "balcony_area_sqmt",
        "balcony_area_conversion_source", "balcony_area_conversion_status", "balcony_area_conversion_done",
        "total_area_conversion_done", "plot_area_conversion_done", "parking_area_sqmt",
        "parking_area_conversion_source", "parking_area_conversion_status", "parking_area_conversion_done",
        "covered_parking_area_sqmt", "covered_parking_area_conversion_source",
        "covered_parking_area_conversion_status", "covered_parking_area_conversion_done",
        "car_parking_area_sqmt", "car_parking_area_conversion_source", "car_parking_area_conversion_status",
        "car_parking_area_conversion_done", "garden_area_sqmt", "garden_area_conversion_source",
        "garden_area_conversion_status", "garden_area_conversion_done", "gallery_area_sqmt",
        "gallery_area_conversion_source", "gallery_area_conversion_status", "gallery_area_conversion_done",
        "loft_area_sqmt", "loft_area_conversion_source", "loft_area_conversion_status", "loft_area_conversion_done",
        "office_area_sqmt", "office_area_conversion_source", "office_area_conversion_status",
        "office_area_conversion_done", "shop_area_sqmt", "shop_area_conversion_source",
        "shop_area_conversion_status", "shop_area_conversion_done", "mezzanine_area_sqmt",
        "mezzanine_area_conversion_source", "mezzanine_area_conversion_status", "mezzanine_area_conversion_done",
        "open_area_sqmt", "open_area_conversion_source", "open_area_conversion_status",
        "open_area_conversion_done", "AREA DETAILS_garage_area", "AREA DETAILS_old_flat_area",
        "PROPERTY IDENTIFICATION_rex_chambers_coop_soc_ltd", "AREA DETAILS_additional_area",
        "AREA DETAILS_shop_1_area", "AREA DETAILS_shop_2_area", "AREA DETAILS_shop_3_area",
        "AREA DETAILS_shop_4_area", "AREA DETAILS_shop_5_area", "AREA DETAILS_shop_6_area",
        "AREA DETAILS_shop_12_area", "AREA DETAILS_shop_12a_area", "AREA DETAILS_shop_14_area",
        "AREA DETAILS_shop_15_area", "AREA DETAILS_shop_16_area", "AREA DETAILS_shop_17_area",
        "AREA DETAILS_other_area", "AREA DETAILS_builtup_area_sqm", "FLAT AREAS",
        "AREA DETAILS_shop_9_area", "AREA DETAILS_shop_10_area", "AREA DETAILS_new_carpet_area_mofa",
        "AREA DETAILS_new_carpet_area_rera", "AREA DETAILS_plot_area_additional",
        "AREA DETAILS_shop_area_1", "AREA DETAILS_shop_area_2", "AREA DETAILS_shop_area_3",
        "PROPERTY IDENTIFICATION_CTS_no_new", "Corrected By Deeksha", "AREA DETAILS_chatai_area",
        "AREA DETAILS_shop_area_05", "AREA DETAILS_shop_area_06", "AREA DETAILS_office_01_area",
        "AREA DETAILS_office_02_area", "AREA DETAILS_office_03_area", "AREA DETAILS_office_04_area",
        "AREA DETAILS_office_05_area", "AREA DETAILS_office_06_area", "OTHER DETAILS_rera_details",
        "PROPERTY IDENTIFICATION_society_name_2", "AREA DETAILS_builtup_area_2", "OTHER DETAILS_owner_name_2",
        "OTHER DETAILS_owner_name_original_2", "OTHER DETAILS_rera_mentioned",
        "PROPERTY IDENTIFICATION_CTS_no_old", "OTHER DETAILS_village", "AREA DETAILS_office_205_area",
        "AREA DETAILS_office_306_area", "AREA DETAILS_plot_area_4", "AREA DETAILS_plot_area_5",
        "AREA DETAILS_plot_area_6", "AREA DETAILS_godown_area", "AREA DETAILS_old_area",
        "AREA DETAILS_new_area", "AREA DETAILS_plot_area_other", "AREA DETAILS_plot_area_other2",
        "AREA DETAILS_plot_area_other3", "AREA DETAILS_plot_area_other4", "AREA DETAILS_unit_1901_area",
        "AREA DETAILS_unit_1902_area", "AREA DETAILS_unit_1903_area", "AREA DETAILS_unit_1904_area",
        "AREA DETAILS_unit_2001_area", "AREA DETAILS_unit_2002_area", "AREA DETAILS_unit_2003_area",
        "AREA DETAILS_unit_405", "AREA DETAILS_unit_406", "AREA DETAILS_unit_412",
        "AREA DETAILS_unit_427", "AREA DETAILS_unit_428", "AREA DETAILS_open_car_parking_area",
        "AREA DETAILS_basement_car_parking_area", "AREA DETAILS_area_unit_201", "AREA DETAILS_area_unit_202",
        "UNIT DETAILS", "AREA DETAILS_ground_floor_area", "AREA DETAILS_reserved_garden_area",
        "AREA DETAILS_roadside_area", "AREA DETAILS_stilt_car_parking_area", "AREA DETAILS_area_details",
        "AREA DETAILS_kitchen_balcony_area", "AREA DETAILS_shop_7_area", "rate",
        "AREA DETAILS_verona_carpet_area", "AREA DETAILS_flower_bed_area", "AREA DETAILS_plot_area_tps",
        "AREA DETAILS_flat_101_area", "AREA DETAILS_flat_103_area", "AREA DETAILS_flat_1404_area",
        "AREA DETAILS_flat_1504_area", "AREA DETAILS_closed_garage_area", "AREA DETAILS_setback_area"
    }

    cols_to_drop = [c for c in merged_df.columns if c.strip() in exclude_set or c.strip().lower() in {x.lower() for x in exclude_set}]
    if cols_to_drop:
        merged_df.drop(columns=cols_to_drop, inplace=True, errors="ignore")
        _log(f"✂️ Excluded {len(cols_to_drop)} unneeded column(s) from merged output file.", "info")

    report = {
        "file_count": len(valid_paths),
        "total_rows": len(merged_df),
        "total_unique_columns": len(all_columns_order),
        "status_type": status_type,
        "status_message": status_msg,
        "has_column_mismatch": any_missing,
        "files": [
            {
                "index": f["index"],
                "filename": f["filename"],
                "path": f["path"],
                "row_count": f["row_count"],
                "column_count": f["column_count"],
                "missing_columns": f["missing_columns"],
                "missing_count": f["missing_count"],
            }
            for f in file_info_list
        ]
    }

    # Automatically save merged file to Google Drive '3. Manually Corrected / FINAL MERGE'
    saved_merged_path = None
    save_dir = None
    shortcut_dir = os.path.join(r"G:\.shortcut-targets-by-id", "1ywb1-CSRDXNV80Yc8AXYm5Bgze34TXFA")
    if os.path.exists(shortcut_dir):
        sub_items = [os.path.join(shortcut_dir, d) for d in os.listdir(shortcut_dir) if os.path.isdir(os.path.join(shortcut_dir, d))]
        for sub in sub_items:
            if "manually corrected" in os.path.basename(sub).lower():
                save_dir = sub
                break
        if not save_dir:
            save_dir = shortcut_dir

    if not save_dir or not os.path.exists(save_dir):
        save_dir = os.path.dirname(valid_paths[0]) if valid_paths else os.getcwd()

    final_merge_dir = os.path.join(save_dir, "FINAL MERGE")
    os.makedirs(final_merge_dir, exist_ok=True)

    saved_merged_path = os.path.join(final_merge_dir, "final merge file.xlsx")
    try:
        merged_df.to_excel(saved_merged_path, index=False)
        _log(f"💾 Merged file saved to '3. Manually Corrected / FINAL MERGE' ({len(merged_df):,} rows): {saved_merged_path}", "success")
    except Exception as save_err:
        _log(f"⚠️ Note saving merged file to '{saved_merged_path}': {save_err}", "warning")

    report["merged_output_file"] = saved_merged_path

    # Generate dedicated Excel & CSV reports showing missing columns per file
    def _clean_str(val):
        if val is None or pd.isna(val):
            return ""
        s = str(val)
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', s)

    missing_report_path = os.path.join(final_merge_dir, "Step7_Missing_Columns_Report.xlsx")
    csv_matrix_path = os.path.join(final_merge_dir, "Step7_Missing_Columns_Matrix.csv")
    try:
        # Sheet 1: Per-File Summary
        summary_rows = []
        for info in file_info_list:
            summary_rows.append({
                "File Index": info["index"],
                "File Name": _clean_str(info["filename"]),
                "File Path": _clean_str(info["path"]),
                "Total Rows": info["row_count"],
                "Present Columns Count": info["column_count"],
                "Missing Columns Count": info["missing_count"],
                "Missing Columns List": _clean_str(", ".join(str(c) for c in info["missing_columns"])) if info["missing_columns"] else "None (All Present)"
            })
        df_summary = pd.DataFrame(summary_rows)

        # Sheet 2: Matrix View (Columns x Files)
        matrix_rows = []
        for col_name in all_columns_order:
            col_clean = _clean_str(col_name)
            row = {"Column Name": col_clean}
            present_cnt = 0
            missing_cnt = 0
            for info in file_info_list:
                col_key = f"File {info['index']}: {_clean_str(info['filename'])}"
                if col_name in info["columns_set"]:
                    row[col_key] = "Present"
                    present_cnt += 1
                else:
                    row[col_key] = "Missing"
                    missing_cnt += 1
            row["Total Files Present"] = present_cnt
            row["Total Files Missing"] = missing_cnt
            matrix_rows.append(row)

        df_matrix = pd.DataFrame(matrix_rows)
        matrix_cols = ["Column Name", "Total Files Present", "Total Files Missing"] + [c for c in df_matrix.columns if c not in ["Column Name", "Total Files Present", "Total Files Missing"]]
        df_matrix = df_matrix[matrix_cols]

        # Sheet 3: Detailed List of Missing Columns
        detail_rows = []
        for info in file_info_list:
            if info["missing_columns"]:
                for missing_col in info["missing_columns"]:
                    detail_rows.append({
                        "File Index": info["index"],
                        "File Name": _clean_str(info["filename"]),
                        "Missing Column Name": _clean_str(missing_col),
                        "File Path": _clean_str(info["path"])
                    })
            else:
                detail_rows.append({
                    "File Index": info["index"],
                    "File Name": _clean_str(info["filename"]),
                    "Missing Column Name": "None (All Present)",
                    "File Path": _clean_str(info["path"])
                })
        df_detail = pd.DataFrame(detail_rows)

        # Save CSV matrix fallback
        df_matrix.to_csv(csv_matrix_path, index=False)
        _log(f"📊 Missing Columns Matrix CSV saved: {csv_matrix_path}", "success")

        # Save Multi-sheet Excel workbook
        with pd.ExcelWriter(missing_report_path, engine="openpyxl") as writer:
            df_summary.to_excel(writer, sheet_name="Summary", index=False)
            df_matrix.to_excel(writer, sheet_name="Column Matrix", index=False)
            df_detail.to_excel(writer, sheet_name="Missing Columns Detail", index=False)

        _log(f"📊 Missing Columns Report Excel saved to '3. Manually Corrected': {missing_report_path}", "success")
        report["missing_columns_excel_report"] = missing_report_path
        report["missing_columns_csv_report"] = csv_matrix_path
    except Exception as rep_err:
        import traceback
        _log(f"⚠️ Note generating missing columns report: {rep_err}", "warning")
        _log(f"Traceback: {traceback.format_exc()}", "error")

    _log(f"✅ Step 7 Merge Complete: Merged {len(valid_paths)} file(s) -> {len(merged_df):,} total rows, {len(merged_df.columns)} columns.", "success")
    return merged_df, report




