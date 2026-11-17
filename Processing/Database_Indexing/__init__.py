"""
Database Indexing Package
=========================
Centralized indexing utilities for Land Identification and Sales Velocity runbooks.
"""

from .index_definitions import INDEX_CATALOG, INDEX_MAP, REQUIRED_EXTENSIONS
from .db_indexer import (
    check_index_health,
    clean_invalid_indexes,
    ensure_production_indexes,
    verify_query_performance,
    get_connection,
    resolve_db_params,
)

__all__ = [
    "INDEX_CATALOG",
    "INDEX_MAP",
    "REQUIRED_EXTENSIONS",
    "check_index_health",
    "clean_invalid_indexes",
    "ensure_production_indexes",
    "verify_query_performance",
    "get_connection",
    "resolve_db_params",
]

