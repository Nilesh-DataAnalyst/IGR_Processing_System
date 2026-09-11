import pandas as pd
import ast
import numpy as np


def _get_rera_values(rera_grand, project, village):
    """Exact then list-fallback RERA lookup for a project+village pair."""
    mask = (
        (rera_grand['modified_project_name'] == project) &
        (rera_grand['rera_location'] == village)
    )
    match = rera_grand[mask]

    if match.empty:
        def _in_list(x):
            try:
                return isinstance(x, str) and x.startswith('[') and village in ast.literal_eval(x)
            except Exception:
                return False
        mask = (
            (rera_grand['modified_project_name'] == project) &
            rera_grand['rera_location_v1'].apply(_in_list)
        )
        match = rera_grand[mask]

    if not match.empty:
        r = match.iloc[0]
        return r['index'], r['project_lat'], r['project_lng']
    return None, None, None


def assign_rera_index(final_village: pd.DataFrame,
                       rera_grand: pd.DataFrame, city: str) -> pd.DataFrame:
    print("[RERA] Assigning index...")

    # Safe string normalisation — handles NaN and non-string values
    for col in ['registered_document_village_name', 'location_name', 'project_name']:
        final_village[col] = (
            final_village[col].astype(str)
            .str.title().str.strip().str.strip("\n")
            .replace('Nan', np.nan)
        )

    final_village['location_name'] = final_village['location_name'].fillna(final_village['registered_document_village_name'])

    for col in ['modified_project_name', 'rera_location', 'rera_location_v1']:
        rera_grand[col] = (
            rera_grand[col].astype(str)
            .str.strip().str.title()
            .replace('Nan', np.nan)
        )

    rera_grand = rera_grand.sort_values('index')
    print(f"  Duplicate RERA entries: {rera_grand.duplicated(subset=['modified_project_name', 'rera_location']).sum()}")
    rera_grand.drop_duplicates(subset=['modified_project_name', 'rera_location'], inplace=True)

    # Exact merge on project_name + location
    final_village = final_village.merge(
        rera_grand[['index', 'modified_project_name', 'rera_location', 'project_lat', 'project_lng','project_type']],
        left_on=['project_name', 'location_name'],
        right_on=['modified_project_name', 'rera_location'],
        how='left'
    )

    # Fuzzy fallback for rows still missing index
    lookup = {}
    unmatched = final_village[
        final_village['project_name'].notna() & final_village['index'].isna()
    ].groupby(['project_name', 'location_name'])

    for (project, village), group in unmatched:
        if (project, village) not in lookup:
            lookup[(project, village)] = _get_rera_values(rera_grand, project, village)
        idx, lat, lng = lookup[(project, village)]
        final_village.loc[group.index, 'index'] = idx
        final_village.loc[group.index, 'project_lat'] = lat
        final_village.loc[group.index, 'project_lng'] = lng

    # Assign non-RERA index codes for manually processed rows
    final_village['index'] = pd.to_numeric(final_village['index'], errors='coerce')
    final_village['city'] = city.title()

    # non_rera = (
    #     final_village[
    #         final_village['index'].isna() & (final_village['manual_processed'] == 'Yes')
    #     ][['project_name', 'igr_village']]
    #     .drop_duplicates()
    #     .reset_index(drop=True)
    # )

    # prefix = (city.lower()[0] + "NR").lower()
    # non_rera['index'] = [f"{prefix}{str(i).zfill(3)}" for i in range(101, 101 + len(non_rera))]

    # merged_df = final_village.merge(
    #     non_rera[['project_name', 'igr_village', 'index']],
    #     on=['project_name', 'igr_village'],
    #     how='left', suffixes=('', '_grouped')
    # )
    # merged_df['index'] = merged_df['index'].fillna(merged_df.pop('index_grouped'))
    # merged_df['index'] = merged_df['index'].apply(
    #     lambda x: str(int(float(x))) if str(x).replace('.', '').isdigit() else x
    # )
    return final_village

import ast
import os
import re
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
warnings.filterwarnings("ignore")

SKIP_BHK = {'UNDEFINED FLATS', 'SHOP', 'OFFICE', 'OTHERS'}
NULL_KEYS = {'', 'NA', 'NULL'}


def combine_columns(bhk_ca):
    """Flatten BHK-wise carpet area nested structure into {BHK_KEY: [area_list]}."""
    try:
        if isinstance(bhk_ca, float):
            return None
        result_local = {}
        try:
            old_ca_list = eval(str(bhk_ca).lower())   # noqa: S307
        except Exception:
            old_ca_list = str(bhk_ca).lower()
        try:
            old_ca_list = eval(old_ca_list)            # noqa: S307
        except Exception:
            pass
        try:
            old_ca_list = eval(old_ca_list)            # noqa: S307
        except Exception:
            pass

        for values in old_ca_list.values():
            try:
                for item in eval(values):              # noqa: S307
                    for key in item:
                        new_key = key.replace(" bhk", "bhk").upper()
                        result_local.setdefault(new_key, []).extend(item[key])
            except Exception:
                try:
                    for item in eval(values)[0]:       # noqa: S307
                        for key in item:
                            new_key = key.replace(" bhk", "bhk").upper()
                            result_local.setdefault(new_key, [])
                except Exception:
                    pass
        return str(result_local)
    except Exception:
        print(bhk_ca)
        return None


def _normalize_bhk_key(key, keyword_map):
    k = key.strip().upper()
    if k in NULL_KEYS:
        return 'OTHERS'
    if k in SKIP_BHK:
        return k
    return keyword_map.get(k, k)


def _clean_bhk_values(value_list):
    out = []
    for v in value_list:
        s = re.sub(r'(\d+\.\d+)\.', r'\1', str(v))
        s = re.sub(r'(\d+)\.\.(\d+)', r'\1.\2', s)
        try:
            out.append(round(float(s), 2))
        except ValueError:
            pass
    return out


def _find_closest_bhk(carpet, building_info, max_diff):
    best_bhk, best_val, best_diff = None, None, float('inf')
    for bhk_type, values in building_info.items():
        if not values:
            continue
        arr = np.array(values, dtype=np.float64)
        diffs = np.abs(arr - carpet)
        idx = diffs.argmin()
        diff = float(diffs[idx])
        if diff < best_diff and diff <= max_diff:
            best_diff = diff
            best_val = arr[idx]
            best_bhk = bhk_type
    return best_bhk, (float(best_val) if best_val is not None else None)


def assign_bhk_carpet_match(village_df: pd.DataFrame,
                             rera_grand: pd.DataFrame,
                             rera_keywords: pd.DataFrame,
                             bhk_max_diff: float = 5) -> pd.DataFrame:
    """Stages 1+2+3: exact -> closest -> skip-type retry BHK matching."""

    keyword_map = rera_keywords.set_index('Keywords')['BHK'].to_dict()

    def normalize_key(key):
        return _normalize_bhk_key(key, keyword_map)

    def process_row(i, carpet_raw, building_raw, parse_cache):
        try:
            carpet = round(float(carpet_raw), 2)
            if np.isnan(carpet):
                return i, None
        except (ValueError, TypeError):
            return i, None

        building_info = parse_cache.get(building_raw)
        if not building_info:
            return i, None

        cleaned = {k: _clean_bhk_values(v) for k, v in building_info.items()}
        bhk = None

        for key, values in cleaned.items():         # Stage 1: exact match
            if carpet in values:
                bhk = normalize_key(key)

        if bhk is None:                             # Stage 2: closest match
            raw_bhk, _ = _find_closest_bhk(carpet, cleaned, bhk_max_diff)
            if raw_bhk is not None:
                bhk = normalize_key(raw_bhk)

        if bhk and bhk.upper() in SKIP_BHK:        # Stage 3: retry without skip types
            filtered = {
                normalize_key(k): v for k, v in cleaned.items()
                if k.strip().upper() not in (SKIP_BHK | NULL_KEYS)
                and normalize_key(k).upper() not in SKIP_BHK
            }
            if filtered:
                new_bhk, _ = _find_closest_bhk(carpet, filtered, bhk_max_diff)
                bhk = new_bhk if (new_bhk and new_bhk.upper() not in SKIP_BHK) else None
            else:
                bhk = None

        final = bhk.upper() if bhk else None
        return i, (None if final in SKIP_BHK else final)

    # Extract first number from mixed strings
    village_df['net_carpet_area_sqmt'] = village_df['net_carpet_area_sqmt'].apply(
        lambda x: re.findall(r"[-+]?\d*\.?\d+|\d+", str(x))[0] if not isinstance(x, float) else x
    )

    # Make index datatype identical in both DataFrames
    village_df['index'] = pd.to_numeric(
        village_df['index'],
        errors='coerce'
    ).astype('Int64')

    rera_grand['index'] = pd.to_numeric(
        rera_grand['index'],
        errors='coerce'
    ).astype('Int64')

    village_df = village_df.merge(
        rera_grand[['index', 'building_wise_carpet_area']],
        on='index',
        how='left'
    )

    village_df.sort_values('index', inplace=True)
    village_df['BHK'] = None

    mask = village_df['building_wise_carpet_area'].notna() & (village_df['property_type'] == 'Flat')
    target = village_df[mask][['net_carpet_area_sqmt', 'building_wise_carpet_area']].copy()

    parse_cache = {}
    for raw in target['building_wise_carpet_area'].unique():
        try:
            parse_cache[raw] = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            parse_cache[raw] = None

    print("Pre-parsing building info...")
    print(f"Processing {len(target)} rows, {len(parse_cache)} unique building configs...")

    results = Parallel(n_jobs=-1, backend='threading', verbose=1)(
        delayed(process_row)(i, row['net_carpet_area_sqmt'], row['building_wise_carpet_area'], parse_cache)
        for i, row in target.iterrows()
    )
    valid = {i: bhk for i, bhk in results if bhk is not None}
    print(f"Matched {len(valid)} / {len(target)} rows")
    village_df.loc[list(valid.keys()), 'BHK'] = list(valid.values())

    village_df.loc[village_df['BHK'].isin(SKIP_BHK | {'FLAT'}), 'BHK'] = None
    return village_df


def _build_bhk_phase_data(rera_grand: pd.DataFrame) -> pd.DataFrame:
    phase_data_list = []
    for _, row in rera_grand.iterrows():
        data_str = row['carpet_wise_total_sold_units']
        data_list = data_str if isinstance(data_str, dict) else {}
        if isinstance(data_str, str):
            try:
                data_list = ast.literal_eval(data_str)
            except Exception:
                pass
        for phase, phase_data in data_list.items():
            if isinstance(phase_data, list) and phase_data:
                for item in phase_data[0]:
                    phase_data_list.append({
                        "modified_project_name": row["modified_project_name"],
                        "Rera_Location": row["rera_location"],
                        "Phase": phase, "Data": item,
                    })
    return pd.DataFrame(phase_data_list)


def _reshape_bhk_row(row):
    new_rows = []
    if isinstance(row["Data"], dict):
        for bhk, data in row["Data"].items():
            if isinstance(data, dict):
                for carpet, values in data.items():
                    if isinstance(values, list) and len(values) == 2:
                        new_rows.append({
                            "modified_project_name": row["modified_project_name"],
                            "Rera_Location": row["Rera_Location"],
                            "Phase": row["Phase"],
                            "BHK": bhk, "carpet_sqmt": carpet,
                        })
    return pd.DataFrame(new_rows) if new_rows else None


def assign_bhk_range_fallback(village_df: pd.DataFrame,
                               rera_grand: pd.DataFrame,
                               rera_keywords: pd.DataFrame) -> pd.DataFrame:
    """Stage 4: Percentile range fallback for Flat rows still without BHK."""
    try:
        rera_grand['carpet_wise_total_sold_units'] = rera_grand['carpet_wise_total_sold_units'].apply(safe_parse)
        rera_grand['index'] = rera_grand['index'].astype(int)
        rera_keywords = rera_keywords.apply(lambda c: c.str.upper().str.strip() if c.dtype == object else c)
        village_df['BHK'] = village_df['BHK'].str.title()

        df2 = _build_bhk_phase_data(rera_grand)
        if df2.empty:
            print("[WARN] No phase data — skipping range fallback")
            return village_df

        reshaped_list = df2.apply(_reshape_bhk_row, axis=1).dropna().tolist()
        if not reshaped_list:
            print("[WARN] No reshaped BHK rows — skipping range fallback")
            return village_df

        df_expanded = pd.concat(reshaped_list, ignore_index=True)

        df_expanded["BHK"] = df_expanded["BHK"].str.replace(" ", "").str.upper()
        rera_keywords["Keywords"] = rera_keywords["Keywords"].str.replace(" ", "")
        bhk_mapping = dict(zip(rera_keywords["Keywords"], rera_keywords["Final BHK"]))
        df_expanded["BHK_Modified"] = df_expanded["BHK"].map(bhk_mapping).fillna("UNDEFINED OTHERS")

        df_grouped = (
            df_expanded.groupby("BHK_Modified")["carpet_sqmt"]
            .agg(lambda x: [float(i) for i in x if str(i).replace('.', '', 1).isdigit()])
            .reset_index()
        )
        df_grouped = df_grouped[df_grouped["BHK_Modified"].isin(["1BHK", "2BHK", "3BHK"])].reset_index(drop=True)

        if len(df_grouped) < 3:
            print("[WARN] Not enough BHK rows for percentile ranges")
            return village_df

        df_grouped["p10"] = df_grouped["carpet_sqmt"].apply(
            lambda x: round(np.percentile(x, 10), 2) if x else None
        )
        df_grouped["p90"] = df_grouped["carpet_sqmt"].apply(
            lambda x: round(np.percentile(x, 90), 2) if x else None
        )

        ranges = {
            "<1BHK": (0, df_grouped.loc[0, "p10"]),
            "1BHK": (df_grouped.loc[0, "p10"], (df_grouped.loc[0, "p90"] + df_grouped.loc[1, "p10"]) / 2),
            "2BHK": ((df_grouped.loc[0, "p90"] + df_grouped.loc[1, "p10"]) / 2, (df_grouped.loc[1, "p90"] + df_grouped.loc[2, "p10"]) / 2),
            "3BHK": ((df_grouped.loc[1, "p90"] + df_grouped.loc[2, "p10"]) / 2, df_grouped.loc[2, "p90"]),
            ">3BHK": (df_grouped.loc[2, "p90"], float("inf")),
        }
        for label, (lo, hi) in ranges.items():
            print(f"  {label}: {round(lo, 2)} -> {round(hi, 2)}")

        def assign_bhk_range(carpet_area):
            for bhk, (low, high) in ranges.items():
                if float(low) <= carpet_area < float(high):
                    return bhk
            return None

        village_df['BHK'] = village_df.apply(
            lambda row: assign_bhk_range(row['net_carpet_area_sqmt'])
            if pd.isna(row['BHK']) and row['property_type'] == 'Flat'
            else row['BHK'],
            axis=1
        )

    except Exception as e:
        print(f"[WARN] BHK range fallback failed: {e}")

    return village_df


def finalise_bhk(village_df: pd.DataFrame) -> pd.DataFrame:
    village_df['BHK'] = village_df['BHK'].astype(str).str.title().str.strip()
    village_df['BHK'] = village_df['BHK'].replace({'None': None, 'Nan': None, '': None})
    village_df['BHK'] = np.where(village_df['BHK'].isna(), village_df['property_type'], village_df['BHK'])
    village_df['BHK'] = village_df['BHK'].str.upper()

    village_df['unit_number'] = village_df['unit_number'].astype(str)
    village_df.loc[village_df['unit_number'] == 'nan', 'unit_number'] = None
    return village_df

def safe_parse(x):
    """Parse a stringified Python literal safely; return None on failure."""
    if pd.isna(x):
        return None
    if isinstance(x, str):
        x = x.replace("''", "'")
        try:
            return ast.literal_eval(x)
        except Exception as e:
            print(f"Error parsing: {str(x)[:80]} | {e}")
    return x

def process_rera_matching(
    df: pd.DataFrame,
    city: str = "Pune",
    rera_grand_path: str = None,
    rera_keywords_path: str = None,
    bhk_max_diff: float = 5,
) -> pd.DataFrame:
    """Takes in-memory DataFrame (df) from Step 10/11 and runs RERA matching, returning the updated df."""
    df = df.copy()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if rera_grand_path is None:
        try:
            from city_config import resolve_rera_grand_path
            rera_grand_path = resolve_rera_grand_path(city)
        except Exception:
            pass

    if rera_grand_path is None or not os.path.exists(rera_grand_path):
        raise FileNotFoundError(
            f"RERA Grand dataset not found for city '{city}'. "
            f"Please ensure 'rera_grand_file' is configured in city_config.py or placed in {base_dir}"
        )

    if rera_keywords_path is None:
        candidate = os.path.join(base_dir, "RERA_All_Keywords_BHK_Prop_Type.xlsx")
        rera_keywords_path = candidate if os.path.exists(candidate) else "RERA_All_Keywords_BHK_Prop_Type.xlsx"

    print(f"[RERA] Reading RERA grand reference dataset: {os.path.basename(rera_grand_path)}...")
    rera_grand = pd.read_excel(rera_grand_path)

    # Standardize column names (strip whitespace)
    rera_grand.columns = [c.strip() if isinstance(c, str) else c for c in rera_grand.columns]

    rera_grand = rera_grand[[
        'index', 'modified_project_name', 'rera_location_v1',
        'rera_location', 'project_lat', 'project_lng',
        'bhk_wise_ca', 'carpet_wise_total_sold_units', 'project_type'
    ]]
    rera_grand = rera_grand[rera_grand['modified_project_name'] != 0]

    # Defensive coordinate cleaning (handles strings with comma e.g. "19.08, 72.90")
    def _clean_coord(v):
        if pd.isna(v):
            return np.nan
        if isinstance(v, str) and ',' in v:
            parts = v.split(',')
            try:
                return float(parts[0].strip())
            except Exception:
                return np.nan
        try:
            return float(v)
        except Exception:
            return np.nan

    rera_grand['project_lat'] = rera_grand['project_lat'].apply(_clean_coord)
    rera_grand['project_lng'] = rera_grand['project_lng'].apply(_clean_coord)

    merged_df = assign_rera_index(df, rera_grand, city)
    print("Total  Index found in merged df ", merged_df['index'].unique())

    # 3.7 BHK
    rera_grand['bhk_wise_ca'] = rera_grand['bhk_wise_ca'].apply(safe_parse)
    rera_grand['building_wise_carpet_area'] = rera_grand['bhk_wise_ca'].apply(combine_columns)

    rera_keywords = pd.read_excel(rera_keywords_path)
    rera_keywords['Keywords'] = rera_keywords['Keywords'].str.upper().str.strip()
    rera_keywords['Final BHK'] = rera_keywords['Final BHK'].str.upper().str.strip()
    rera_keywords['Final Property Type'] = rera_keywords['Final Property Type'].str.upper().str.strip()

    village_df = assign_bhk_carpet_match(merged_df, rera_grand, rera_keywords, bhk_max_diff)
    village_df = assign_bhk_range_fallback(village_df, rera_grand, rera_keywords)
    df = finalise_bhk(village_df)

    return df


# Alias for compatibility
process_dataframe = process_rera_matching