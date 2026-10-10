# Dubai Land Department (DLD) Real Estate Data Scraping & Processing Pipeline

Automated extraction, schema normalization, database enrichment, and NR index allocation pipeline for **Dubai Land Department Open Data Portal** ([https://dubailand.gov.ae/en/open-data/real-estate-data/#/](https://dubailand.gov.ae/en/open-data/real-estate-data/#/)).

---

## 📌 Architecture & Components

The Dubai pipeline consists of two tightly integrated components:

```
Dubai_processing/
├── dubai_scraper.py             # 📥 Part 1: Automated Selenium Web Scraper & Google Drive Sync
├── dld_pipeline.py              # ⚙️ Part 2: End-to-End Data Transformation & Database Ingestion
├── project_coordinates.ipynb    # 🗺️ Geocoding and coordinate exploration notebook
├── requirements.txt             # 📦 Python dependencies (selenium, psycopg2-binary, pandas, etc.)
└── downloads/                   # 📂 Local cache for downloaded raw DLD CSV files
```

---

## 🚀 1. Dubai Scraper (`dubai_scraper.py`)

Automates downloading transactional CSV datasets directly from the DLD Open Data portal:

### Key Features:
- **Automatic Last Date Retrieval**: Automatically connects to PostgreSQL (`public.transactions WHERE city_id = 15`) and queries the latest existing transaction date. Uses that as `--from-date` to fetch only incremental records.
- **Automated reCAPTCHA Solver**: Detects and interacts with the Google reCAPTCHA checkbox inside the portal iframe.
- **Headless & Interactive Modes**: Can run headlessly in CI/CD / scheduled cron jobs or in visual GUI mode.
- **Local Download Verification**: Polls the download directory until Chrome finishes writing `.csv` (preventing partial `.crdownload` reads).
- **Google Drive Auto-Upload**: Uses Service Account or OAuth credentials to stream downloaded CSVs directly to the configured Google Drive folder (`1CyL3ecimjHLcpUv2AfP8d6fJXNbOcVVE`).

### Scraper Usage:
```bash
# Run with automatic date discovery from DB
python dubai_scraper.py

# Specify custom date range (DD/MM/YYYY)
python dubai_scraper.py --from-date 01/09/2026 --to-date 30/09/2026

# Run in headless mode without browser window
python dubai_scraper.py --headless --non-interactive
```

---

## ⚙️ 2. Dubai Processing Pipeline (`dld_pipeline.py`)

Performs comprehensive data cleaning, PostgreSQL reference enrichment, and Non-RERA (NR) index allocation in two automated phases:

### Phase 1: Data Cleaning & Master Schema Normalization
1. **Raw CSV Ingestion & Deduplication**: Reads raw CSV files (`dtype=str`, UTF-8 BOM encoding) and drops duplicate transaction IDs.
2. **Temporal Parsing**: Extracts `year` and `quarter` (e.g., `Q3-2026`) from `INSTANCE_DATE`.
3. **Column Mapping**: Normalizes raw DLD fields to internal PostgreSQL schema:
   - `procedure_area` -> `net_carpet_area_sq_m`
   - `actual_worth` -> `agreement_price`
   - `procedure_name` -> `transaction_category`
   - `property_type_raw` -> `property_type` (Villa, Flat, Office, Shop, etc.)
4. **PostgreSQL Spatial & Project Enrichment**:
   - Queries `public.dim_project` and `public.dim_location` (scoped to `city_id = 15`).
   - Pulls `project_latitude`, `project_longitude`, `location_latitude`, `location_longitude`.
   - Populates existing internal project index if both `project_name` and `location_name` match.
5. **Cosmetic Title-Casing**: Normalizes casing across all string columns.

### Phase 2: NR Index Allocation
1. **Sequential NR ID Generation**: Queries the highest existing `nrXXXX` index for Dubai (`city_id = 15`) from `public.transactions`.
2. **Project-Location Key Mapping**: Reuses existing project IDs across rows sharing identical `(project_name, location_name, city_name)`.
3. **Collision Checking**: Guarantees no conflicting or overlapping index IDs.
4. **Final Export**: Produces normalized CSV / Excel datasets ready for direct database loading and outlier analysis.

### Pipeline Usage:
```bash
# Run processing on downloaded dataset
python dld_pipeline.py --db nilesh
```

---

## 🔗 Integrated Execution

You can run the entire Dubai workflow seamlessly through the master pipeline:

### Via CLI (`project.py`):
When selecting **Dubai** (City ID `15`):
```
  [1] Run FULL Workflow (Step 1: Scraping ➔ Step 2: Processing)
  [2] Run Step 1 ONLY: Scraping (dubai_scraper.py)
  [3] Run Step 2 ONLY: Processing (dld_pipeline.py)
```

### Via Web Dashboard (`server.py`):
Select `Dubai` in the City dropdown to access automated DLD scraping and processing controls with real-time SSE progress streaming.
