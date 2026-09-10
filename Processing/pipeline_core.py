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

DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "database": "nilesh",
    "user": "postgres",
    "password": "nilesh",
}

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


def derive_net_carpet_area(df: pd.DataFrame, city: str = "pune") -> pd.DataFrame:
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

    for i in rows_to_assign:
        while f"nr{next_num}" in existing_indexes:
            next_num += 1
        new_index = f"nr{next_num}"
        df.at[i, "index"] = new_index
        existing_indexes.add(new_index)
        next_num += 1

    stats = {
        "highest_db_nr": max_nr,
        "eligible_rows": len(rows_to_assign),
        "assigned_count": len(rows_to_assign),
        "highest_new_nr": f"nr{next_num - 1}" if len(rows_to_assign) > 0 else f"nr{max_nr}",
        "blank_remaining": int(df["index"].isna().sum())
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
    try:
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
    finally:
        conn.close()

    lookup = lookup.drop_duplicates(subset=["village_name_marathi"], keep="first")
    lookup = lookup.set_index("village_name_marathi")

    col_series = df[col].iloc[:, 0] if isinstance(df[col], pd.DataFrame) else df[col]
    keys = col_series.astype(str).str.strip()
    df["location_name"] = keys.map(lookup["location_name"])
    df["registered_document_village_name"] = keys.map(lookup["registered_document_village_name"])
    return df
