
"""
Database Indexer Engine
=======================
Applies and audits production indexes on PostgreSQL transactions table
without downtime (CONCURRENTLY) and without modifying table schema or columns.
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

# Safe UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure parent directory is in sys.path so pipeline_core can be imported seamlessly
PROCESSING_DIR = Path(__file__).resolve().parent.parent
if str(PROCESSING_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSING_DIR))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

try:
    import pipeline_core as core
except ImportError:
    core = None

from .index_definitions import INDEX_CATALOG, REQUIRED_EXTENSIONS, INDEX_MAP


def resolve_db_params(override_db: Optional[str] = None, db_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolves active database parameters, prioritizing explicitly passed dict or core.get_db_params."""
    if db_params and isinstance(db_params, dict):
        params = db_params.copy()
        if override_db:
            params["database"] = override_db
        return params

    if core and hasattr(core, "get_db_params"):
        return core.get_db_params(override_db)

    # Fallback to local default
    return {
        "host": "localhost",
        "port": "5432",
        "database": override_db or "nilesh",
        "user": "postgres",
        "password": "nilesh",
    }


def get_connection(db_params: Optional[Dict[str, Any]] = None, autocommit: bool = True):
    """
    Creates a psycopg2 connection with autocommit=True by default.
    MANDATORY: CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    """
    params = resolve_db_params(db_params=db_params)
    conn = psycopg2.connect(**params)
    if autocommit:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def check_index_health(
    db_params: Optional[Dict[str, Any]] = None,
    table_name: str = "transactions",
) -> Dict[str, Any]:
    """
    Audits the current status of all cataloged indexes on the specified table.
    Returns:
      - table_exists: bool
      - estimated_rows: int
      - total_size_pretty: str
      - extensions: List[str]
      - indexes: List[Dict[str, Any]] (status: 'valid', 'missing', 'invalid')
      - summary: counts of valid, missing, invalid
    """
    params = resolve_db_params(db_params=db_params)
    conn = get_connection(params, autocommit=True)
    cur = conn.cursor()

    try:
        # Check installed extensions
        cur.execute("SELECT extname FROM pg_extension;")
        installed_extensions = [r[0] for r in cur.fetchall()]

        # Check table existence & size
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = %s
            );
            """,
            (table_name,),
        )
        table_exists = cur.fetchone()[0]

        if not table_exists:
            return {
                "database": params.get("database"),
                "table": table_name,
                "table_exists": False,
                "estimated_rows": 0,
                "total_size_pretty": "0 MB",
                "extensions": installed_extensions,
                "indexes": [],
                "summary": {"total": len(INDEX_CATALOG), "valid": 0, "missing": len(INDEX_CATALOG), "invalid": 0},
            }

        # Estimated rows & pretty size
        cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = %s;", (table_name,))
        row_estimate = cur.fetchone()
        estimated_rows = int(row_estimate[0]) if row_estimate and row_estimate[0] is not None else 0

        cur.execute("SELECT pg_size_pretty(pg_total_relation_size(%s));", (f"public.{table_name}",))
        total_size = cur.fetchone()[0]

        # Query all existing indexes on this table
        cur.execute(
            """
            SELECT 
                i.relname AS index_name,
                idx.indisvalid AS is_valid,
                pg_size_pretty(pg_relation_size(i.oid)) AS size_pretty,
                pg_relation_size(i.oid) AS size_bytes,
                pg_get_indexdef(idx.indexrelid) AS index_def
            FROM pg_class t
            JOIN pg_index idx ON t.oid = idx.indrelid
            JOIN pg_class i ON i.oid = idx.indexrelid
            WHERE t.relname = %s
            ORDER BY i.relname;
            """,
            (table_name,),
        )
        existing_rows = cur.fetchall()
        existing_map = {
            r[0]: {
                "is_valid": bool(r[1]),
                "size_pretty": r[2],
                "size_bytes": r[3],
                "def": r[4],
            }
            for r in existing_rows
        }

        # Compare against CATALOG
        index_statuses = []
        valid_count = 0
        missing_count = 0
        invalid_count = 0

        for item in INDEX_CATALOG:
            idx_name = item["name"]
            if idx_name in existing_map:
                ex = existing_map[idx_name]
                if ex["is_valid"]:
                    status = "valid"
                    valid_count += 1
                else:
                    status = "invalid"
                    invalid_count += 1
                size_pretty = ex["size_pretty"]
                index_def = ex["def"]
            else:
                status = "missing"
                missing_count += 1
                size_pretty = "-"
                index_def = item["sql"]

            index_statuses.append({
                "name": idx_name,
                "feature": item.get("feature", "Core"),
                "runbook": item.get("runbook", ""),
                "type": item.get("type", "btree"),
                "status": status,
                "size_pretty": size_pretty,
                "description": item.get("description", ""),
                "definition": index_def,
            })

        return {
            "database": params.get("database"),
            "table": table_name,
            "table_exists": True,
            "estimated_rows": estimated_rows,
            "total_size_pretty": total_size,
            "extensions": installed_extensions,
            "indexes": index_statuses,
            "summary": {
                "total": len(INDEX_CATALOG),
                "valid": valid_count,
                "missing": missing_count,
                "invalid": invalid_count,
            },
        }

    finally:
        cur.close()
        conn.close()


def clean_invalid_indexes(
    db_params: Optional[Dict[str, Any]] = None,
    table_name: str = "transactions",
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> List[str]:
    """
    Finds and drops any indexes marked `indisvalid = false` on the target table.
    Necessary if an index build was interrupted mid-way in production.
    """
    params = resolve_db_params(db_params=db_params)
    conn = get_connection(params, autocommit=True)
    cur = conn.cursor()
    dropped = []

    try:
        cur.execute(
            """
            SELECT i.relname
            FROM pg_class t
            JOIN pg_index idx ON t.oid = idx.indrelid
            JOIN pg_class i ON i.oid = idx.indexrelid
            WHERE t.relname = %s AND idx.indisvalid = false;
            """,
            (table_name,),
        )
        invalid_indexes = [r[0] for r in cur.fetchall()]

        for idx_name in invalid_indexes:
            msg = f"Found invalid/broken index '{idx_name}'. Dropping concurrently..."
            if log_fn:
                log_fn(msg, "warning")
            else:
                print(f"⚠️  {msg}")

            cur.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{idx_name};")
            dropped.append(idx_name)

            msg_done = f"Dropped invalid index '{idx_name}' successfully."
            if log_fn:
                log_fn(msg_done, "info")
            else:
                print(f"✓  {msg_done}")

    finally:
        cur.close()
        conn.close()

    return dropped


def ensure_production_indexes(
    db_params: Optional[Dict[str, Any]] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    is_stopped_fn: Optional[Callable[[], bool]] = None,
    target_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Ensures all required indexes exist and are valid on public.transactions:
      1. Installs required extensions (pg_trgm).
      2. Drops any broken/invalid indexes.
      3. Builds missing indexes one-by-one with CREATE INDEX CONCURRENTLY.
      4. Runs ANALYZE public.transactions.
    Zero column/table modifications are performed.
    """
    t_start = time.time()
    params = resolve_db_params(db_params=db_params)
    db_name = params.get("database", "nilesh")

    def _log(msg: str, level: str = "info"):
        if log_fn:
            log_fn(msg, level)
        else:
            icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
            print(f"{icons.get(level, '')} {msg}", flush=True)

    _log(f"Starting Database Index Optimization on '{db_name}'...", "info")

    conn = get_connection(params, autocommit=True)
    cur = conn.cursor()

    built = []
    skipped = []
    errors = []

    try:
        # Step 1: Ensure extensions
        for ext in REQUIRED_EXTENSIONS:
            ext_name = ext["name"]
            try:
                cur.execute(ext["sql"])
                _log(f"Extension '{ext_name}' verified active.", "info")
            except Exception as e:
                _log(f"Note checking extension '{ext_name}': {e}", "warning")

        # Step 2: Clean invalid indexes
        cleaned = clean_invalid_indexes(params, log_fn=log_fn)
        if cleaned:
            _log(f"Cleaned up {len(cleaned)} invalid index(es): {', '.join(cleaned)}", "info")

        # Step 3: Check current state
        health = check_index_health(params)
        existing_valid = {idx["name"] for idx in health["indexes"] if idx["status"] == "valid"}

        # Filter catalog if target_names specified
        targets = [
            item for item in INDEX_CATALOG 
            if not target_names or item["name"] in target_names
        ]

        total_targets = len(targets)
        _log(f"Evaluating {total_targets} required production indexes against '{db_name}.transactions'...", "info")

        for i, item in enumerate(targets, 1):
            if is_stopped_fn and is_stopped_fn():
                _log("Index optimization cancelled by user.", "warning")
                break

            name = item["name"]
            feature = item.get("feature", "Core")

            if name in existing_valid:
                skipped.append(name)
                _log(f"[{i}/{total_targets}] Index '{name}' is already present & valid ({feature}) — skipped.", "info")
                continue

            # Need to build
            sql = item["sql"]
            _log(f"[{i}/{total_targets}] Building index '{name}' ({feature}) CONCURRENTLY...", "info")
            t_idx_start = time.time()

            try:
                cur.execute(sql)
                dur = f"{time.time() - t_idx_start:.2f}s"
                built.append({"name": name, "feature": feature, "duration": dur})
                _log(f"[{i}/{total_targets}] Successfully created '{name}' in {dur}!", "success")
            except Exception as build_err:
                err_msg = f"Failed to build index '{name}': {build_err}"
                errors.append({"name": name, "error": str(build_err)})
                _log(err_msg, "error")

        # Step 4: Refresh Postgres statistics with ANALYZE
        if built:
            _log("Refreshing PostgreSQL query planner statistics (ANALYZE public.transactions)...", "info")
            try:
                cur.execute("ANALYZE public.transactions;")
                _log("ANALYZE public.transactions completed successfully.", "success")
            except Exception as ae:
                _log(f"Note on ANALYZE: {ae}", "warning")

        total_dur = f"{time.time() - t_start:.2f}s"
        summary_msg = f"Indexing finished in {total_dur}: {len(built)} built, {len(skipped)} already valid, {len(errors)} errors."
        _log(summary_msg, "success" if not errors else "warning")

        return {
            "status": "success" if not errors else "partial_error",
            "database": db_name,
            "duration": total_dur,
            "built": built,
            "skipped": skipped,
            "errors": errors,
        }

    finally:
        cur.close()
        conn.close()


def verify_query_performance(
    db_params: Optional[Dict[str, Any]] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """
    Runs EXPLAIN (ANALYZE, BUFFERS) on canonical benchmark queries from both runbooks:
      1. Land Identification exact match (LOWER)
      2. Land Identification fuzzy match (trigram ILIKE)
      3. Sales Velocity bounding box radius query (latitude/longitude)
    Confirms they are using 'Index Scan' or 'Bitmap Index Scan', NOT 'Seq Scan'.
    """
    params = resolve_db_params(db_params=db_params)
    conn = get_connection(params, autocommit=True)
    cur = conn.cursor()

    benchmarks = [
        {
            "name": "Land Identification (Exact Lower Match)",
            "runbook": "Land Identification v1.1",
            "expected_index": "idx_trans_location_name_lower",
            "sql": "EXPLAIN ANALYZE SELECT DISTINCT location_name FROM transactions WHERE LOWER(location_name) = 'wakad' LIMIT 10;",
        },
        {
            "name": "Land Identification (Fuzzy Trigram Match)",
            "runbook": "Land Identification v1.1",
            "expected_index": "idx_trans_location_name_trgm",
            "sql": "EXPLAIN ANALYZE SELECT DISTINCT location_name FROM transactions WHERE location_name ILIKE '%wakad%' LIMIT 10;",
        },
        {
            "name": "Sales Velocity (Spatial Lat/Lng Radius Bounding Box)",
            "runbook": "Sales Velocity Runbook",
            "expected_index": "idx_transactions_lat_lng",
            "sql": """
                EXPLAIN ANALYZE 
                SELECT DISTINCT project_name 
                FROM transactions 
                WHERE project_latitude IS NOT NULL 
                  AND project_longitude IS NOT NULL 
                  AND project_latitude BETWEEN 18.50000000 AND 18.60000000
                  AND project_longitude BETWEEN 73.80000000 AND 73.90000000
                LIMIT 10;
            """,
        },
    ]

    results = []

    try:
        for bench in benchmarks:
            b_name = bench["name"]
            expected = bench["expected_index"]
            try:
                cur.execute(bench["sql"])
                lines = [r[0] for r in cur.fetchall()]
                plan_text = "\n".join(lines)

                uses_index = expected.lower() in plan_text.lower()
                is_seq_scan = "seq scan" in plan_text.lower() and not ("bitmap index scan" in plan_text.lower())

                # Extract execution time
                exec_time_line = next((l for l in lines if "Execution Time:" in l), "Execution Time: N/A")
                exec_time = exec_time_line.replace("Execution Time:", "").strip()

                status = "PASS (Index Scan)" if uses_index else ("PASS (Cached/Alternative Index)" if not is_seq_scan else "FAIL (Seq Scan)")

                results.append({
                    "name": b_name,
                    "runbook": bench["runbook"],
                    "expected_index": expected,
                    "uses_expected_index": uses_index,
                    "execution_time": exec_time,
                    "status": status,
                    "plan_summary": lines[:3],
                })
            except Exception as be:
                results.append({
                    "name": b_name,
                    "runbook": bench["runbook"],
                    "expected_index": expected,
                    "status": f"ERROR: {be}",
                    "execution_time": "N/A",
                })

        return {
            "database": params.get("database"),
            "benchmarks": results,
        }

    finally:
        cur.close()
        conn.close()
