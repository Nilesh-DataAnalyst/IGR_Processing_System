import os, time, requests
import pandas as pd

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyBS63yAQTYMnYAKDv5gQ7G1Qw2ngup15-w")
CITY = "Pune, India"


def get_coordinates(project_name, location_name=None):
    if location_name and pd.notna(location_name) and str(location_name).strip():
        query = f"{project_name}, {str(location_name).strip()}, {CITY}"
    else:
        query = f"{project_name}, {CITY}"
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": "geometry,name,formatted_address,place_id",
        "key": GOOGLE_MAPS_API_KEY
    }

    try:
        data = requests.get(url, params=params, timeout=10).json()

        if data.get("status") == "OK" and data.get("candidates"):
            r = data["candidates"][0]
            loc = r["geometry"]["location"]

            return {
                "project_latitude": loc.get("lat"),
                "project_longitude": loc.get("lng"),
                "google_project_name": r.get("name"),
                "google_address": r.get("formatted_address"),
                "google_place_id": r.get("place_id"),
                "searched_query": query,
                "coordinate_status": "FOUND"
            }

        return {"searched_query": query, "coordinate_status": "NOT_FOUND"}

    except Exception as e:
        return {
            "searched_query": query,
            "coordinate_status": "FAILED",
            "coordinate_error": str(e)
        }


def populate_project_coordinates(df):
    df = df.copy()

    for c in ["project_name", "location_name"]:
        df[c] = df[c].astype("string").str.strip()

    for c in ["project_latitude", "project_longitude"]:
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce")

    mask = (
        df["project_name"].notna()
        & df["location_name"].notna()
        & (df["project_latitude"].isna() | df["project_longitude"].isna())
    )

    projects = df.loc[
        mask, ["project_name", "location_name"]
    ].drop_duplicates()

    results = []

    for i, row in enumerate(projects.itertuples(index=False), 1):
        print(f"[{i}/{len(projects)}] {row.project_name} - {row.location_name}")

        r = get_coordinates(row.project_name, row.location_name)
        r.update({
            "project_name": row.project_name,
            "location_name": row.location_name
        })

        results.append(r)
        time.sleep(0.1)

    if results:
        lookup = pd.DataFrame(results)

        # Avoid duplicate coordinate columns during merge
        lookup = lookup.rename(columns={
            "project_latitude": "google_lat",
            "project_longitude": "google_long"
        })

        df = df.merge(
            lookup,
            on=["project_name", "location_name"],
            how="left",
            validate="many_to_one"
        )

        df["project_latitude"] = df["project_latitude"].fillna(df["google_lat"])
        df["project_longitude"] = df["project_longitude"].fillna(df["google_long"])

        df.drop(columns=["google_lat", "google_long"], inplace=True)

    return df