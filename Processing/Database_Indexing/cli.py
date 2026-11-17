"""
Database Indexer CLI Tool
=========================
Command line runner for auditing, building, and benchmarking production indexes
on public.transactions.

Usage:
    python -m Database_Indexing.cli
    python -m Database_Indexing.cli --check-only
    python -m Database_Indexing.cli --db nilesh
    python -m Database_Indexing.cli --benchmark
"""

import argparse
import sys
from pathlib import Path

# Safe UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tabulate import tabulate

PROCESSING_DIR = Path(__file__).resolve().parent.parent
if str(PROCESSING_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSING_DIR))

from Database_Indexing.db_indexer import (
    check_index_health,
    clean_invalid_indexes,
    ensure_production_indexes,
    verify_query_performance,
    resolve_db_params,
)


def print_health_table(health: dict):
    print("\n" + "=" * 70)
    print(f"  🔍 DATABASE INDEX AUDIT: {health['database']}.{health['table']}")
    print("=" * 70)
    print(f"Estimated Rows : {health['estimated_rows']:,}")
    print(f"Total Rel Size : {health['total_size_pretty']}")
    print(f"Extensions     : {', '.join(health['extensions'])}")
    summary = health["summary"]
    print(f"Index Summary  : Total={summary['total']} | Valid={summary['valid']} | Missing={summary['missing']} | Invalid={summary['invalid']}")
    print("-" * 70)

    rows = []
    for idx in health["indexes"]:
        status_map = {
            "valid": "✅ Valid",
            "missing": "⚠️ Missing",
            "invalid": "❌ INVALID",
        }
        rows.append([
            idx["name"],
            idx["feature"],
            status_map.get(idx["status"], idx["status"]),
            idx["size_pretty"],
            idx["type"],
        ])

    print(tabulate(rows, headers=["Index Name", "Feature", "Status", "Size", "Type"], tablefmt="grid"))
    print("\n")


def main():
    parser = argparse.ArgumentParser(description="Database Indexer for Land Identification & Sales Velocity")
    parser.add_argument("--db", type=str, default=None, help="Database name override (e.g. nilesh, pipeline_one_db1_db2)")
    parser.add_argument("--check-only", action="store_true", help="Only check index health without building")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark EXPLAIN ANALYZE queries")
    parser.add_argument("--clean-invalid", action="store_true", help="Clean up any broken/invalid indexes")

    args = parser.parse_args()
    params = resolve_db_params(override_db=args.db)

    print(f"\nTarget Database: {params['database']} on {params['host']}:{params['port']}")

    if args.clean_invalid:
        print("\nCleaning invalid indexes...")
        cleaned = clean_invalid_indexes(params)
        print(f"Cleaned {len(cleaned)} index(es).")

    health = check_index_health(params)
    print_health_table(health)

    if args.check_only:
        return

    if args.benchmark:
        print("\nRunning benchmark queries...")
        bench = verify_query_performance(params)
        b_rows = []
        for b in bench["benchmarks"]:
            b_rows.append([b["name"], b["expected_index"], b["execution_time"], b["status"]])
        print(tabulate(b_rows, headers=["Benchmark", "Expected Index", "Execution Time", "Status"], tablefmt="grid"))
        return

    # If missing indexes exist, prompt or build
    missing_count = health["summary"]["missing"]
    invalid_count = health["summary"]["invalid"]

    if missing_count == 0 and invalid_count == 0:
        print("🎉 All 12 production indexes are already present and valid! No action needed.")
        return

    print(f"⚠️  Found {missing_count} missing and {invalid_count} invalid index(es).")
    confirm = input("Do you want to build/apply missing indexes now? (y/n) [default: y]: ").strip().lower()
    if confirm in ("", "y", "yes"):
        ensure_production_indexes(params)
        # Re-audit
        print("\nRe-auditing database...")
        new_health = check_index_health(params)
        print_health_table(new_health)
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()
