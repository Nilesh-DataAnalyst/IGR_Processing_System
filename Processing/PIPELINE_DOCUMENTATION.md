# IGR & Real Estate Data Processing Pipeline Documentation (`project.py`)

## 1. Executive Summary & Overview

`project.py` is the central orchestrator and data engineering pipeline for processing Inspector General of Registration (**IGR**) registration deeds and international real estate transaction datasets. It ingests semi-structured LLM-parsed output files, standardizes project names through character n-gram TF-IDF machine-learning clustering, normalizes traditional Marathi land/area measurements (Hectare, Are, Guntha, Sq.m, Sq.ft), harmonizes and merges multi-file human review datasets, reconciles records against MahaRERA master datasets, enriches buyer demographics and geospatial coordinates, applies statistical outlier detection, and formats the output for strict PostgreSQL database ingestion.

The system natively supports domestic Indian markets (Maharashtra: Pune, Mumbai, Thane) as well as international real estate data (Middle East: **Dubai Land Department**, Abu Dhabi). It can be operated either through an interactive terminal CLI (`project.py`) or a full-featured real-time Web Dashboard (`server.py` with Server-Sent Events). Shared core functions and utilities are encapsulated in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py).

---

## 2. Pipeline Execution Modes

When launching `project.py` (or triggering runs via the Web Dashboard), the operator selects the **Target City** and one of the execution modes:

```
[1] Run from START (Step 1 to Step 20)
    - Full end-to-end execution starting with raw LLM outputs from Google Drive.
    - Runs entity clustering, outputs manual review file (_for_manual.xlsx), pauses for
      human review, resumes upon approval (or auto-resumes), standardizes schema,
      converts to Parquet, uploads to PostgreSQL, and flags statistical outliers.

[2] Run from STEP 7 (Load manually corrected file directly, Steps 7 to 20)
    - Resumes the pipeline after human review of project names and areas.
    - Supports loading a single file, multiple comma-separated files, or all files in a location.
    - Executes automated schema harmonization, column mismatch audit reporting, and merging.
    - Continues with RERA matching, NR indexing, coordinate enrichment, Parquet export,
      database upload, and outlier classification.

[3] Run STEP 18 ONLY (Parquet Conversion directly, Steps 18 to 20)
    - Fast-path for converting verified final Excel/CSV datasets directly to Parquet.
    - Automatically triggers database upload (Step 19) and outlier classification (Step 20).

[4] Run STEP 20 ONLY (Outlier Detection & Update)
    - Standalone statistical outlier detection and classification directly on PostgreSQL.
    - Computes P1/P99 trimmed medians, updates database flags (rate, is_outlier, outlier_type),
      and exports audit summaries without re-running data ingestion.
```

For **Dubai** (City ID `15`), `project.py` provides a dedicated 2-step workflow:
```
[1] Run FULL Workflow (Step 1: Scraping ➔ Step 2: Processing) [Default]
[2] Run Step 1 ONLY: Scraping (dubai_scraper.py)
[3] Run Step 2 ONLY: Processing (dld_pipeline.py)
```

---

## 3. High-Level Architecture Flow

```mermaid
flowchart TD
    subgraph Ingestion & Entity Resolution [Steps 1 - 6]
        A[Raw LLM Output File\nGoogle Drive: 2. LLM Processed Data] --> B[Steps 1-5: Preprocessing\nDictToColumn, Deed Mapping, Village Mapping]
        B --> C[Step 6: Clustering & Area Conversion\nTF-IDF N-grams, Marathi Regex, Divisors]
        C --> D[Review File: _for_manual.xlsx\nGoogle Drive: 3. Manually Corrected]
    end

    subgraph Human Review & Multi-File Merging [Step 7]
        D --> E[Human Verification / Correction]
        E --> F[Step 7: Multi-File Ingestion & Merge Engine\npipeline_core.load_and_merge_step7_files]
        F --> F1[Auto-Save: FINAL MERGE / final merge file.xlsx]
        F --> F2[Audit Report: Step7_Missing_Columns_Report.xlsx]
    end

    subgraph Enrichment & Normalization [Steps 8 - 16]
        F --> G[Steps 8-10: Schema & Demographics\nColumn Mapping, Property Types, Indian Pincode]
        G --> H[Steps 11-14: Master Reconciliation\nMahaRERA Fuzzy Match, NR Indexing, Coordinates]
        H --> I[Steps 15-16: Selective Filtering\nStrict DB Sequence, Title Case Normalization]
    end

    subgraph Export, Upload & Outlier Audit [Steps 17 - 20]
        I --> J[Step 17: Final Excel Export & Checker Email\nSave to Drive + Alert to deeksha@sigmavalue.co.in]
        J --> K[Step 18: Columnar Parquet Conversion\nCompressed City-Level Parquet Dataset]
        K --> L[Step 19: Database Upload Pipeline\nTriggering final_code.py for PostgreSQL]
        L --> M[Step 20: Statistical Outlier Detection\nP1/P99 Trimmed Medians, Flagging & DB Writeback]
    end
```

---

## 4. End-to-End Step-by-Step Breakdown (Steps 1 to 20)

### Pre-Step: Target City Selection & Environment Configuration
- **City Registry ([`city_config.py`](file:///e:/Nilesh/IGR_processing_System/Processing/city_config.py))**: Resolves active city settings: Pune (ID: `9`), Mumbai (ID: `8`), Thane (ID: `12`), Dubai (ID: `15`), Abu Dhabi (ID: `1`), and other database cities.
- **Dynamic Google Drive Binding**: Resolves local Google Drive desktop shortcut paths on `G:\.shortcut-targets-by-id` for:
  - Input Folder (`2. LLM Processed Data`)
  - Manual Review Folder (`3. Manually Corrected`)
  - Final Output Folder (`4. Final processed file`)
- **Divisor Loading ([`divisor.py`](file:///e:/Nilesh/IGR_processing_System/Processing/divisor.py))**: Sets city-specific Saleable-to-Carpet divisors (Mumbai: `1.45`, Pune: `1.35`, Thane: `1.40`, Dubai: `1.0`).

---

### Step 1: Input File Selection (Location-Wise Drive Browser)
- **Function**: `get_file_from_drive(...)` in [`project.py`](file:///e:/Nilesh/IGR_processing_System/Processing/project.py)
- **Source**: `G:\.shortcut-targets-by-id\<input_id>\2. LLM Processed Data\`
- **Mechanism**:
  - Recursively scans the input folder on Google Drive.
  - Groups files by locality subfolders (e.g., Andheri, Kothrud, Wakad).
  - Displays an interactive menu of locations and file counts.
  - Automatically captures `selected_location` for downstream folder structuring.

---

### Step 2: DictToColumn Parsing
- **Module**: [`DictToColumn.py`](file:///e:/Nilesh/IGR_processing_System/Processing/DictToColumn.py) (`process_dict_to_column`)
- **Purpose**: Raw IGR files contain nested dictionary / JSON string representations inside text columns.
- **Transformation**:
  - Parses stringified dictionaries and extracts individual key-value pairs into first-class DataFrame columns.
  - Resolves target city metadata (`target_city_id`, `target_city_name`).

---

### Step 3: Create `final_project_name`
- **Purpose**: Establish a standardized project name column before entity resolution.
- **Logic**:
  - Checks if `project_name_en` is populated.
  - If blank or empty string, falls back to `building_name_en`.
  - Flags provenance in `final_project_name_status`: `"Project Name Considered"` or `"Building Name Considered"`.

---

### Step 4: Static Dictionary Mapping
- **Module**: [`static.py`](file:///e:/Nilesh/IGR_processing_System/Processing/static.py) (`result_dict`, `word_number_dict`)
- **Purpose**: Maps Marathi registration deed names (`docname`) to standardized English transaction descriptions.
- **Transformation**:
  - Transforms Marathi deed labels (खरेदीखत, भाडेपट्टा, बक्षीसपत्र, गहाणखत) into standardized English transaction types (`Sale Deed`, `Lease Deed`, `Gift Deed`, `Mortgage Deed`).
  - Prints summary distribution of 100% matched transaction types (`docname == transaction_type`).

---

### Step 5: Transaction Categorisation
- **Module**: [`transaction_categorizer.py`](file:///e:/Nilesh/IGR_processing_System/Processing/transaction_categorizer.py) (`categorise`)
- **Purpose**: Groups granular transaction types into primary analytical buckets:
  - **`Sale`**: Outright purchases, conveyances, developer-buyer sales.
  - **`Lease / Mortgage`**: Rental agreements, leave & license, mortgage deeds.
  - **`Other`**: Gift deeds, release deeds, conveyances, power of attorney.

---

### Step 5.5: Marathi Village to Location Mapping
- **Function**: `populate_village_mapping(...)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Purpose**: Resolves localized Marathi revenue village names (`village_name_marathi` / `areaname`) against the PostgreSQL database.
- **Mechanism**:
  - Queries `SELECT DISTINCT village_name_marathi, location_name, registered_document_village_name FROM public.transactions WHERE city_id = %s`.
  - Populates standardized `location_name` and `registered_document_village_name`.

---

### Step 6: Project Standardization & Area Conversion (`_for_manual.xlsx`)
- **Module**: [`project_name_Std_and_area_conversion.py`](file:///e:/Nilesh/IGR_processing_System/Processing/project_name_Std_and_area_conversion.py) (`process_dataframe`)
- **Architecture**:
  1. **Part A - Hybrid Entity Resolution**:
     - Strips legal suffixes (CHS, Phase, Wing, Coop Hsg Soc).
     - Computes character n-gram TF-IDF embeddings and cosine nearest neighbors.
     - Performs pairwise candidate validation (rejecting unsafe matches across phases or differing numerical identifiers).
     - Greedy clustering with cluster summary metrics.
  2. **Part B - Marathi Area Unit Parsing & Conversion**:
     - Extracts complex Marathi area expressions (Hectare-Are-Sq.m, Guntha, Are, Sq.ft, Sq.m).
     - Converts all parsed measurements into normalized **Square Metres**.
  3. **Part C - Unit and Floor Processing**:
     - Standardizes flat numbers into `flat_number` (from `flat_no_raw` or `flat_no`).
     - Extracts floor numbers into `floor_number` via `map_floor` (from `floor_no_raw` or `floor_no`).
  4. **Part D - Net Carpet Area Derivation & Rate**:
     - Applies the configured city divisor (`1.45` for Mumbai, `1.35` for Pune) to derive `net_carpet_area_sq_m`.
     - Derives `rate_in_sqft` as $\frac{\text{consideration\_amt}}{\text{net\_carpet\_area\_sq\_m} \times 10.764}$.
     - Generates `is_manual_processed` flag (`"Yes"` if `Sale` and `consideration_amt >= 70,000`, else `"No"`).
  5. **Part E - Clean Export of Multi-Sheet Review Workbook**:
     - Strips internal helper columns (`project_name_list`, `project_match_confidence_label`, `cluster_min_confidence_score`, etc.) from final review tabs.
     - Creates `<Location>_for_manual.xlsx` with review tabs: `Processed_Data`, `cluster_summary`, `manual_review`, `pair_review`, `Area_Review`, `Conversion_Test`.
     - Saves directly to Google Drive: `3. Manually Corrected/<Location>/`.

---

### Step 7: Multi-File Ingestion, Schema Audit & Merging
- **Module**: [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py) (`load_and_merge_step7_files`)
- **Function**: `get_manual_corrected_file(...)` in [`project.py`](file:///e:/Nilesh/IGR_processing_System/Processing/project.py)
- **Multi-File Selection**:
  - The operator can select a single file, multiple comma-separated indices (e.g., `1,2,3`), or enter `all` to merge all files within a location.
- **Automated Processing & Verification**:
  1. **Raw Column Harmonization**: Pre-maps `flat_no` -> `flat_no_raw` and `floor_no` -> `floor_no_raw` for each individual file.
  2. **Schema Cross-Check & Missing Column Detection**:
     - Calculates the complete union of columns across all files.
     - Evaluates every file against the union and identifies any missing columns.
  3. **Multi-Sheet Missing Column Audit Report**:
     - Exports **`Step7_Missing_Columns_Report.xlsx`** containing:
       - **Summary**: Rows, columns, and missing counts per file.
       - **Column Matrix**: Cross-tabulated matrix showing "Present" vs "Missing" for every column in each file.
       - **Missing Columns Detail**: Detailed row-by-row list of absent columns.
     - Exports **`Step7_Missing_Columns_Matrix.csv`** as a lightweight matrix fallback.
  4. **Master Merged Dataset Auto-Save**:
     - Saves the combined DataFrame directly to Google Drive:
       `3. Manually Corrected / FINAL MERGE / final merge file.xlsx`.
  5. **Systematic Column Stripping**:
     - Drops over 100 internal and unneeded helper columns (e.g., `society_name_en`, `requires_manual_review`, `FLAT AREAS`, `AREA DETAILS_*`).

---

### Step 8: Standardize Schema & Rename Columns
- **Function**: `rename_columns(...)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Mapping**:
  | Raw Column | Standard Database Column |
  | :--- | :--- |
  | `docno` | `document_number` |
  | `consideration_amt` | `agreement_price` |
  | `marketvalue` | `guideline_value` |
  | `Bhumapan` | `property_description` |
  | `registrationdate` | `transaction_date` |
  | `sellerparty` | `seller_name` |
  | `purchaserparty` | `buyer_name` |
  | `property_type` | `property_type_raw` |
  | `dateofexecution` | `date_of_agreement_execution` |
  | `micrno` | `micr_number` |
  | `stampdutypaid` | `stamp_duty_paid` |
  | `registrationfees` | `registration_fee` |
  | `flat_number` | `unit_number` |
  | `areaname` | `village_name_marathi` |
  | `srocode` | `sub_registrar_office_code` |

---

### Step 9: Categorise Property Type
- **Function**: `_map_property_type(...)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Standardized Categories**:
  - **`Flat`**: Apartment, Flat, Flat/Shop, House, Residential, Room.
  - **`Office`**: Commercial Property, Office, Commercial Wing.
  - **`Shop`**: Commercial Shop, Restaurant/Bar, Shop, Shop/Office.
  - **`Villa`**: Bungalow, Row House, Villa.
  - **`Plot`**: Land, Open Land, Plot.
  - **`Others`**: Unmapped or composite types.

---

### Step 10: Buyer Location & Pincode Enrichment
- **Function**: `add_buyer_location(...)`
- **Mechanism**:
  - Extracts 6-digit Indian postal PIN codes from `buyer_name` (e.g., `400053`).
  - Merges against [`postal_pincode.csv`](file:///e:/Nilesh/IGR_processing_System/Processing/postal_pincode.csv) (`Pincode`, `OfficeName_P`, `District_P`, `StateName_P`).
  - Enriches `buyer_locality`, `buyer_district`, and `buyer_state`.

---

### Step 11: MahaRERA Master Dataset Matching
- **Module**: [`rera_matching.py`](file:///e:/Nilesh/IGR_processing_System/Processing/rera_matching.py) (`process_rera_matching`)
- **Dataset**: City-specific RERA grand master file (e.g., `mumbai RERA GRAND EXCEL VERSION.xlsx`, `Pune RERA GRAND EXCEL VERSION 9.xlsx`).
- **Enrichment Fields**:
  - `index`: Unique MahaRERA project identifier.
  - `modified_project_name`: Verified MahaRERA project title.
  - `project_latitude` & `project_longitude`: Verified project coordinates.
  - `unit_configuration` / `BHK`: 1 BHK, 2 BHK, 3 BHK, etc., derived via carpet-wise sold units or carpet range fallback.
  - `rera_location`: Official registered location.
- Non-RERA cities safely bypass this step with null placeholders.

---

### Intermediate Schema Alignment & Rate Derivation
Before index assignment, `project.py` executes critical derivations:
1. **Quarter Derivation**: Formats `Q1-2026`, `Q2-2026`, etc., from `transaction_date`.
2. **Date Reformatting**: Standardizes dates to `DD/MM/YYYY`.
3. **Net Carpet Area in Sq.Ft**: `net_carpet_area_sqft = net_carpet_area_sq_m * 10.7639`.
4. **Calculated Rate (`rate`)**:
   $$\text{rate} = \frac{\text{agreement\_price}}{\text{net\_carpet\_area\_sqft}}$$
5. **Database Default Assignments**: Populates defaults for `state_name`, `country_name`, `data_source` ("Igr"), `source_accessibility` ("Easy"), `is_llm_processed` ("Yes").

---

### Step 12: Assign Non-RERA (NR) Indexes via PostgreSQL
- **Function**: `assign_nr_indexes(...)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Purpose**: Transactions that did not match any MahaRERA project require a unique project-level tracking ID.
- **Mechanism**:
  - Connects to PostgreSQL:
    ```sql
    SELECT MAX((regexp_match(internal_index_id, '^nr(\d+)', 'i'))[1]::int)
    FROM public.transactions
    WHERE city_id = %s AND internal_index_id ~* '^nr\d+';
    ```
  - Identifies highest existing NR number for the city (e.g., `nr18420`).
  - Sequentially assigns new NR IDs (`nr18421`, `nr18422`, ...) to unindexed projects.

---

### Step 13: Fetch Location Coordinates from Database
- **Function**: `populate_location_coords(...)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Purpose**: Ensures every record has regional geospatial fallback coordinates even if specific project coordinates are missing.
- **Mechanism**: Reads coordinates from `public.dim_location` (`location_latitude`, `location_longitude`) matching on `location_name`.

---

### Step 14: Project Coordinates via Google Places API (Toggleable)
- **Module**: `project_coordinates.py`
- **Status**: Optional / commented out in standard runs to conserve API credits.

---

### Step 15: Filter & Order Selective Database Columns
- **Module**: [`db_columns.py`](file:///e:/Nilesh/IGR_processing_System/Processing/db_columns.py) (`DB_SEQUENCE`)
- **Function**: `keep_db_columns(df, DB_SEQUENCE)` in [`pipeline_core.py`](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py)
- **Purpose**: Strict schema conformity. Reorders and filters DataFrame columns so that their order exactly mirrors `public.transactions` in PostgreSQL.

---

### Step 16: Title Case Normalization
- **Purpose**: Cosmetic consistency across text fields.
- **Logic**: Applies Python `.title()` across all string columns.

---

### Step 17: Final Output Save & Automated Checker Notification
- **Naming Pattern**: `<Location>_final_processed.xlsx`
- **Target Folder**: `G:\.shortcut-targets-by-id\<final_drive_id>\4. Final processed file\<Location>\`
- **Automated Checker Email**:
  - Spawns a background thread calling `send_final_checker_email()` in [`city_config.py`](file:///e:/Nilesh/IGR_processing_System/Processing/city_config.py).
  - Dispatches an automated HTML report to the quality checker (`deeksha@sigmavalue.co.in`).
  - Email includes: City, Location, Row Count, Local Output Path, Google Drive Shareable Folder Link, and timestamp.

---

### Step 18: Parquet Conversion
- **Module**: [`parquet_conersion.py`](file:///e:/Nilesh/IGR_processing_System/Processing/parquet_conersion.py) (`convert_csv_to_parquet`)
- **Purpose**: Generates high-speed columnar Parquet format optimized for bulk database loading.
- **Type Casting & Date Overflow Protection**: Converts dates safely to string `YYYY-MM-DD` (preventing 64-bit nanosecond datetime overflows on historical records).

---

### Step 19: Trigger Database Upload Pipeline (`final_code.py`)
- **Script**: `E:\Nilesh\Database\DB1_DB2_Uploading_Pipeline\final_code.py`
- **Mechanism**:
  - Executes database loader subprocess in the active virtual environment.
  - Bulk inserts transactions into PostgreSQL tables (`transactions`, `projects`, `listings`).

---

### Step 20: Post-Upload Statistical Outlier Detection (`outlier_update.py`)
- **Module**: [`outlier_update.py`](file:///e:/Nilesh/IGR_processing_System/Processing/outlier_update.py)
- **Purpose**: Classifies newly ingested transactions into statistical outlier categories.
- **Algorithm**:
  1. Computes $\text{calc\_rate} = \frac{\text{agreement\_price}}{\text{net\_carpet\_area\_sq\_m} \times 10.764}$.
  2. Groups by `(city, location, transaction_category, property_type)` (international markets collapsed into `__ALL_LOCATIONS__`).
  3. Trims top 1% and bottom 1% records (P1 / P99) per group.
  4. Computes trimmed medians and boundaries:
     $$\text{lower\_limit} = \frac{\text{median}}{4}, \quad \text{upper\_limit} = \text{median} \times 4$$
  5. Classifies records: `Normal`, `Lower Outlier`, `Upper Outlier`, `Mumbai Low Price Outlier (Sale < 1L)`, `Mumbai Zero Area & Rate - Not Outlier`, `Invalid/Excluded`.
  6. Batch updates PostgreSQL columns (`rate`, `is_outlier`, `outlier_type`) using `execute_values`.

---

## 5. Web Operations Dashboard Architecture (`server.py`)

A full-stack, browser-based operations interface is provided in [`Processing/server.py`](file:///e:/Nilesh/IGR_processing_System/Processing/server.py) and [`Processing/web/`](file:///e:/Nilesh/IGR_processing_System/Processing/web):

```
Processing/web/
├── index.html       # Single-page operations interface
├── app.js           # Real-time SSE streaming client & dynamic stage router
├── style.css        # Premium dark-themed design system
└── email_template.html # Email template for automated reviews
```

### Key Web Features:
1. **Server-Sent Events (SSE) Stream**: Real-time terminal log stream at `/api/status` with auto-scroll and status pills.
2. **Multi-File Selection & Audit**: Allows operators to pick multiple review files and displays real-time merge status.
3. **Dynamic Database Switcher**: Switch target PostgreSQL databases on the fly via `/api/set-db`.
4. **Interactive Google Drive Pickers**: Browses local Google Drive folders dynamically for Input, Manual, and Final files.
5. **Stage Execution Controls**: Trigger full runs, resume Step 7, trigger Parquet conversion, run outlier updates, or stop active processes.

---

## 6. International Data Ingestion (Dubai Land Department & Abu Dhabi)

The system extends real estate data processing beyond Indian IGR to Middle Eastern markets:

1. **Automated Selenium Scraper ([`Processing/Dubai_processing/dubai_scraper.py`](file:///e:/Nilesh/IGR_processing_System/Processing/Dubai_processing/dubai_scraper.py))**:
   - Scrapes transaction datasets from the DLD Open Data Portal.
   - Automatically queries `public.transactions` for the last recorded transaction date to fetch only incremental data.
   - Handles Google reCAPTCHA challenges automatically.
   - Supports headless execution and automatic upload to Google Drive.
2. **End-to-End Processing & NR Allocation ([`Processing/Dubai_processing/dld_pipeline.py`](file:///e:/Nilesh/IGR_processing_System/Processing/Dubai_processing/dld_pipeline.py))**:
   - Ingests raw DLD CSV files, strips duplicates, and parses dates into quarterly format.
   - Enriches records with PostgreSQL spatial coordinates and project IDs (`dim_project`, `dim_location`).
   - Allocates sequential NR index IDs (`nrXXXX`) scoped to Dubai (`city_id = 15`).
3. **Outlier Grouping Logic**:
   - In `outlier_update.py`, international markets (`dubai`, `abu_dhabi`) have localities collapsed into `__ALL_LOCATIONS__` to compute unified city-level price distribution metrics.

---

## 7. Master File & Dependency Registry

| File / Script | Core Functionality & Role |
| :--- | :--- |
| [project.py](file:///e:/Nilesh/IGR_processing_System/Processing/project.py) | Master CLI pipeline orchestrator coordinating Steps 1 through 20. |
| [server.py](file:///e:/Nilesh/IGR_processing_System/Processing/server.py) | FastAPI/HTTP server providing real-time SSE progress streaming and web dashboard. |
| [pipeline_core.py](file:///e:/Nilesh/IGR_processing_System/Processing/pipeline_core.py) | Shared core library: DB connections, Step 7 multi-merging, schema renaming, NR indexing, village mapping. |
| [city_config.py](file:///e:/Nilesh/IGR_processing_System/Processing/city_config.py) | Central configuration for city IDs, Google Drive IDs, RERA paths, and automated checker emails. |
| [divisor.py](file:///e:/Nilesh/IGR_processing_System/Processing/divisor.py) | Defines city-specific carpet area divisors (Mumbai: 1.45, Pune: 1.35, Thane: 1.40, Dubai: 1.0). |
| [DictToColumn.py](file:///e:/Nilesh/IGR_processing_System/Processing/DictToColumn.py) | Extracts stringified JSON dictionaries into structured tabular columns. |
| [transaction_categorizer.py](file:///e:/Nilesh/IGR_processing_System/Processing/transaction_categorizer.py) | Categorizes transaction types into Sale, Lease / Mortgage, or Other. |
| [project_name_Std_and_area_conversion.py](file:///e:/Nilesh/IGR_processing_System/Processing/project_name_Std_and_area_conversion.py) | TF-IDF clustering, Marathi area converter, unit/floor parser, and review workbook exporter. |
| [rera_matching.py](file:///e:/Nilesh/IGR_processing_System/Processing/rera_matching.py) | MahaRERA fuzzy matching engine for project name, coordinate, and BHK enrichment. |
| [postal_pincode.csv](file:///e:/Nilesh/IGR_processing_System/Processing/postal_pincode.csv) | Master Indian postal PIN code database for buyer locality and district mapping. |
| [db_columns.py](file:///e:/Nilesh/IGR_processing_System/Processing/db_columns.py) | Canonical PostgreSQL column sequence definition (`DB_SEQUENCE`). |
| [parquet_conersion.py](file:///e:/Nilesh/IGR_processing_System/Processing/parquet_conersion.py) | High-performance Excel/CSV-to-Parquet conversion utility with timestamp overflow protection. |
| [outlier_update.py](file:///e:/Nilesh/IGR_processing_System/Processing/outlier_update.py) | Statistical outlier detection engine, P1/P99 trimmed medians, and PostgreSQL batch updater. |
| [generate_pdf_doc.py](file:///e:/Nilesh/IGR_processing_System/Processing/generate_pdf_doc.py) | ReportLab script that compiles this documentation into a publication-quality PDF. |
| [Dubai_processing/dubai_scraper.py](file:///e:/Nilesh/IGR_processing_System/Processing/Dubai_processing/dubai_scraper.py) | Automated Selenium scraper and Google Drive uploader for Dubai Land Department data. |
| [Dubai_processing/dld_pipeline.py](file:///e:/Nilesh/IGR_processing_System/Processing/Dubai_processing/dld_pipeline.py) | End-to-end data transformation, coordinate lookup, and NR index allocator for Dubai data. |
| [web/](file:///e:/Nilesh/IGR_processing_System/Processing/web) | Web Operations Dashboard frontend (`index.html`, `app.js`, `style.css`). |
