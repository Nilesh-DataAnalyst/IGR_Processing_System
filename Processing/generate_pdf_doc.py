import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))

        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "IGR & Real Estate Data Processing Pipeline Documentation | project.py")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.5)
            self.line(54, 744, 558, 744)

        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 558, 45)

        self.drawString(54, 32, "Confidential | Real Estate Analytics & Data Engineering")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(558, 32, page_str)
        self.restoreState()


def build_pdf(filename="PIPELINE_DOCUMENTATION.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#1A365D")
    secondary_color = colors.HexColor("#2B6CB0")
    dark_neutral = colors.HexColor("#2D3748")
    light_neutral = colors.HexColor("#4A5568")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=secondary_color,
        spaceAfter=6
    )

    tagline_style = ParagraphStyle(
        'DocTagline',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12,
        textColor=light_neutral,
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=secondary_color,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=dark_neutral,
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10.5,
        textColor=dark_neutral,
        leftIndent=12,
        spaceAfter=2
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=dark_neutral
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=primary_color
    )

    story = []

    # Title Banner
    story.append(Paragraph("IGR & REAL ESTATE DATA PROCESSING PIPELINE", title_style))
    story.append(Paragraph("Comprehensive Technical Architecture & Step-by-Step System Documentation (project.py)", subtitle_style))
    story.append(Paragraph("Automated Ingestion, Entity Resolution, Spatial Enrichment, 20-Step Pipeline, Web Dashboard & PostgreSQL Loading", tagline_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceBefore=0, spaceAfter=8))

    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary & Core Mission", h1_style))
    story.append(Paragraph(
        "<b>project.py</b> serves as the master production orchestrator responsible for transforming raw, semi-structured Inspector General of "
        "Registration (IGR) filings and international real estate transaction datasets into a standardized, validated, and enriched relational format. "
        "Operating across domestic micro-markets (Mumbai, Pune, Thane) and international markets (Dubai, Abu Dhabi), the pipeline automates nested "
        "JSON parsing, machine-learning phonetic/n-gram project clustering, Marathi land area conversion (Hectare-Are-Guntha to Sq.m), MahaRERA master reconciliation, "
        "automated Non-RERA (NR) sequencing, buyer demographics geo-enrichment, automated quality-checker notification emails, columnar Parquet export, "
        "PostgreSQL upload, and statistical outlier classification.",
        body_style
    ))

    # 2. Pipeline Execution Modes
    story.append(Paragraph("2. Pipeline Execution Modes", h1_style))
    modes_data = [
        [Paragraph("Mode", table_header_style), Paragraph("Scope & Steps", table_header_style), Paragraph("Operational Workflow & Use Case", table_header_style)],
        [
            Paragraph("<b>Mode [1]</b>", table_cell_bold),
            Paragraph("<b>Run from START</b><br/>Steps 1 to 20<br/>(Full End-to-End)", table_cell_style),
            Paragraph("Processes freshly delivered LLM files from Google Drive (<i>2. LLM Processed Data</i>). Runs entity clustering, outputs manual review file, pauses for operator verification, resumes upon confirmation, aligns schema, converts to Parquet, uploads to DB, and flags outliers.", table_cell_style)
        ],
        [
            Paragraph("<b>Mode [2]</b>", table_cell_bold),
            Paragraph("<b>Run from STEP 7</b><br/>Steps 7 to 20<br/>(Resume Mode)", table_cell_style),
            Paragraph("Directly loads a verified/corrected manual review workbook from Google Drive (<i>3. Manually Corrected</i>). Bypasses raw ingestion & clustering, immediately executing RERA matching, NR index assignment, coordinate enrichment, Parquet export, DB upload, and outlier classification.", table_cell_style)
        ],
        [
            Paragraph("<b>Mode [3]</b>", table_cell_bold),
            Paragraph("<b>Run STEP 18 ONLY</b><br/>Steps 18 to 20<br/>(Direct Parquet)", table_cell_style),
            Paragraph("Fast-path for converting verified final Excel/CSV datasets directly to compressed Apache Parquet format. Automatically proceeds to database ingestion via <code>final_code.py</code> (Step 19) and statistical outlier detection (Step 20).", table_cell_style)
        ],
        [
            Paragraph("<b>Mode [4]</b>", table_cell_bold),
            Paragraph("<b>Run STEP 20 ONLY</b><br/>Step 20 Only<br/>(Outlier Update)", table_cell_style),
            Paragraph("Standalone statistical outlier detection and classification directly on PostgreSQL database records. Computes P1/P99 trimmed medians, updates flags (<code>is_outlier</code>, <code>outlier_type</code>), and exports multi-sheet audit workbooks without re-running data ingestion.", table_cell_style)
        ],
    ]
    t_modes = Table(modes_data, colWidths=[65, 110, 329])
    t_modes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_modes)
    story.append(Spacer(1, 6))

    # 3. Detailed Step-by-Step Technical Guide
    story.append(Paragraph("3. Detailed Step-by-Step Technical Guide (Steps 1 to 20)", h1_style))

    steps = [
        ("Pre-Step: City Configuration & Google Drive Binding",
         "Initializes the active city context via <code>city_config.py</code> (Pune: 9, Mumbai: 8, Thane: 12, Dubai: 15, Abu Dhabi: 1). Dynamically binds to Google Drive desktop shortcuts on <code>G:\\.shortcut-targets-by-id\\...</code> for input, review, and final folders. Loads city carpet area divisors (Mumbai: 1.45, Pune: 1.35, Dubai: 1.0 from <code>divisor.py</code>)."),

        ("Step 1: Input File Discovery (Location-Wise Drive Browser)",
         "Recursively scans <i>2. LLM Processed Data</i> on Google Drive. Groups and displays available localities (e.g., Andheri, Kothrud, Wakad). Captures selected location globally for structured subfolder export downstream."),

        ("Step 2: DictToColumn JSON & Dictionary Extraction",
         "Executes <code>DictToColumn.py</code>. Flattens nested stringified JSON dictionary representations from raw IGR metadata columns into typed DataFrame columns. Automatically verifies target city identity."),

        ("Step 3: Standardization of Initial Project Name",
         "Populates <code>final_project_name</code> from <code>project_name_en</code>. Falls back to <code>building_name_en</code> if blank, recording audit provenance in <code>final_project_name_status</code> ('Project Name Considered' vs 'Building Name Considered')."),

        ("Step 4: Static Dictionary Transaction Type Mapping",
         "Imports <code>static.py</code>. Translates localized Marathi deed classifications (Kharedikhat, Bhadepatta, Bakshispatra, etc.) into standardized English transaction types (Sale Deed, Lease Deed, Gift Deed, Mortgage Deed)."),

        ("Step 5: High-Level Transaction Categorisation",
         "Applies <code>transaction_categorizer.py</code> to categorize transactions into primary analytical buckets: <b>Sale</b> (capital purchases/conveyances), <b>Lease / Mortgage</b> (rental agreements and bank liens), and <b>Other</b>."),

        ("Step 5.5: Marathi Revenue Village to Locality Mapping",
         "Queries PostgreSQL <code>public.transactions</code> to map <code>village_name_marathi</code> / <code>areaname</code> to canonical <code>location_name</code> and <code>registered_document_village_name</code>, ensuring zero data loss for municipal revenue villages."),

        ("Step 6: Hybrid Project Clustering & Marathi Area Conversion (_for_manual.xlsx)",
         "Core ML component via <code>project_name_Std_and_area_conversion.py</code>:<br/>"
         "• <b>Part A (Entity Resolution)</b>: Strips legal suffixes (CHS, Phase, Wing); builds character n-gram TF-IDF matrices; computes pairwise cosine nearest neighbours; applies conservative rejection heuristics; executes greedy clustering.<br/>"
         "• <b>Part B (Marathi Area Parsing)</b>: Regex-parses Marathi units (Hectare-Are-Sq.m, Guntha, Are, Sq.ft, Sq.m) into normalized square metres.<br/>"
         "• <b>Part C (Unit & Floor)</b>: Extracts flat/shop numbers (<code>unit_number</code>) and floor numbers (<code>floor_number</code>).<br/>"
         "• <b>Part D (Carpet Derivation)</b>: Applies city divisors to derive <code>net_carpet_area_sq_m</code> for Sale deeds.<br/>"
         "• <b>Export</b>: Generates multi-sheet workbook <code>&lt;Location&gt;_for_manual.xlsx</code> in Google Drive (<i>3. Manually Corrected/&lt;Location&gt;/</i>).<br/>"
         "• <b>Review Alert</b>: Prompts user to send automated email notification to reviewers with review guidelines and Drive links."),

        ("Step 7: Load Manually Corrected Review File",
         "Pipeline pauses for human review. Once project name corrections and area validations are complete, Step 7 loads the reviewed file directly from Drive or custom path. Pressing 'Enter' automatically selects the Step 6 file."),

        ("Step 8: Standardize Database Column Schema",
         "Executes <code>rename_columns()</code> to align raw fields to production PostgreSQL schema: <code>docno</code> → <code>document_number</code>, <code>consideration_amt</code> → <code>agreement_price</code>, <code>marketvalue</code> → <code>guideline_value</code>, <code>sellerparty</code> → <code>seller_name</code>, <code>purchaserparty</code> → <code>buyer_name</code>, <code>flat_number</code> → <code>unit_number</code>, <code>srocode</code> → <code>sub_registrar_office_code</code>."),

        ("Step 9: Categorise Property Types",
         "Normalizes property descriptions into six canonical types: <b>Flat</b> (Apartments, Rooms, Houses), <b>Office</b> (Commercial Offices), <b>Shop</b> (Retail, Restaurants), <b>Villa</b> (Bungalows, Row Houses), <b>Plot</b> (Open Land), and <b>Others</b>."),

        ("Step 10: Buyer Location & Postal PIN Code Enrichment",
         "Uses regex to extract 6-digit Indian PIN codes from <code>buyer_name</code>. Merges against <code>postal_pincode.csv</code> to append <code>buyer_locality</code>, <code>buyer_district</code>, and <code>buyer_state</code>."),

        ("Step 11: MahaRERA Master Dataset Matching",
         "Runs <code>rera_matching.py</code> against city-specific MahaRERA grand files (e.g., <i>mumbai RERA GRAND EXCEL VERSION.xlsx</i>, <i>Pune RERA GRAND EXCEL VERSION 9.xlsx</i>). Appends official RERA index, verified project names, geocoded coordinates (<code>project_latitude</code>, <code>project_longitude</code>), and configurations (<code>BHK</code>). Non-RERA cities safely bypass with null placeholders."),

        ("Intermediate: Financial & Chronological Calculations",
         "• Derives registration quarters (e.g. Q1-2026) and standardizes date formatting to <code>DD/MM/YYYY</code>.<br/>"
         "• Computes net carpet area in square feet: <code>net_carpet_area_sqft = net_carpet_area_sq_m * 10.7639</code>.<br/>"
         "• Computes calculated rate: <code>rate = agreement_price / net_carpet_area_sqft</code> (standardized to column <code>rate</code>).<br/>"
         "• Assigns DB defaults: <code>state_name</code>, <code>country_name</code>, <code>data_source='Igr'</code>, <code>is_llm_processed='Yes'</code>."),

        ("Step 12: Sequential Non-RERA (NR) Index Assignment",
         "Transactions without a MahaRERA match receive an incremental Non-RERA ID. Queries PostgreSQL for current max sequence (<code>SELECT MAX(internal_index_id) WHERE internal_index_id ~* '^nr\\d+'</code>) and assigns new sequential IDs (<code>nr18421</code>, <code>nr18422</code>, etc.)."),

        ("Step 13: Fetch Location Coordinates from Database",
         "Queries <code>public.dim_location</code> for <code>location_latitude</code> and <code>location_longitude</code> based on <code>location_name</code>, providing locality-level geospatial fallbacks for every record."),

        ("Step 14: Project Coordinates via Google Places API (Optional)",
         "Toggleable geocoding module (<code>project_coordinates.py</code>) to query high-precision project coordinates for unmapped developments using Google Places API."),

        ("Step 15: Filter & Order Selective Database Columns",
         "Imports <code>DB_SEQUENCE</code> from <code>db_columns.py</code>. Strictly reorders and filters DataFrame columns to mirror the exact positional schema of <code>public.transactions</code> in PostgreSQL."),

        ("Step 16: Title Case Normalization",
         "Applies Python <code>.title()</code> formatting across all object/string columns for cosmetic and visual uniformity."),

        ("Step 17: Final Dataset Export & Automated Checker Email Notification",
         "• Saves master cleaned workbook <code>&lt;Location&gt;_final_processed.xlsx</code> to Google Drive: <i>4. Final processed file/&lt;Location&gt;/</i>.<br/>"
         "• <b>Automated Email Dispatch</b>: Launches background thread via <code>send_final_checker_email()</code> in <code>city_config.py</code>. Dispatches an automated HTML alert to the quality checker (<code>deeksha@sigmavalue.co.in</code>) with city, locality, row count, file path, and Google Drive share link."),

        ("Step 18: High-Performance Parquet Conversion",
         "Executes <code>parquet_conersion.py</code> to convert the final dataset into an optimized Apache Parquet columnar file under <code>converted_feather_parquet/&lt;City&gt;/&lt;City&gt;_db1.parquet</code> with date string normalization (safe from 64-bit nanosecond overflows)."),

        ("Step 19: Trigger Central Database Upload Pipeline",
         "Executes <code>DB1_DB2_Uploading_Pipeline\\final_code.py</code> via subprocess in the active Python virtual environment to ingest the Parquet records directly into PostgreSQL tables."),

        ("Step 20: Post-Upload Statistical Outlier Detection (outlier_update.py)",
         "Statistical outlier classification engine (<code>outlier_update.py</code> / <code>incremental_outlier_update.py</code>):<br/>"
         "• <b>Trimmed Baseline</b>: Computes P1/P99 trimmed medians and IQR boundaries per <code>(city, location, category, property_type)</code> slice.<br/>"
         "• <b>Dynamic Thresholds</b>: Sets <code>lower_limit = median / 4</code> and <code>upper_limit = median * 4</code>.<br/>"
         "• <b>Classification</b>: Flags records as <code>Normal</code>, <code>Lower Outlier</code>, <code>Upper Outlier</code>, <code>Mumbai Low Price Outlier</code>, or <code>Zero Area/Price</code>.<br/>"
         "• <b>Database Update</b>: Performs batch update on PostgreSQL columns: <code>rate</code>, <code>is_outlier</code>, and <code>outlier_type</code>.<br/>"
         "• <b>Audit Workbook</b>: Generates multi-sheet Excel summary report in <code>outlier_summaries/</code>.")
    ]

    for title, desc in steps:
        story.append(Paragraph(f"<b>{title}</b>", h2_style))
        story.append(Paragraph(desc, body_style))

    story.append(Spacer(1, 6))

    # 4. Web Dashboard Architecture
    story.append(Paragraph("4. Web Dashboard Architecture (server.py & web/)", h1_style))
    story.append(Paragraph(
        "A full-stack, browser-based management interface is integrated in <code>Processing/server.py</code> and <code>Processing/web/</code>. "
        "Built with a high-performance FastAPI backend and vanilla modern CSS/JS frontend, it provides:<br/>"
        "• <b>Real-Time SSE Streaming</b>: Server-Sent Events stream live terminal logs from <code>project.py</code> directly to the browser UI with auto-scroll and status indicators.<br/>"
        "• <b>Dynamic Mode Routing & Auto-Scroll</b>: Selecting a mode automatically redirects, scrolls, and focuses the relevant form card (Mode 1: Start/Drive Picker, Mode 2: Step 7 Resume Card, Mode 3: Parquet Conversion Card, Mode 4: Outlier Detection Card).<br/>"
        "• <b>Interactive Drive Explorer</b>: Recursively scans local Google Drive shortcut trees and allows point-and-click file selection.<br/>"
        "• <b>Multi-City Support</b>: Dropdown configuration populated from <code>public.dim_city</code> with automatic divisor binding.",
        body_style
    ))
    story.append(Spacer(1, 6))

    # 5. International Real Estate Processing
    story.append(Paragraph("5. International Real Estate Processing (Dubai & Abu Dhabi)", h1_style))
    story.append(Paragraph(
        "The system natively accommodates international datasets from the Middle East:<br/>"
        "• <b>Automated Portal Scraper (<code>Processing/Dubai_processing/</code>)</b>: Includes <code>dubai_scraper_all_in_one.py</code> for the Dubai Land Department (DLD) Open Data portal. Handles automated reCAPTCHA, date filtering, CSV download, and Google Drive upload.<br/>"
        "• <b>City-Wide Grouping in Outlier Detection</b>: For Dubai (City ID: 15) and Abu Dhabi (City ID: 1), all micro-locations are collapsed into <code>__ALL_LOCATIONS__</code> in <code>outlier_update.py</code> to compute unified, robust price distribution statistics across the emirate.<br/>"
        "• <b>Historical Calendar Serialization</b>: Date parsing in <code>parquet_conersion.py</code> preserves historical and Hijri dates as safe strings without conversion failures.",
        body_style
    ))
    story.append(Spacer(1, 6))

    # 6. Master File & Dependency Registry
    story.append(Paragraph("6. Master File & Dependency Registry", h1_style))

    files_data = [
        [Paragraph("File / Module", table_header_style), Paragraph("Role & Core Responsibility", table_header_style)],
        [Paragraph("<b>project.py</b>", table_cell_bold), Paragraph("Master CLI orchestrator coordinating full 20-step execution pipeline.", table_cell_style)],
        [Paragraph("<b>server.py</b>", table_cell_bold), Paragraph("FastAPI Web Server providing real-time SSE progress streaming and web dashboard.", table_cell_style)],
        [Paragraph("<b>web/ (index.html, app.js, style.css)</b>", table_cell_bold), Paragraph("Modern browser operations interface with mode routing, live log viewer, and Drive explorer.", table_cell_style)],
        [Paragraph("<b>city_config.py</b>", table_cell_bold), Paragraph("Central registry for city IDs, Google Drive URLs/IDs, RERA paths, and automated checker email dispatcher.", table_cell_style)],
        [Paragraph("<b>divisor.py</b>", table_cell_bold), Paragraph("Carpet area divisors by city (Mumbai: 1.45, Pune: 1.35, Thane: 1.40, Dubai: 1.0).", table_cell_style)],
        [Paragraph("<b>DictToColumn.py</b>", table_cell_bold), Paragraph("JSON flattener extracting stringified dictionary entries into typed DataFrame columns.", table_cell_style)],
        [Paragraph("<b>transaction_categorizer.py</b>", table_cell_bold), Paragraph("Rule-based transaction categorizer classifying deeds into Sale, Lease/Mortgage, and Other.", table_cell_style)],
        [Paragraph("<b>project_name_Std_and_area_conversion.py</b>", table_cell_bold), Paragraph("TF-IDF n-gram clustering, Marathi area converter, unit/floor parser, and manual review workbook exporter.", table_cell_style)],
        [Paragraph("<b>rera_matching.py</b>", table_cell_bold), Paragraph("Fuzzy matching engine reconciling project names, RERA indexes, and coordinates against MahaRERA master records.", table_cell_style)],
        [Paragraph("<b>postal_pincode.csv</b>", table_cell_bold), Paragraph("Master Indian postal directory for buyer locality, district, and state geo-enrichment.", table_cell_style)],
        [Paragraph("<b>db_columns.py</b>", table_cell_bold), Paragraph("Canonical PostgreSQL column sequence definition (<code>DB_SEQUENCE</code>).", table_cell_style)],
        [Paragraph("<b>parquet_conersion.py</b>", table_cell_bold), Paragraph("High-speed columnar Parquet conversion utility with type validation and date string normalization.", table_cell_style)],
        [Paragraph("<b>outlier_update.py / incremental_outlier_update.py</b>", table_cell_bold), Paragraph("Statistical outlier detection engine calculating trimmed medians and updating PostgreSQL flags.", table_cell_style)],
        [Paragraph("<b>Dubai_processing/ (dubai_scraper_all_in_one.py)</b>", table_cell_bold), Paragraph("Automated scraper and Drive uploader for Dubai Land Department real estate transaction records.", table_cell_style)],
    ]

    t_files = Table(files_data, colWidths=[150, 354])
    t_files.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_files)

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated {filename}")

if __name__ == '__main__':
    build_pdf()
