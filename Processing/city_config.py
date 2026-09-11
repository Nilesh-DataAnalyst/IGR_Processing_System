"""
City-specific configuration module for Pune, Mumbai, Thane, and other cities.
Centralizes:
1. Google Drive URLs (Raw Input, Manual Correction, Final Processed)
2. Database City IDs (public.dim_city)
3. RERA reference file mappings
4. City divisors imported from divisor.py
"""

import os
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
        "rera_grand_file": "mumbai RERA GRAND EXCEL VERSION.xlsx",
        "saleable_to_carpet_divisor": SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get("mumbai", 1.45),
        # Location-specific overrides
        "location_manual_correction_drive_urls": {
            "bandra": "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link",
        },
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

# Specific location Google Drive configurations (e.g. Bandra in Mumbai)
LOCATION_DRIVE_CONFIG = {
    "bandra": {
        "city_key": "mumbai",
        "city_id": 8,
        "display_name": "Bandra",
        "manual_correction_drive_url": "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link",
        "manual_correction_drive_id": "1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq",
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

    # Check location aliases (e.g. "bandra")
    if cid_str in LOCATION_DRIVE_CONFIG:
        loc_cfg = LOCATION_DRIVE_CONFIG[cid_str]
        parent_cfg = dict(CITY_CONFIG.get(loc_cfg.get("city_key", "mumbai"), CITY_CONFIG["mumbai"]))
        parent_cfg["manual_correction_drive_url"] = loc_cfg["manual_correction_drive_url"]
        parent_cfg["manual_correction_drive_id"] = loc_cfg.get("manual_correction_drive_id", extract_folder_id(loc_cfg["manual_correction_drive_url"]))
        parent_cfg["display_name"] = f"{loc_cfg.get('display_name', 'Bandra')} ({parent_cfg.get('display_name', 'Mumbai')})"
        return parent_cfg

    # Match by key (e.g. "pune", "mumbai", "thane")
    if cid_str in CITY_CONFIG:
        return CITY_CONFIG[cid_str]

    # Match by city_id (e.g. 9, 8, 12)
    for cfg in CITY_CONFIG.values():
        if str(cfg.get("city_id")) == cid_str:
            return cfg

    # Partial / alias match
    for key, cfg in CITY_CONFIG.items():
        if key in cid_str or cid_str in key:
            return cfg

    # Fallback to Pune
    return CITY_CONFIG["pune"]


def get_manual_correction_drive_url(
    city_identifier: str | int = None,
    location_name: str = None,
    file_path: str = None,
) -> str:
    """
    Returns the appropriate manual correction Google Drive folder URL.
    Prioritizes:
    1. Exact location match (e.g. Bandra -> https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link)
    2. Location keyword found in file_path
    3. Known city shortcut path in file_path (e.g. 1ywb1-CSRDXNV80Yc8AXYm5Bgze34TXFA for Mumbai)
    4. City configuration manual_correction_drive_url
    """
    # 1. Direct location_name lookup
    if location_name:
        loc_clean = str(location_name).strip().lower()
        if loc_clean in LOCATION_DRIVE_CONFIG:
            return LOCATION_DRIVE_CONFIG[loc_clean]["manual_correction_drive_url"]
        for k, v in LOCATION_DRIVE_CONFIG.items():
            if k in loc_clean or loc_clean in k:
                return v["manual_correction_drive_url"]

    # 2. Check file_path for location names
    if file_path:
        fp_lower = str(file_path).lower()
        for k, v in LOCATION_DRIVE_CONFIG.items():
            if k in fp_lower:
                return v["manual_correction_drive_url"]

        # Check if file_path is inside Mumbai's shortcut target or references Mumbai locations
        mumbai_mc_id = extract_folder_id(CITY_CONFIG["mumbai"]["manual_correction_drive_url"]).lower()
        if mumbai_mc_id and mumbai_mc_id in fp_lower:
            return CITY_CONFIG["mumbai"]["manual_correction_drive_url"]

        mumbai_locations = ["mumbai", "borivali", "andheri", "kurla", "chembur", "dadar", "goregaon", "malad", "powai"]
        if any(mloc in fp_lower for mloc in mumbai_locations):
            return CITY_CONFIG["mumbai"]["manual_correction_drive_url"]

    # 3. City lookup
    cfg = get_city_config(city_identifier) if city_identifier is not None else CITY_CONFIG["pune"]
    return cfg.get("manual_correction_drive_url") or CITY_CONFIG["pune"]["manual_correction_drive_url"]


def resolve_rera_grand_path(city_identifier: str | int = None) -> str | None:
    """
    Resolves the local file path to the RERA Grand Excel dataset for the specified city.
    Checks:
    1. Configured 'rera_grand_file' in city_config (as absolute path or relative to Processing directory).
    2. Auto-discovery in Processing directory matching city name and 'rera'.
    3. Pune default fallback if city is Pune.
    """
    cfg = get_city_config(city_identifier) if city_identifier is not None else CITY_CONFIG["pune"]
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Configured path
    configured = cfg.get("rera_grand_file")
    if configured:
        clean = str(configured).strip().strip('"').strip("'")
        if os.path.isabs(clean) and os.path.isfile(clean):
            return clean
        candidate = os.path.join(base_dir, clean)
        if os.path.isfile(candidate):
            return candidate
        if os.path.isfile(clean):
            return os.path.abspath(clean)

    # 2. Auto-discovery in base_dir by city name/alias
    city_key = str(cfg.get("key", city_identifier or "")).lower()
    city_display = str(cfg.get("display_name", "")).lower()
    targets = {t for t in [city_key, city_display] if t and len(t) > 2}
    if targets:
        try:
            for f in os.listdir(base_dir):
                f_lower = f.lower()
                if f_lower.endswith((".xlsx", ".xls")) and not f.startswith("~$"):
                    if "rera" in f_lower and any(t in f_lower for t in targets):
                        return os.path.join(base_dir, f)
        except Exception:
            pass

    # 3. Pune default fallback
    if any(t == "pune" for t in targets):
        pune_default = os.path.join(base_dir, "Pune RERA GRAND EXCEL VERSION 9.xlsx")
        if os.path.isfile(pune_default):
            return pune_default

    return None


def render_correction_email_html(
    loc_intro: str,
    file_name: str,
    drive_url: str,
    file_path: str,
    delivery_note_html: str,
    deadline_banner_html: str = "",
) -> str:
    """
    Renders the HTML email template by reading email_template.html (located in web/ or Processing root)
    and replacing placeholders with actual transaction and file details.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "web", "email_template.html"),
        os.path.join(base_dir, "email_template.html"),
    ]
    template_html = None
    for cand in candidates:
        if os.path.isfile(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    template_html = f.read()
                break
            except Exception:
                pass

    if not template_html:
        template_html = """<!DOCTYPE html><html><body style="font-family:sans-serif;padding:16px;">
        <p>Hello,</p><p><strong>{{loc_intro}}</strong> is ready for review.</p>
        {{deadline_banner_html}}
        <p><strong>📄 File:</strong> {{file_name}}</p>
        <p><strong>🌐 Google Drive Folder:</strong> <a href="{{drive_url}}">{{drive_url}}</a></p>
        <p><strong>📂 Local / Drive Path:</strong> <code>{{file_path}}</code></p>
        <p>{{delivery_note_html}}</p>
        <p>Best regards,<br><strong>Nilesh K.</strong></p>
        </body></html>"""

    replacements = {
        "{{loc_intro}}": loc_intro or "",
        "{{file_name}}": file_name or "",
        "{{drive_url}}": drive_url or "",
        "{{file_path}}": file_path or "",
        "{{delivery_note_html}}": delivery_note_html or "",
        "{{deadline_banner_html}}": deadline_banner_html or "",
    }
    html_output = template_html
    for key, val in replacements.items():
        html_output = html_output.replace(key, str(val))
    return html_output


