"""
Outlier detection & update script (Python port of the SQL CTE pipeline).

For a given city_id:
  1. Fetches transactions joined with dim_city.
  2. Computes calc_rate = agreement_price / (net_carpet_area_sq_m * 10.764).
  3. Groups by (city, location, transaction_category, property_type) -
     for Dubai / Abu Dhabi, all locations are collapsed into '__ALL_LOCATIONS__'.
  4. Within each group: trims rows outside the [p1, p99] percentile band of
     calc_rate, computes the median of the trimmed rows, and derives
     lower_limit = median / 4, upper_limit = median * 4.
  5. Flags outliers (lower/upper/null-rate/Mumbai-low-price), with a
     Mumbai zero-area/zero-rate exception.
  6. Writes rate, is_outlier, outlier_type back to public.transactions,
     matched on transaction_id.

Install deps:  pip install psycopg2-binary pandas numpy
"""

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Database connection parameters (from pipeline_core to avoid interactive CLI prompt in project.py)
from pipeline_core import DB_PARAMS

# City configurations (from city_config.py)
try:
    from city_config import CITY_CONFIG
except ImportError:
    CITY_CONFIG = {
        "pune": {"city_id": 9, "display_name": "Pune"},
        "mumbai": {"city_id": 8, "display_name": "Mumbai"},
        "thane": {"city_id": 12, "display_name": "Thane"},
    }

# NOTE: CITY_ID and LOCATION_NAME are obtained dynamically from user selection
# (passed directly from project.py or server.py, or prompted interactively below).

GROUP_COLS = ["k_city", "k_loc", "k_cat", "k_ptype"]


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
ALL_LOCATIONS_CITIES = {"dubai", "abu_dhabi"}


def get_city_name(conn, city_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT city_name FROM public.dim_city WHERE city_id = %s", (city_id,))
        row = cur.fetchone()
        return row[0] if row else None


def fetch_data(conn, city_id: int, location_name: str | None = None, log_fn=None) -> pd.DataFrame:
    city_name = get_city_name(conn, city_id)
    city_clean = (city_name or "").strip().lower()

    if location_name and city_clean in ALL_LOCATIONS_CITIES:
        msg = f"City ID {city_id} ({city_name}) groups all locations together; pulling entire city dataset."
        print(f"Note: {msg}")
        if log_fn:
            log_fn(f"Step 20: ℹ️ {msg}", "info")
        location_name = None

    query = """
        SELECT
            t.transaction_id,
            c.city_name,
            t.location_name,
            t.transaction_category,
            t.property_type,
            t.agreement_price,
            t.net_carpet_area_sq_m
        FROM public.transactions t
        JOIN public.dim_city c ON c.city_id = t.city_id
        WHERE t.city_id = %s
    """
    params = [city_id]

    if location_name:
        query += " AND lower(trim(t.location_name)) = lower(trim(%s))"
        params.append(location_name)

    target_desc = f"location='{location_name}'" if location_name else f"all locations in {city_name or 'City ' + str(city_id)}"
    if log_fn:
        log_fn(f"Step 20: 🔍 Fetching transactions from public.transactions for {target_desc}...", "info")

    df = pd.read_sql(query, conn, params=tuple(params))
    if log_fn:
        log_fn(f"Step 20: 📥 Fetched {len(df):,} transactions from public.transactions.", "info")

    return df


# --------------------------------------------------------------------------- #
# Compute
# --------------------------------------------------------------------------- #
def compute_outliers(df: pd.DataFrame, save_merged_path: str | None = None, log_fn=None) -> pd.DataFrame:
    df = df.copy()

    if log_fn:
        log_fn(f"Step 20: ⚙️ Calculating rate percentiles (p1/p99) and median boundaries...", "info")

    # --- normalized helper columns -----------------------------------------
    df["city_name_clean"] = df["city_name"].astype(str).str.strip().str.lower()
    df["category_clean"] = df["transaction_category"].astype(str).str.strip().str.lower()

    df["is_valid"] = (df["agreement_price"] > 0) & (df["net_carpet_area_sq_m"] > 0)

    df["calc_rate"] = np.where(
        df["is_valid"],
        df["agreement_price"] / (df["net_carpet_area_sq_m"] * 10.764),
        np.nan,
    )

    # Dubai / Abu Dhabi -> collapse all locations into one bucket
    df["group_location_name"] = np.where(
        df["city_name_clean"].isin(["dubai", "abu_dhabi"]),
        "__ALL_LOCATIONS__",
        df["location_name"],
    )

    # grouping keys (COALESCE(..., '~NULL~') equivalent)
    df["k_city"] = df["city_name"].fillna("~NULL~")
    df["k_loc"] = df["group_location_name"].fillna("~NULL~")
    df["k_cat"] = df["transaction_category"].fillna("~NULL~")
    df["k_ptype"] = df["property_type"].fillna("~NULL~")

    # --- group_stats: p1 / p99 over valid rows ------------------------------
    valid_df = df[df["is_valid"]]
    group_stats = (
        valid_df.groupby(GROUP_COLS)["calc_rate"]
        .quantile([0.01, 0.99])
        .unstack()
        .rename(columns={0.01: "p1", 0.99: "p99"})
        .reset_index()
    )
    df = df.merge(group_stats, on=GROUP_COLS, how="left")

    # --- trimmed + median_stats ---------------------------------------------
    trimmed_mask = (
        df["is_valid"] & (df["calc_rate"] >= df["p1"]) & (df["calc_rate"] <= df["p99"])
    )
    trimmed = df[trimmed_mask]
    median_stats = (
        trimmed.groupby(GROUP_COLS)["calc_rate"].median().reset_index()
        .rename(columns={"calc_rate": "median_rate"})
    )
    df = df.merge(median_stats, on=GROUP_COLS, how="left")

    df["lower_limit"] = df["median_rate"] / 4
    df["upper_limit"] = df["median_rate"] * 4

    # --- flags ----------------------------------------------------------------
    df["is_lower"] = df["is_valid"] & (df["calc_rate"] < df["lower_limit"])
    df["is_upper"] = df["is_valid"] & (df["calc_rate"] > df["upper_limit"])
    df["is_rate_null"] = df["calc_rate"].isna()

    df["is_mumbai_low_price"] = (
        (df["city_name_clean"] == "mumbai")
        & (df["category_clean"] == "sale")
        & (df["agreement_price"] < 100000)
    )

    area_or_price_zero = (
        df["net_carpet_area_sq_m"].isna() | (df["net_carpet_area_sq_m"] == 0)
    ) | (df["agreement_price"].isna() | (df["agreement_price"] == 0))

    df["is_mumbai_zero_exception"] = (
        (df["city_name_clean"] == "mumbai")
        & (df["calc_rate"].isna() | (df["calc_rate"] == 0))
        & area_or_price_zero
    )

    # --- final outlier flag / type --------------------------------------------
    df["is_outlier"] = np.where(
        df["is_mumbai_zero_exception"],
        False,
        df["is_lower"] | df["is_upper"] | df["is_rate_null"] | df["is_mumbai_low_price"],
    )

    def outlier_type(row):
        if row["is_mumbai_zero_exception"]:
            return "Mumbai Zero Area & Rate - Not Outlier"
        if not row["is_valid"]:
            return "Invalid/Excluded"
        if row["is_mumbai_low_price"]:
            return "Mumbai Low Price Outlier (Sale < 1L)"
        if row["is_lower"]:
            return "Lower Outlier"
        if row["is_upper"]:
            return "Upper Outlier"
        return "Normal"

    df["outlier_type"] = df.apply(outlier_type, axis=1)

    if save_merged_path:
        if save_merged_path.lower().endswith(".csv"):
            df.to_csv(save_merged_path, index=False)
        else:
            df.to_excel(save_merged_path, index=False)
        msg = f"Saved merged outlier analysis to: {save_merged_path}"
        print(msg)
        if log_fn:
            log_fn(f"Step 20: 📄 {msg}", "success")

    result = df[["transaction_id", "calc_rate", "is_outlier", "outlier_type"]].rename(
        columns={"calc_rate": "rate"}
    )
    result["rate"] = result["rate"].where(result["rate"].notna(), None)

    n_outliers = int(result["is_outlier"].sum())
    lower_cnt = int((result["outlier_type"] == "Lower Outlier").sum())
    upper_cnt = int((result["outlier_type"] == "Upper Outlier").sum())
    normal_cnt = int((result["outlier_type"] == "Normal").sum())
    invalid_cnt = int((result["outlier_type"] == "Invalid/Excluded").sum())
    if log_fn:
        pct = (n_outliers / max(1, len(result))) * 100
        log_fn(f"Step 20: 📊 Outliers breakdown: {n_outliers:,} flagged ({pct:.1f}%) | Normal: {normal_cnt:,} | Lower: {lower_cnt:,} | Upper: {upper_cnt:,} | Invalid/Excluded: {invalid_cnt:,}", "info")

    return result


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
def update_db(conn, result_df: pd.DataFrame, batch_size: int = 5000, log_fn=None, is_stopped_fn=None) -> None:
    records = [
        (int(row.transaction_id), row.rate, bool(row.is_outlier), row.outlier_type)
        for row in result_df.itertuples(index=False)
    ]
    total_records = len(records)
    if total_records == 0:
        return

    if log_fn:
        log_fn(f"Step 20: 💾 Updating {total_records:,} rows in public.transactions (batch size: {batch_size:,})...", "info")

    sql = """
        UPDATE public.transactions AS t
        SET rate = data.rate,
            is_outlier = data.is_outlier,
            outlier_type = data.outlier_type
        FROM (VALUES %s) AS data(transaction_id, rate, is_outlier, outlier_type)
        WHERE t.transaction_id = data.transaction_id
    """

    with conn.cursor() as cur:
        for i in range(0, total_records, batch_size):
            if is_stopped_fn and is_stopped_fn():
                if log_fn:
                    log_fn("Step 20: ⏹️ Outlier update cancelled by user.", "warning")
                conn.rollback()
                return
            chunk = records[i : i + batch_size]
            execute_values(cur, sql, chunk, template="(%s, %s, %s, %s)", page_size=batch_size)
            conn.commit()
            processed = min(i + batch_size, total_records)
            pct = int((processed / total_records) * 100)
            if log_fn and (processed == total_records or i % (batch_size * 2) == 0):
                log_fn(f"Step 20: 💾 Updated {processed:,} / {total_records:,} rows ({pct}%)...", "info")

    if log_fn:
        log_fn(f"Step 20: ✓ Database update committed: {total_records:,} rows updated.", "success")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(
    city_id: int | None = None,
    location_name: str | None = None,
    db_params: dict | None = None,
    save_merged_path: str | None = None,
    log_fn=None,
    is_stopped_fn=None,
) -> None:
    if city_id is None:
        raise ValueError("city_id must be provided (e.g. Pune=9, Mumbai=8, Thane=12, Dubai=15).")

    conn_params = db_params or DB_PARAMS
    db_name = conn_params.get("database", "nilesh")

    if log_fn:
        log_fn(f"Step 20: 🔌 Connecting to PostgreSQL database '{db_name}' (host={conn_params.get('host', 'localhost')}:{conn_params.get('port', 5432)})...", "info")

    conn = psycopg2.connect(**conn_params)
    try:
        df = fetch_data(conn, city_id, location_name, log_fn=log_fn)
        if df.empty:
            where = f", location_name='{location_name}'" if location_name else ""
            msg = f"No transactions found for city_id={city_id}{where} in database '{db_name}'."
            print(msg)
            if log_fn:
                log_fn(f"Step 20: ⚠️ {msg}", "warning")
            return

        if is_stopped_fn and is_stopped_fn():
            if log_fn:
                log_fn("Step 20: ⏹️ Outlier detection stopped by user.", "warning")
            return

        result_df = compute_outliers(df, save_merged_path=save_merged_path, log_fn=log_fn)

        if is_stopped_fn and is_stopped_fn():
            if log_fn:
                log_fn("Step 20: ⏹️ Outlier detection stopped by user.", "warning")
            return

        update_db(conn, result_df, log_fn=log_fn, is_stopped_fn=is_stopped_fn)

        n_outliers = int(result_df["is_outlier"].sum())
        scope = f"city_id={city_id}" + (f", location='{location_name}'" if location_name else " (all locations)")
        print(f"{scope}: updated {len(result_df)} rows ({n_outliers} flagged as outliers).")
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Outlier detection & update")
    parser.add_argument("--city_id", type=int, default=None, help="Target city ID (e.g. Pune: 9, Mumbai: 8, Thane: 12)")
    parser.add_argument("--location", type=str, default=None, help="Location name (or None / all for all locations)")
    parser.add_argument("--save_excel", type=str, default=None, help="Optional file path to save merged outlier Excel report")
    args, _ = parser.parse_known_args()

    target_city_id = args.city_id
    if target_city_id is None:
        print("\n" + "=" * 55)
        print("  📊 OUTLIER DETECTION & UPDATE - CITY SELECTION")
        print("=" * 55)
        cities_list = list(CITY_CONFIG.values())
        for idx, cfg in enumerate(cities_list, 1):
            print(f"  [{idx}] {cfg.get('display_name', 'Unknown')} (City ID: {cfg.get('city_id')})")
        print(f"  [{len(cities_list) + 1}] Enter custom City ID")

        while target_city_id is None:
            choice = input(f"\nSelect target city (1-{len(cities_list) + 1}): ").strip()
            if choice.isdigit():
                c_idx = int(choice)
                if 1 <= c_idx <= len(cities_list):
                    target_city_id = cities_list[c_idx - 1]["city_id"]
                    print(f"  ✓ Selected City: {cities_list[c_idx - 1].get('display_name')} (ID: {target_city_id})")
                elif c_idx == len(cities_list) + 1:
                    custom_id = input("Enter custom numeric City ID: ").strip()
                    if custom_id.isdigit():
                        target_city_id = int(custom_id)
            if target_city_id is None:
                print("Invalid selection. Please enter a valid number.")

    target_location = args.location
    if target_location is None:
        loc_input = input("\nEnter location name to filter (press Enter for ALL locations): ").strip()
        target_location = loc_input if loc_input and loc_input.lower() not in ["none", "all", ""] else None
    else:
        target_location = None if target_location.lower() in ["none", "all", ""] else target_location

    main(city_id=target_city_id, location_name=target_location, save_merged_path=args.save_excel)