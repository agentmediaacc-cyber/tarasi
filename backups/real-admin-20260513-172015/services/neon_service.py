from __future__ import annotations

from .db_service import get_db_status, get_neon_connection, get_schema_status, resolve_table_name, test_neon_connection


def neon_available() -> bool:
    connected, _error = test_neon_connection()
    return connected


def neon_schema_ready() -> bool:
    return bool(get_schema_status().get("schema_ready"))


def neon_missing_tables() -> list[str]:
    return list(get_schema_status().get("missing_tables", []))


__all__ = [
    "get_db_status",
    "get_neon_connection",
    "get_schema_status",
    "resolve_table_name",
    "test_neon_connection",
    "neon_available",
    "neon_schema_ready",
    "neon_missing_tables",
]

