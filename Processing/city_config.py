"""
City-specific configuration module for Pune, Mumbai, Thane, and other cities.
Centralizes:
1. Google Drive URLs (Raw Input, Manual Correction, Final Processed)
2. Database City IDs (public.dim_city)
3. RERA reference file mappings
4. City divisors imported from divisor.py
"""

import re
from divisor import SALEABLE_TO_CARPET_DIVISOR_BY_CITY

def extract_folder_id(url_or_id: str) -> str:
    """Extracts Google Drive folder ID from a URL or raw ID string."""
    if not url_or_id or not str(url_or_id).strip():
        return ""
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", str(url_or_id))
    return match.group(1) if match else str(url_or_id).strip()


CITY_CONFIG = {
    "pune": {
        "city_id": 9,
        "display_name": "Pune",
        # 1. Raw Input / LLM Processed Drive Folder
        "input_drive_url": "https://drive.google.com/drive/folders/1i-dPwAQce86kR552YF03XcvLHsOoDjb-?usp=drive_link",
        # 2. Manually Corrected Drive Folder
        "manual_correction_drive_url": "https://drive.google.com/drive/folders/1oQ3JQ_v9shWZQlW4JYDpLPXKFOEdAqRW?usp=drive_link",
        # 3. Final Processed File Drive Folder
        "final_drive_url": "https://drive.google.com/drive/folders/1l-HFh36Yk8pSs-NmoSK60if6cP2cjztM",
        # RERA Grand reference Excel file
        "rera_grand_file": "Pune RERA GRAND EXCEL VERSION 9.xlsx",
        # Divisor
        "saleable_to_carpet_divisor": SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get("pune", 1.35),
    },
    "mumbai": {
        "city_id": 8,
        "display_name": "Mumbai",
        # Main Parent Mumbai Folder
        "parent_drive_url": "https://drive.google.com/drive/folders/17ctyRJe8VMkH0556Ayu2syiVGZiu5zot?usp=drive_link",
        # 2. LLM Processed Data (Raw Input)
        "input_drive_url": "https://drive.google.com/drive/folders/1rT8PvmuS_s03yrsMvK93luMghbE-9rwD?usp=drive_link",
        # 3. Manually Corrected
        "manual_correction_drive_url": "https://drive.google.com/drive/folders/1ywb1-CSRDXNV80Yc8AXYm5Bgze34TXFA?usp=drive_link",
        # 4. Final Processed File
        "final_drive_url": "https://drive.google.com/drive/folders/1Fxf1yTUo4FZWRHjm_XrpA7jq93kG7diO?usp=drive_link",
        "rera_grand_file": None,
        "saleable_to_carpet_divisor": SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get("mumbai", 1.45),
    },
    "thane": {
        "city_id": 12,
        "display_name": "Thane",
        # Set to None or empty until Thane Google Drive folders are created
        "input_drive_url": None,
        "manual_correction_drive_url": None,
        "final_drive_url": None,
        "rera_grand_file": None,
        "saleable_to_carpet_divisor": SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get("thane", 1.4),
    },
}

# Add precomputed folder IDs and city keys
for _city, _cfg in CITY_CONFIG.items():
    _cfg["key"] = _city
    if "parent_drive_url" in _cfg:
        _cfg["parent_drive_id"] = extract_folder_id(_cfg.get("parent_drive_url"))
    _cfg["input_drive_id"] = extract_folder_id(_cfg.get("input_drive_url"))
    _cfg["manual_correction_drive_id"] = extract_folder_id(_cfg.get("manual_correction_drive_url"))
    _cfg["final_drive_id"] = extract_folder_id(_cfg.get("final_drive_url"))


def get_city_config(city_identifier: str | int = "pune") -> dict:
    """
    Returns the configuration dictionary for a given city name, city ID, or alias.
    Defaults to Pune if not found.
    """
    if city_identifier is None:
        return CITY_CONFIG["pune"]

    cid_str = str(city_identifier).strip().lower()

    # Match by key (e.g. "pune", "mumbai", "thane")
    if cid_str in CITY_CONFIG:
        return CITY_CONFIG[cid_str]

    # Match by city_id (e.g. 9, 8, 12)
    for cfg in CITY_CONFIG.values():
        if str(cfg["city_id"]) == cid_str:
            return cfg

    # Partial / alias match
    for key, cfg in CITY_CONFIG.items():
        if key in cid_str or cid_str in key:
            return cfg

    # Fallback to Pune
    return CITY_CONFIG["pune"]
