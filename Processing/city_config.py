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


DIM_CITY_CONFIG = {
    1: {"city_id": 1, "key": "abu_dhabi", "display_name": "Abu_Dhabi", "saleable_to_carpet_divisor": 1.0, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    2: {"city_id": 2, "key": "ahmedabad", "display_name": "Ahmedabad", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    3: {"city_id": 3, "key": "banglore", "display_name": "Banglore", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    5: {"city_id": 5, "key": "ghaziabad", "display_name": "Ghaziabad", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    6: {"city_id": 6, "key": "hyderabad", "display_name": "Hyderabad", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    7: {"city_id": 7, "key": "medchal_malkajgiri", "display_name": "Medchal_Malkajgiri", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    8: {"city_id": 8, "key": "mumbai", "display_name": "Mumbai", "saleable_to_carpet_divisor": 1.45, "input_drive_url": CITY_CONFIG["mumbai"]["input_drive_url"], "manual_correction_drive_url": CITY_CONFIG["mumbai"]["manual_correction_drive_url"], "final_drive_url": CITY_CONFIG["mumbai"]["final_drive_url"]},
    9: {"city_id": 9, "key": "pune", "display_name": "Pune", "saleable_to_carpet_divisor": 1.35, "input_drive_url": CITY_CONFIG["pune"]["input_drive_url"], "manual_correction_drive_url": CITY_CONFIG["pune"]["manual_correction_drive_url"], "final_drive_url": CITY_CONFIG["pune"]["final_drive_url"]},
    10: {"city_id": 10, "key": "rangareddy", "display_name": "Rangareddy", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    11: {"city_id": 11, "key": "sangareddy", "display_name": "Sangareddy", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    12: {"city_id": 12, "key": "thane", "display_name": "Thane", "saleable_to_carpet_divisor": 1.40, "input_drive_url": CITY_CONFIG["thane"]["input_drive_url"], "manual_correction_drive_url": CITY_CONFIG["thane"]["manual_correction_drive_url"], "final_drive_url": CITY_CONFIG["thane"]["final_drive_url"]},
    13: {"city_id": 13, "key": "yadadri_bhuvanagiri", "display_name": "Yadadri_Bhuvanagiri", "saleable_to_carpet_divisor": 1.35, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
    15: {"city_id": 15, "key": "dubai", "display_name": "Dubai", "saleable_to_carpet_divisor": 1.0, "input_drive_url": None, "manual_correction_drive_url": None, "final_drive_url": None},
}


def get_city_config(city_identifier: str | int = "pune") -> dict:
    """
    Returns the configuration dictionary for a given city name, city ID, or alias.
    Matches against CITY_CONFIG and all database cities in DIM_CITY_CONFIG.
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

    # Match by integer city_id (e.g. 15 for Dubai, 1 for Abu Dhabi, 9 for Pune)
    try:
        cid_int = int(cid_str)
        if cid_int in DIM_CITY_CONFIG:
            dcfg = dict(DIM_CITY_CONFIG[cid_int])
            if dcfg["key"] in CITY_CONFIG:
                return CITY_CONFIG[dcfg["key"]]
            return dcfg
    except (ValueError, TypeError):
        pass

    # Match by city_id string in CITY_CONFIG (e.g. 9, 8, 12)
    for cfg in CITY_CONFIG.values():
        if str(cfg.get("city_id")) == cid_str:
            return cfg

    # Match by name / key in DIM_CITY_CONFIG
    for dcfg in DIM_CITY_CONFIG.values():
        if dcfg["key"] == cid_str or dcfg["display_name"].lower() == cid_str:
            if dcfg["key"] in CITY_CONFIG:
                return CITY_CONFIG[dcfg["key"]]
            return dict(dcfg)

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


def send_final_checker_email(
    file_path: str,
    city_name: str,
    location_name: str = None,
    row_count: int = None,
    drive_url: str = None,
    checker_email: str = "deeksha@sigmavalue.co.in",
    cc_emails: list = None,
) -> dict:
    """
    Sends the final processed file to the checker person (deeksha@sigmavalue.co.in)
    via Gmail SMTP with the Excel file attached (if <= 24.5MB) and Google Drive link.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    sender_email = "nilesh@sigmavalue.co.in"
    sender_password = "nvlf igcl tyxm nnwo"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    recipient = checker_email.strip() if checker_email else "deeksha@sigmavalue.co.in"
    if cc_emails is None:
        cc_emails = ["nilesh@sigmavalue.co.in"]
    clean_cc = [c.strip() for c in cc_emails if c and c.strip()]
    all_recipients = list(dict.fromkeys([recipient] + clean_cc))

    file_name = os.path.basename(file_path) if file_path else "final_processed.xlsx"
    loc_display = location_name if location_name else "All Locations"
    city_display = str(city_name or "Target City").title()
    rows_display = f"{row_count:,}" if isinstance(row_count, int) else (str(row_count) if row_count else "N/A")
    drive_link_display = drive_url or "Google Drive folder link"

    subject = f"[Final Processed File - Ready for Verification] {city_display} - {loc_display} ({file_name})"

    # Check file size for attachment
    is_attached = False
    file_exists = file_path and os.path.isfile(file_path)
    file_size_mb = (os.path.getsize(file_path) / (1024 * 1024)) if file_exists else 0

    delivery_note_plain = (
        "Please find the final processed Excel file attached to this email."
        if (file_exists and file_size_mb <= 24.5)
        else "Please access the file directly from Google Drive using the link above (file exceeds email attachment limit)."
    )
    delivery_note_html = (
        "📎 <strong>Please find the final processed Excel file attached to this email.</strong>"
        if (file_exists and file_size_mb <= 24.5)
        else "🌐 <strong>Please access the file directly from Google Drive using the link above (file exceeds email attachment limit).</strong>"
    )

    plain_body = f"""Hello Deeksha,

The final processed dataset for {city_display} (Location: {loc_display}) has been successfully generated and is ready for your checking and verification.

Summary:
- City: {city_display}
- Location: {loc_display}
- File Name: {file_name}
- Total Records: {rows_display} rows
- Google Drive Link: {drive_link_display}
- File Path: {file_path}

{delivery_note_plain}

Best regards,
Nilesh K.
"""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1f2937; margin: 0; padding: 16px; background-color: #f9fafb;">
  <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
    <p style="margin-top: 0; font-size: 15px;">Hello <strong>Deeksha</strong>,</p>
    <p style="font-size: 15px;">The final processed dataset for <strong>{city_display}</strong> (Location: <strong>{loc_display}</strong>) has been successfully generated and is ready for your checking and verification.</p>

    <div style="background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 14px 18px; margin: 16px 0; border-radius: 4px; font-size: 13.5px;">
      <p style="margin: 4px 0;"><strong>🏙️ City:</strong> {city_display}</p>
      <p style="margin: 4px 0;"><strong>📍 Location:</strong> {loc_display}</p>
      <p style="margin: 4px 0;"><strong>📄 File Name:</strong> <code>{file_name}</code></p>
      <p style="margin: 4px 0;"><strong>📊 Total Records:</strong> <strong>{rows_display} rows</strong></p>
      <p style="margin: 4px 0;"><strong>🌐 Google Drive Folder:</strong> <a href="{drive_link_display}" target="_blank" style="color: #2563eb; text-decoration: underline; word-break: break-all;">{drive_link_display}</a></p>
      <p style="margin: 4px 0; color: #4b5563;"><strong>📂 Saved Path:</strong> <code style="background: #e5e7eb; padding: 2px 4px; border-radius: 3px; font-size: 12.5px;">{file_path}</code></p>
    </div>

    <p style="font-size: 14px; color: #374151; margin: 14px 0;">{delivery_note_html}</p>

    <div style="margin-top: 18px; padding-top: 14px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12.5px;">
      <p style="margin: 0;">This dataset has passed all standard pipeline transformations (Project Name Resolution, Transaction Categorisation, Area Standardization, RERA Grand Matching, Coordinates Lookup, and DB Columns Filtering).</p>
    </div>

    <p style="margin-top: 20px;">Best regards,<br><strong>Nilesh K.</strong></p>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Nilesh <{sender_email}>"
    msg["To"] = recipient
    if clean_cc:
        msg["Cc"] = ", ".join(clean_cc)
    msg["Subject"] = subject

    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(plain_body, "plain", "utf-8"))
    body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    if file_exists and file_size_mb <= 24.5:
        try:
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')
            msg.attach(part)
            is_attached = True
        except Exception:
            is_attached = False

    server = smtplib.SMTP(smtp_server, smtp_port, timeout=120)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, all_recipients, msg.as_string())
    server.quit()

    return {
        "status": "sent",
        "recipient": recipient,
        "cc": clean_cc,
        "attached": is_attached,
    }


