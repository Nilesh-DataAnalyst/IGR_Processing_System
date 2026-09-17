# IGR & Real Estate Data Processing Pipeline Documentation (`project.py`)

## 1. Executive Summary & Overview

`project.py` is the central orchestrator and data transformation pipeline for processing Inspector General of Registration (IGR) and international real estate transaction datasets. It ingests semi-structured LLM-parsed output files, standardizes project names through machine-learning clustering, normalizes traditional Marathi land/area measurements (Hectare-Are-Guntha), reconciles records against MahaRERA master datasets, enriches buyer demographics and geospatial coordinates, applies statistical outlier detection, and formats the output for strict PostgreSQL database ingestion.

The system supports domestic Indian markets (e.g., Pune, Mumbai, Thane) as well as international real estate data (Dubai Land Department, Abu Dhabi), and can be operated either through an interactive terminal CLI or a full-featured real-time Web Dashboard (`server.py`).

---

## 2. Pipeline Execution Modes

When launching `project.py` (or through the Web Dashboard), the operator selects the **Target City** and one of four execution modes:

```
[1] Run from START (Step 1 to Step 20)
    - Full end-to-end execution starting with raw LLM outputs.
    - Runs entity clustering, outputs manual review file, resumes upon approval,
      standardizes schema, converts to Parquet, uploads to DB, and flags outliers.

[2] Run from STEP 7 (Load manually corrected file directly, Steps 7 to 20)
    - Resumes pipeline after human review of project names and areas.
    - Skips raw ingestion & clustering, directly executing RERA matching, NR indexing,
      coordinate enrichment, Parquet export, DB upload, and outlier detection.

[3] Run STEP 18 ONLY (Parquet Conversion directly, Steps 18 to 20)
    - Fast-path for converting verified final Excel/CSV datasets directly to Parquet.
    - Automatically triggers database upload (Step 19) and outlier classification (Step 20).

[4] Run STEP 20 ONLY (Outlier Detection & Update)
    - Standalone statistical outlier detection and classification directly on PostgreSQL.
    - Calculates P1/P99 trimmed medians, updates database flags (is_outlier, outlier_type),
      and exports multi-sheet audit workbooks without re-running data ingestion.
```

---

## 3. High-Level Architecture Flow

```mermaid
flowchart TD
    subgraph Ingestion & Entity Resolution [Steps 1 - 6]
        A[Raw LLM Output File\nGoogle Drive: 2. LLM Processed Data] --> B[Steps 1-5: Preprocessing\nDictToColumn, Categorisation, Village Mapping]
        B --> C[Step 6: Clustering & Area Conversion\nTF-IDF N-grams, Marathi Regex, Divisors]
        C --> D[Review File: _for_manual.xlsx\nGoogle Drive: 3. Manually Corrected]
    end

    subgraph Human Review Loop [Step 7]
        D --> E[Human Verification / Correction]
        E --> F[Step 7: Ingestion of Reviewed File]
    end

    subgraph Enrichment & Normalization [Steps 8 - 16]
        F --> G[Steps 8-10: Schema & Demographics\nColumn Mapping, Property Types, Indian Pincode]
        G --> H[Steps 11-14: Master Reconciliation\nMahaRERA Fuzzy Match, NR Indexing, Coordinates]
        H --> I[Steps 15-16: Selective Filtering\nDB Column Sequence, Title Case Normalization]
    end

    subgraph Export, Upload & Audit [Steps 17 - 20]
        I --> J[Step 17: Final Excel Export & Checker Email\nSave to Drive + Alert to deeksha@sigmavalue.co.in]
        J --> K[Step 18: Parquet Conversion\nCompressed City-Level Parquet Dataset]
        K --> L[Step 19: Database Upload\nTriggering final_code.py for PostgreSQL]
        L --> M[Step 20: Outlier Detection\nTrimmed Medians, Flagging & Summary Workbooks]
    end
```

---

## 4. End-to-End Step-by-Step Breakdown (Steps 1 to 20)

### Pre-Step: Target City Selection & Environment Configuration
- **City Registry (`city_config.py`)**: Resolves active city settings (Pune [ID: 9], Mumbai [ID: 8], Thane [ID: 12], Dubai [ID: 15], Abu Dhabi [ID: 1], etc.).
- **Dynamic Drive Binding**: Resolves local Google Drive desktop shortcut paths on `G:\.shortcut-targets-by-id` for:
  - Input Folder (`2. LLM Processed Data`)
  - Manual Review Folder (`3. Manually Corrected`)
  - Final Output Folder (`4. Final processed file`)
- **Divisor Loading (`divisor.py`)**: Sets city-specific Saleable-to-Carpet divisors (e.g., Mumbai: `1.45`, Pune: `1.35`, Dubai: `1.0`).

---

### Step 1: Input File Selection (Location-Wise Drive Browser)
- **Function**: `get_file_from_drive(...)`
- **Source**: `G:\.shortcut-targets-by-id\<input_id>\2. LLM Processed Data\`
- **Mechanism**:
  - Recursively scans the input folder on Google Drive.
  - Groups files by locality subfolders (e.g., Andheri, Kothrud, Wakad).
  - Displays an interactive menu of locations and file counts.
  - Automatically captures `selected_location` for downstream folder structuring.

---

### Step 2: DictToColumn Parsing
- **Module**: `DictToColumn.py` (`process_dict_to_column`)
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
  - Flags provenance in `final_project_name_status`:
    - `"Project Name Considered"`
    - `"Building Name Considered"`

---

### Step 4: Static Dictionary Mapping
- **Module**: `static.py` (`result_dict`, `word_number_dict`)
- **Purpose**: Maps Marathi registration deed names (`docname`) to standardized English transaction descriptions.
- **Logic**:
  - Transforms Marathi deed labels (e.g., खरेदीखत, भाडेपट्टा, बक्षीसपत्र, गहाणखत) into standardized English transaction types (`Sale Deed`, `Lease Deed`, `Gift Deed`, `Mortgage Deed`).

---

### Step 5: Transaction Categorisation
- **Module**: `transaction_categorizer.py` (`categorise`)
- **Purpose**: Group granular transaction types into primary analytical buckets:
  - **`Sale`**: Outright purchases, conveyances, developer-buyer sales.
  - **`Lease / Mortgage`**: Rental agreements, leave & license, mortgage deeds.
  - **`Other`**: Gift deeds, release deeds, conveyances, power of attorney.

---

### Step 5.5: Marathi Village to Location Mapping
- **Function**: `populate_village_mapping(...)`
- **Purpose**: Resolves localized Marathi revenue village names (`village_name_marathi` / `areaname`) against the PostgreSQL database.
- **Mechanism**:
  - Queries `SELECT DISTINCT village_name_marathi, location_name, registered_document_village_name FROM public.transactions WHERE city_id = %s`.
  - Populates standardized `location_name` and `registered_document_village_name`.

---

### Step 6: Project Standardization & Area Conversion (`_for_manual.xlsx`)
- **Module**: `project_name_Std_and_area_conversion.py` (`process_dataframe`)
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
     - RegEx extraction of flat/shop numbers (`unit_number`) and floor numbers (`floor_number`).
  4. **Part D - Net Carpet Area Derivation**:
     - For Sale records with only saleable or buildup area, applies the configured city divisor (`1.45` for Mumbai, `1.35` for Pune) to derive `net_carpet_area_sq_m`.
  5. **Export Multi-Sheet Workbook**:
     - Creates `<Location>_for_manual.xlsx` with review tabs (`Combined`, `Cluster Summary`, `Manual Review`, `Unrecognized Areas`).
     - Saves directly to Google Drive: `3. Manually Corrected/<Location>/`.
  6. **Automated Notification (Optional)**:
     - Prompts user to dispatch an automated email via SMTP with review guidelines, deadline banner, and attachment or Google Drive link to colleagues.

---

### Step 7: Load Manually Corrected File
- **Function**: `get_manual_corrected_file(...)`
- **Purpose**: Pipeline pauses for user review. Once manual corrections to project names and areas are finished, this step loads the reviewed file.
- **Mechanism**:
  - Displays available folders and files in `3. Manually Corrected`.
  - Pressing `Enter` automatically accepts the file generated in Step 6.
  - Supports direct path input.

---

### Step 8: Standardize Schema & Rename Columns
- **Function**: `rename_columns(...)`
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
- **Function**: `_map_property_type(val)`
- **Standardized Categories**:
  - **`Flat`**: Apartment, Flat, Flat/Shop, House, Residential, Room.
  - **`Office`**: Commercial Property, Office, Commercial Wing.
  - **`Shop`**: Commercial Shop, Restaurant/Bar, Shop, Shop/Office.
  - **`Villa`**: Bungalow, Row House, Villa.
  - **`Plot`**: Land, Open Land, Plot.
  - **`Others`**: Unmapped or composite types.

---

### Step 10: Buyer Location & Pincode Enrichment
- **Function**: `add_buyer_location(df, postal_csv_path)`
- **Mechanism**:
  - Extracts 6-digit Indian postal PIN codes from `buyer_name` (e.g., `400053`).
  - Merges against `postal_pincode.csv` (`Pincode`, `OfficeName_P`, `District_P`, `StateName_P`).
  - Enriches `buyer_locality`, `buyer_district`, and `buyer_state`.

---

### Step 11: MahaRERA Master Dataset Matching
- **Module**: `rera_matching.py` (`process_rera_matching`)
- **Dataset**: City-specific RERA master file (e.g., `mumbai RERA GRAND EXCEL VERSION.xlsx`, `Pune RERA GRAND EXCEL VERSION 9.xlsx`).
- **Enrichment Fields**:
  - `index`: Unique MahaRERA project identifier.
  - `modified_project_name`: Verified MahaRERA project title.
  - `project_latitude` & `project_longitude`: Verified project coordinates.
  - `unit_configuration` / `BHK`: 1 BHK, 2 BHK, 3 BHK, etc.
  - `rera_location`: Official registered location.
- Non-RERA cities safely bypass this step with null placeholders.

---

### Intermediate Schema Alignment & Rate Derivation
Before index assignment, `project.py` executes critical financial and chronological derivations:
1. **Quarter Derivation**: Formats `Q1-2026`, `Q2-2026`, etc., from `transaction_date`.
2. **Date Reformatting**: Standardizes dates to `DD/MM/YYYY`.
3. **Net Carpet Area in Sq.Ft**: `net_carpet_area_sqft = net_carpet_area_sq_m * 10.7639`.
4. **Calculated Rate (`rate`)**:
   $$\text{rate} = \frac{\text{agreement\_price}}{\text{net\_carpet\_area\_sqft}}$$
   Standardized to PostgreSQL schema column `rate`.
5. **Database Default Assignments**: Populates defaults for `state_name`, `country_name`, `data_source` ("Igr"), `source_accessibility` ("Easy"), `is_llm_processed` ("Yes"), etc.

---

### Step 12: Assign Non-RERA (NR) Indexes via PostgreSQL
- **Function**: `assign_nr_indexes(...)`
- **Purpose**: Transactions that did not match any MahaRERA project still require a unique project-level tracking ID.
- **Mechanism**:
  - Connects to PostgreSQL:
    ```sql
    SELECT MAX((regexp_match(internal_index_id, '^nr(\d+)', 'i'))[1]::int)
    FROM public.transactions
    WHERE city_id = %s AND internal_index_id ~* '^nr\d+';
    ```
  - Identifies highest existing NR number for the city (e.g., `nr18420`).
  - Sequentially assigns new NR IDs (`nr18421`, `nr18422`, ...) to eligible unindexed projects.

---

### Step 13: Fetch Location Coordinates from Database
- **Function**: `populate_location_coords(...)`
- **Purpose**: Ensures every record has regional geospatial fallback coordinates even if specific project coordinates are missing.
- **Mechanism**:
  - Reads coordinates from `public.dim_location` (`location_latitude`, `location_longitude`) matching on `location_name`.

---

### Step 14: Project Coordinates via Google Places API (Toggleable)
- **Module**: `project_coordinates.py`
- **Status**: Optional / commented out in standard runs to conserve API credits.

---

### Step 15: Filter & Order Selective Database Columns
- **Module**: `db_columns.py` (`DB_SEQUENCE`)
- **Function**: `keep_db_columns(df, DB_SEQUENCE)`
- **Purpose**: Strict schema conformity. Reorders and filters the DataFrame so that column order exactly mirrors `public.transactions` in PostgreSQL.

---

### Step 16: Title Case Normalization
- **Purpose**: Cosmetic consistency across text fields.
- **Logic**: Applies Python `.title()` across all object/string columns.

---

### Step 17: Final Output Save & Automated Checker Notification
- **Naming Pattern**: `<Location>_final_processed.xlsx`
- **Target Folder**: `G:\.shortcut-targets-by-id\<final_drive_id>\4. Final processed file\<Location>\`
- **Verification**: Allows interactive path confirmation, filename customization, and validates directory write permissions.
- **Automated Checker Email**:
  - Spawns background thread via `send_final_checker_email()` in `city_config.py`.
  - Dispatches an automated HTML report to the quality checker (`deeksha@sigmavalue.co.in`).
  - Email includes: City, Location, Row Count, Local Output Path, Google Drive Shareable Folder Link, and timestamp.

---

### Step 18: Parquet Conversion
- **Module**: `parquet_conersion.py` (`convert_csv_to_parquet`)
- **Purpose**: Generates high-speed columnar Parquet format optimized for bulk database loading and analytics.
- **Output Target**:
  `G:\.shortcut-targets-by-id\1oGd6xPdp686p0qW-tzZyy5quOpi82hLA\DB1+DB2\converted_feather_parquet\<City>\<City>_db1.parquet`
- **Type Casting & Date Normalization**: Converts dates safely to string `YYYY-MM-DD` (handling historical and modern dates without 64-bit nanosecond overflows).

---

### Step 19: Trigger Database Upload Pipeline (`final_code.py`)
- **Script**: `E:\Nilesh\Database\DB1_DB2_Uploading_Pipeline\final_code.py`
- **Mechanism**:
  - Uses `subprocess.run([sys.executable, "final_code.py"])` in the target virtual environment.
  - Automatically ingests the final Parquet dataset into the PostgreSQL database (`transactions`, `projects`, `listings`, etc.).

---

### Step 20: Post-Upload Statistical Outlier Detection (`outlier_update.py`)
- **Modules**: `outlier_update.py` and `incremental_outlier_update.py`
- **Purpose**: Classifies newly ingested transactions into statistical categories without skewing historical distributions.
- **Algorithm**:
  - Trims top 1% and bottom 1% records (P1 / P99) per `(city, location, category, property_type)` slice.
  - Computes robust baseline medians.
  - Sets dynamic boundaries:
    $$\text{lower\_limit} = \frac{\text{median}}{4}, \quad \text{upper\_limit} = \text{median} \times 4$$
  - Classifies records: `Normal`, `Lower Outlier`, `Upper Outlier`, `Mumbai Low Price Outlier`, `Zero Area/Price`.
  - Batch updates PostgreSQL columns: `rate`, `is_outlier`, `outlier_type`.
  - Multi-Sheet Audit Export: Generates structured summary reports under `outlier_summaries/`.

---

## 5. Web Dashboard Architecture (`server.py`)

A full-stack, browser-based operations dashboard is provided in `Processing/server.py` and `Processing/web/`:

```
Processing/web/
├── index.html       # Single-page operations interface
├── app.js           # Real-time SSE streaming client & dynamic mode router
└── style.css        # Premium dark-themed design system
```

### Key Web Features:
1. **Interactive Multi-City Selector**: Supports Pune, Mumbai, Thane, Dubai, Abu Dhabi, and database cities from `public.dim_city`.
2. **Dynamic Mode Navigation**:
   - Mode 1: Start (Auto-expands Google Drive input file picker).
   - Mode 2: Resume (Auto-scrolls and focuses Step 7 review file card).
   - Mode 3: Parquet (Focuses Step 18 Parquet conversion card).
   - Mode 4: Outliers (Scrolls to Outlier Detection controls).
3. **Live SSE Terminal Stream**: Real-time terminal output streaming with auto-scroll and status indicators.
4. **Google Drive Directory Picker**: Browses local Google Drive folders dynamically from the UI.

---

## 6. International Data Ingestion (Dubai & Abu Dhabi)

The system extends real estate data processing beyond Indian IGR to Middle Eastern markets:

1. **Automated Scraper (`Processing/Dubai_processing/`)**:
   - `dubai_scraper_all_in_one.py`: Automated Selenium-based scraper for the **Dubai Land Department Open Data Portal**.
   - Automated reCAPTCHA handling, date range filtering, CSV download, and Google Drive upload.
2. **Outlier Grouping Logic**:
   - In `outlier_update.py`, international markets (`dubai`, `abu_dhabi`) have their localities collapsed into `__ALL_LOCATIONS__` to compute unified city-level price distribution metrics.
3. **Parquet & DB Schema Compatibility**:
   - Historical date strings (such as Hijri calendar dates) are serialized safely into Parquet strings without truncation.

---

## 7. Master File & Dependency Registry

| File / Script | Core Functionality & Role |
| :--- | :--- |
| [project.py](file:///e:/Nilesh/IGR_processing_System/Processing/project.py) | Master CLI pipeline orchestrator coordinating Steps 1 through 20. |
| [server.py](file:///e:/Nilesh/IGR_processing_System/Processing/server.py) | FastAPI Web server providing real-time SSE progress streaming and web dashboard. |
| [web/](file:///e:/Nilesh/IGR_processing_System/Processing/web) | Web Dashboard frontend (`index.html`, `app.js`, `style.css`). |
| [city_config.py](file:///e:/Nilesh/IGR_processing_System/Processing/city_config.py) | Central configuration for city IDs, Google Drive IDs, RERA paths, and automated email dispatches. |
| [divisor.py](file:///e:/Nilesh/IGR_processing_System/Processing/divisor.py) | Defines city-specific carpet area divisors (Mumbai: 1.45, Pune: 1.35, Dubai: 1.0). |
| [DictToColumn.py](file:///e:/Nilesh/IGR_processing_System/Processing/DictToColumn.py) | Extracts stringified JSON dictionaries into structured tabular columns. |
| [transaction_categorizer.py](file:///e:/Nilesh/IGR_processing_System/Processing/transaction_categorizer.py) | Rule-based transaction categorizer (Sale, Lease/Mortgage, Other). |
| [project_name_Std_and_area_conversion.py](file:///e:/Nilesh/IGR_processing_System/Processing/project_name_Std_and_area_conversion.py) | TF-IDF n-gram clustering, Marathi area converter, unit/floor parser, and review workbook exporter. |
| [rera_matching.py](file:///e:/Nilesh/IGR_processing_System/Processing/rera_matching.py) | MahaRERA fuzzy matching engine for project name and coordinate enrichment. |
| [postal_pincode.csv](file:///e:/Nilesh/IGR_processing_System/Processing/postal_pincode.csv) | Master Indian postal PIN code database for buyer locality and district mapping. |
| [db_columns.py](file:///e:/Nilesh/IGR_processing_System/Processing/db_columns.py) | Canonical PostgreSQL column sequence definition (`DB_SEQUENCE`). |
| [parquet_conersion.py](file:///e:/Nilesh/IGR_processing_System/Processing/parquet_conersion.py) | High-performance Excel/CSV-to-Parquet conversion utility with type validation. |
| [outlier_update.py](file:///e:/Nilesh/IGR_processing_System/Processing/outlier_update.py) | Incremental statistical outlier detection, IQR calculations, and database updater. |
| [Dubai_processing/](file:///e:/Nilesh/IGR_processing_System/Processing/Dubai_processing) | Automated scraper and Google Drive uploader for Dubai Land Department real estate data. |
