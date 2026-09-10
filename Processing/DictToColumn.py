import pandas as pd
import ast
import json
import re


# =========================================================
# CONFIG
# =========================================================

standard_columns = [
    "project_name_en", "project_name_original",
    "building_name_en", "building_name_original",
    "property_type", "transaction_type",

    "flat_no", "floor_no", "wing_no", "plot_no",
    "survey_no", "CTS_no", "block_no",
    "society_name", "society_name_en", "society_name_original",

    "carpet_area", "builtup_area", "super_builtup_area",
    "saleable_area", "terrace_area", "balcony_area",
    "total_area", "plot_area", "parking_area",
    "covered_parking_area", "car_parking_area",
    "garden_area", "gallery_area", "loft_area",
    "office_area", "shop_area", "mezzanine_area", "open_area",

    "full_address_en", "full_address_original",
    "road_name_en", "road_name_original",
    "locality_en", "locality_original",
    "city_en", "city_original",
    "pincode",
    "taluka_en", "taluka_original",
    "district_en", "district_original",
    "state_en", "state_original",

    "registration_no", "document_date",
    "owner_name", "owner_name_original",
    "remarks", "remarks_original",

    "request_number", "input_tokens",
    "output_tokens", "total_tokens",
]


columns_to_remove = [
    "AREA DETAILS_enclosed_balcony_area",
    "AREA DETAILS_dry_balcony_area",
    "AREA DETAILS_flat_area",
    "AREA DETAILS_builtup_area_sqft",
    "AREA DETAILS_parking_area_sqft",
    "OTHER DETAILS_manpa_zone_no",
    "OTHER DETAILS_property_number",
    "AREA DETAILS_plot_area_sqm",
    "AREA DETAILS_plot_area_sqft",
    "AREA DETAILS_plot_area_2",
    "AREA DETAILS_plot_area_3",
    "AREA DETAILS_plot_area_ft",
    "AREA DETAILS_plot_area_ft2",
    "AREA DETAILS_area_mentioned",
    "AREA DETAILS_dry_area",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "transaction_type",
    "remarks",
    "remarks_original",
    "request_number",
]


aliases = {
    "cts_no": "CTS_no",
    "cts number": "CTS_no",
    "built_up_area": "builtup_area",
    "built-up_area": "builtup_area",
    "super_built_up_area": "super_builtup_area",
    "car_park_area": "car_parking_area",
    "covered_car_parking_area": "covered_parking_area",
    "parking": "parking_area",
    "gallery": "gallery_area",
}


# =========================================================
# HELPERS
# =========================================================

def parse_llm_output(value):

    if value is None or pd.isna(value):
        return None

    if isinstance(value, dict):
        return value

    text = str(value).strip()

    if not text:
        return None

    text = re.sub(
        r"^\s*```(?:json|python)?\s*|\s*```\s*$",
        "",
        text,
        flags=re.I
    )

    start, end = text.find("{"), text.rfind("}")

    if start == -1 or end <= start:
        return None

    text = text[start:end + 1]

    # Python dict
    try:
        data = ast.literal_eval(text)
        if isinstance(data, dict):
            return data
    except (ValueError, SyntaxError, TypeError):
        pass

    # JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # Fix JSON keywords
    try:
        fixed = re.sub(r"\bnull\b", "None", text)
        fixed = re.sub(r"\btrue\b", "True", fixed, flags=re.I)
        fixed = re.sub(r"\bfalse\b", "False", fixed, flags=re.I)

        data = ast.literal_eval(fixed)

        if isinstance(data, dict):
            return data

    except (ValueError, SyntaxError, TypeError):
        pass

    return None


def normalize_section_name(section):

    section = str(section).strip()
    section = re.sub(r"\s*\([^)]*\)\s*", "", section)
    section = re.sub(r"_\d+$", "", section)

    return section.strip().upper()


def clean_key_name(key):

    key = str(key).strip()

    return aliases.get(
        key.lower(),
        key
    )


def extract_standard_data(data):

    result = {
        col: None
        for col in standard_columns
    }

    extra = {}

    if not isinstance(data, dict):
        return result, extra

    for section, value in data.items():

        section_name = normalize_section_name(section)

        # Nested dictionary
        if isinstance(value, dict):

            for key, val in value.items():

                key = clean_key_name(key)

                if key in result:

                    if result[key] in (None, ""):
                        result[key] = val

                else:

                    extra[
                        f"{section_name}_{key}"
                    ] = val

        # Flat value
        else:

            key = clean_key_name(section)

            if key in result:

                if result[key] in (None, ""):
                    result[key] = value

            else:
                extra[key] = value

    return result, extra


# =========================================================
# MAIN PROCESS
# =========================================================

def process_dict_to_column(input_file):

    print(f"\nReading input file:\n{input_file}")

    df = pd.read_excel(input_file)

    llm_column = "llm_output"

    if llm_column not in df.columns:
        raise KeyError(
            f"'{llm_column}' column not found."
        )

    standard_rows = []
    extra_rows = []
    invalid_rows = []

    # -----------------------------------------------------
    # Parse rows
    # -----------------------------------------------------

    for index, value in df[llm_column].items():

        parsed = parse_llm_output(value)

        if parsed is None:

            standard_rows.append(
                {col: None for col in standard_columns}
            )

            extra_rows.append({})

            if pd.notna(value) and str(value).strip():

                invalid_rows.append({
                    "excel_row": index + 2,
                    "llm_output": str(value)
                })

            continue

        standard_data, extra_data = extract_standard_data(
            parsed
        )

        standard_rows.append(standard_data)
        extra_rows.append(extra_data)


    # -----------------------------------------------------
    # Create parsed DataFrames
    # -----------------------------------------------------

    standard_df = pd.DataFrame(
        standard_rows,
        columns=standard_columns
    )

    extra_df = pd.DataFrame(extra_rows)


    # -----------------------------------------------------
    # Keep only original source columns
    # -----------------------------------------------------

    generated_prefixes = [
        "PROJECT/BUILDING DETAILS",
        "PROPERTY IDENTIFICATION",
        "AREA DETAILS",
        "LOCATION & ADDRESS",
        "OTHER DETAILS",
        "_token_usage",
        "SHOP/OFFICE DETAILS",
    ]


    original_columns = [

        col for col in df.columns

        if (
            col == llm_column

            or (
                col not in standard_columns

                and not any(
                    col.startswith(prefix)
                    for prefix in generated_prefixes
                )
            )
        )
    ]


    clean_original_df = df[
        original_columns
    ].copy()


    # -----------------------------------------------------
    # Combine
    # -----------------------------------------------------

    result_df = pd.concat(
        [
            clean_original_df.reset_index(drop=True),
            standard_df.reset_index(drop=True),
            extra_df.reset_index(drop=True),
        ],
        axis=1
    )


    # -----------------------------------------------------
    # Remove duplicate columns
    # -----------------------------------------------------

    result_df = result_df.loc[
        :,
        ~result_df.columns.duplicated()
    ]


    # -----------------------------------------------------
    # Remove unwanted columns
    # -----------------------------------------------------

    result_df.drop(
        columns=[
            col
            for col in columns_to_remove
            if col in result_df.columns
        ],
        inplace=True
    )


    # -----------------------------------------------------
    # Invalid row details
    # -----------------------------------------------------

    result_df.attrs["invalid_rows"] = pd.DataFrame(
        invalid_rows,
        columns=[
            "excel_row",
            "llm_output"
        ]
    )


    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print(
        f"✅ DictToColumn completed | "
        f"Rows: {len(result_df):,} | "
        f"Parsed: {len(df) - len(invalid_rows):,} | "
        f"Invalid: {len(invalid_rows):,} | "
        f"Columns: {len(result_df.columns):,}"
    )


    # Send directly to main file
    return result_df