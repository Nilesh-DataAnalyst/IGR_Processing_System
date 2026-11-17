"""
Database Index Definitions for IGR & Real Estate Pipeline
==========================================================
Defines all production indexes required on the `public.transactions` table
as mandated by:
  1. Land Identification Optimization Runbook (v1.1)
  2. Sales Velocity Production Runbook

IMPORTANT:
- No columns are added or removed.
- No DB structural/table schema changes are made.
- Indexes are applied CONCURRENTLY to ensure zero downtime on live systems.
"""

# Extensions required before creating specific indexes
REQUIRED_EXTENSIONS = [
    {
        "name": "pg_trgm",
        "sql": "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
        "description": "PostgreSQL trigram matching extension (powers fuzzy ILIKE search for villages)",
    }
]

# Production Index Catalog for public.transactions
INDEX_CATALOG = [
    # ── Land Identification Optimization (Runbook 1) ──────────────────────
    {
        "name": "idx_trans_location_name_lower",
        "table": "transactions",
        "type": "btree (functional)",
        "feature": "Land Identification",
        "runbook": "Land Identification v1.1",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_location_name_lower ON public.transactions (LOWER(location_name));",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_location_name_lower;",
        "description": "Functional B-tree on LOWER(location_name). Powers exact village name lookup (5s -> 59ms).",
        "verify_sql": "SELECT 1 FROM transactions WHERE LOWER(location_name) = 'wakad' LIMIT 1;",
    },
    {
        "name": "idx_trans_location_name_trgm",
        "table": "transactions",
        "type": "gin (trigram)",
        "feature": "Land Identification",
        "runbook": "Land Identification v1.1",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_location_name_trgm ON public.transactions USING GIN (location_name gin_trgm_ops);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_location_name_trgm;",
        "description": "GIN trigram index on location_name. Powers fuzzy village name search ILIKE '%pattern%' (5s -> 45ms).",
        "required_extension": "pg_trgm",
        "verify_sql": "SELECT 1 FROM transactions WHERE location_name ILIKE '%wakad%' LIMIT 1;",
    },
    {
        "name": "idx_trans_country_name",
        "table": "transactions",
        "type": "btree",
        "feature": "Land Identification",
        "runbook": "Land Identification v1.1",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_country_name ON public.transactions (country_name);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_country_name;",
        "description": "B-tree on country_name. Future-proofing for multi-country datasets.",
    },
    {
        "name": "idx_trans_country_city",
        "table": "transactions",
        "type": "btree (composite)",
        "feature": "Land Identification",
        "runbook": "Land Identification v1.1",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_country_city ON public.transactions (country_name, city_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_country_city;",
        "description": "Composite B-tree on (country_name, city_id). Optimizes country/city group lookups.",
    },

    # ── Sales Velocity Optimization (Runbook 2) ───────────────────────────
    {
        "name": "idx_transactions_lat_lng",
        "table": "transactions",
        "type": "btree (composite)",
        "feature": "Sales Velocity",
        "runbook": "Sales Velocity Production Runbook",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_lat_lng ON public.transactions (project_latitude, project_longitude);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_transactions_lat_lng;",
        "description": "Composite B-tree on (project_latitude, project_longitude). Spatial radius search drops from ~5,000ms to ~5ms.",
        "verify_sql": "SELECT 1 FROM transactions WHERE project_latitude BETWEEN 18.5 AND 18.6 AND project_longitude BETWEEN 73.8 AND 73.9 LIMIT 1;",
    },

    # ── Core Baseline Pipeline Indexes ────────────────────────────────────
    {
        "name": "idx_trans_city",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_city ON public.transactions (city_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_city;",
        "description": "B-tree on city_id for city-level filtering.",
    },
    {
        "name": "idx_trans_location",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_location ON public.transactions (location_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_location;",
        "description": "B-tree on location_id for locality dimension joins.",
    },
    {
        "name": "idx_trans_project",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_project ON public.transactions (project_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_project;",
        "description": "B-tree on project_id for project dimension joins.",
    },
    {
        "name": "idx_trans_transaction_category",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_transaction_category ON public.transactions (transaction_category_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_transaction_category;",
        "description": "B-tree on transaction_category_id.",
    },
    {
        "name": "idx_trans_transaction_date",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_transaction_date ON public.transactions (transaction_date);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_transaction_date;",
        "description": "B-tree on transaction_date for date-range analytics.",
    },
    {
        "name": "idx_trans_year",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_year ON public.transactions (year);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_year;",
        "description": "B-tree on year for yearly slicing.",
    },
    {
        "name": "idx_trans_internal_index",
        "table": "transactions",
        "type": "btree",
        "feature": "Core Pipeline",
        "runbook": "Baseline Schema",
        "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trans_internal_index ON public.transactions (internal_index_id);",
        "drop_sql": "DROP INDEX CONCURRENTLY IF EXISTS public.idx_trans_internal_index;",
        "description": "B-tree on internal_index_id for NR project key matching.",
    },
]

# Quick lookup dict by name
INDEX_MAP = {idx["name"]: idx for idx in INDEX_CATALOG}

