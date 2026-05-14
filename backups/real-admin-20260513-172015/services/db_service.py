from __future__ import annotations

import json
import os
from contextlib import closing
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2 import OperationalError, sql
from psycopg2.extras import Json, RealDictCursor

from .storage_service import load_json, save_json
from .supabase_service import get_supabase_config


TABLE_ALIASES = {
    "profiles": ["profiles", "tarasi_profiles", "tarasi_users"],
    "bookings": ["bookings", "tarasi_bookings"],
    "routes": ["routes", "tarasi_routes"],
    "fleet": ["fleet", "vehicles", "tarasi_fleet"],
    "vehicles": ["vehicles", "fleet", "tarasi_fleet"],
    "tours": ["tours", "tarasi_tours"],
    "support_tickets": ["support_tickets", "tarasi_support_tickets"],
    "drivers": ["drivers", "tarasi_drivers"],
    "payments": ["payments", "tarasi_payments"],
}
DEV_JSON_TABLES = {
    "bookings": "bookings.json",
    "routes": "routes.json",
    "fleet": "cars.json",
    "vehicles": "cars.json",
    "tours": "tours.json",
    "support_tickets": "support_tickets.json",
    "drivers": "drivers_profiles.json",
    "profiles": "users.json",
    "payments": "payments.json",
}
EXPECTED_TABLES = ["profiles", "bookings", "routes", "fleet", "tours", "drivers", "support_tickets"]
_TABLE_CACHE: dict[str, str] = {}


def get_database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    return value or None


def get_database_url_exists() -> bool:
    return bool(get_database_url())


def get_database_mode() -> str:
    if get_database_url_exists():
        return "neon"
    config = get_supabase_config()
    if config["url"] and (config["service_key"] or config["anon_key"]):
        return "supabase"
    return "json_dev_fallback"


def get_supabase_client(use_service_role: bool = True) -> dict[str, str]:
    config = get_supabase_config()
    key = config["service_key"] if use_service_role else config["anon_key"]
    if not config["url"] or not key:
        raise RuntimeError("Supabase configuration is not available.")
    return {"url": config["url"].rstrip("/"), "key": key}


def get_postgres_connection():
    database_url = get_database_url()
    if not database_url:
        raise OperationalError("DATABASE_URL is not configured.")
    return psycopg2.connect(database_url, connect_timeout=5)


def get_neon_connection():
    return get_postgres_connection()


def test_neon_connection() -> tuple[bool, str | None]:
    if not get_database_url_exists():
        return False, "DATABASE_URL is missing."
    try:
        with closing(get_postgres_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
        return True, None
    except Exception as exc:  # pragma: no cover - connectivity guard
        return False, str(exc)


def db_available() -> bool:
    mode = get_database_mode()
    if mode == "neon":
        ok, _error = test_neon_connection()
        return ok
    if mode == "supabase":
        try:
            _supabase_request("GET", "/rest/v1/")
            return True
        except Exception:
            return False
    return True


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in (filters or {}).items() if value not in (None, "")}


def _json_table_name(table: str) -> str | None:
    return DEV_JSON_TABLES.get(table, DEV_JSON_TABLES.get(_logical_table(table)))


def _logical_table(table: str) -> str:
    for logical_name, aliases in TABLE_ALIASES.items():
        if table == logical_name or table in aliases:
            return logical_name
    return table


def _candidates(table: str) -> list[str]:
    logical = _logical_table(table)
    return TABLE_ALIASES.get(logical, [table])


def resolve_table_name(table: str) -> str | None:
    cached = _TABLE_CACHE.get(table)
    if cached:
        return cached
    if get_database_mode() != "neon":
        actual = _candidates(table)[0]
        _TABLE_CACHE[table] = actual
        return actual
    try:
        with closing(get_postgres_connection()) as conn:
            with conn.cursor() as cursor:
                actual = _resolve_table_with_cursor(cursor, table)
                if actual:
                    _TABLE_CACHE[table] = actual
                return actual
    except Exception:
        return None
    

def _resolve_table_with_cursor(cursor, table: str) -> str | None:
    for candidate in _candidates(table):
        cursor.execute("select to_regclass(%s)", (candidate,))
        row = cursor.fetchone()
        if row and row[0]:
            return candidate
    return None


def get_schema_status() -> dict[str, Any]:
    mode = get_database_mode()
    if mode == "json_dev_fallback":
        return {
            "mode": mode,
            "connected": True,
            "schema_ready": False,
            "missing_tables": EXPECTED_TABLES,
            "setup_required": True,
            "error": "Database environment variables are not configured.",
        }
    if mode == "supabase":
        return {
            "mode": mode,
            "connected": db_available(),
            "schema_ready": False,
            "missing_tables": EXPECTED_TABLES,
            "setup_required": True,
            "error": None if db_available() else "Supabase REST could not be reached.",
        }

    try:
        with closing(get_postgres_connection()) as conn:
            with conn.cursor() as cursor:
                missing_tables = []
                for table in EXPECTED_TABLES:
                    resolved = _resolve_table_with_cursor(cursor, table)
                    if resolved:
                        _TABLE_CACHE[table] = resolved
                    else:
                        missing_tables.append(table)
        return {
            "mode": mode,
            "connected": True,
            "schema_ready": not missing_tables,
            "missing_tables": missing_tables,
            "setup_required": bool(missing_tables),
            "error": None,
        }
    except Exception as exc:
        return {
            "mode": mode,
            "connected": False,
            "schema_ready": False,
            "missing_tables": EXPECTED_TABLES,
            "setup_required": True,
            "error": str(exc),
        }


def get_db_status() -> dict[str, Any]:
    mode = get_database_mode()
    if mode == "json_dev_fallback":
        return {
            "database": mode,
            "database_url_exists": False,
            "connected": False,
            "schema_ready": False,
            "setup_required": True,
            "missing_tables": EXPECTED_TABLES,
            "error": "DATABASE_URL is missing.",
        }

    if mode == "supabase":
        health = get_schema_status()
        return {
            "database": "supabase",
            "database_url_exists": False,
            "connected": health["connected"],
            "schema_ready": health["schema_ready"],
            "setup_required": health["setup_required"],
            "missing_tables": health["missing_tables"],
            "error": health["error"],
        }

    try:
        with closing(get_postgres_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("select current_database()")
                database_name = cursor.fetchone()[0]
                missing_tables = []
                for table in EXPECTED_TABLES:
                    resolved = _resolve_table_with_cursor(cursor, table)
                    if resolved:
                        _TABLE_CACHE[table] = resolved
                    else:
                        missing_tables.append(table)
        return {
            "database": "neon",
            "database_url_exists": True,
            "connected": True,
            "database_name": database_name,
            "schema_ready": not missing_tables,
            "setup_required": bool(missing_tables),
            "missing_tables": missing_tables,
            "error": None,
        }
    except Exception as exc:
        return {
            "database": "neon",
            "database_url_exists": True,
            "connected": False,
            "schema_ready": False,
            "setup_required": True,
            "missing_tables": EXPECTED_TABLES,
            "error": str(exc),
        }


def fetch_rows(table: str, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    mode = get_database_mode()
    normalized_filters = _normalize_filters(filters)

    if mode == "neon":
        actual_table = resolve_table_name(table)
        if not actual_table:
            return []
        where_parts = []
        values: list[Any] = []
        for key, value in normalized_filters.items():
            where_parts.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
            values.append(value)
        query = sql.SQL("select * from {}").format(sql.Identifier(actual_table))
        if where_parts:
            query += sql.SQL(" where ") + sql.SQL(" and ").join(where_parts)
        query += sql.SQL(" order by created_at desc nulls last")
        if limit:
            query += sql.SQL(" limit %s")
            values.append(limit)
        try:
            with closing(get_postgres_connection()) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, tuple(values))
                    return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    if mode == "supabase":
        actual_table = _candidates(table)[0]
        params = {"select": "*"}
        if limit:
            params["limit"] = str(limit)
        for key, value in normalized_filters.items():
            params[key] = f"eq.{value}"
        try:
            payload = _supabase_request("GET", f"/rest/v1/{actual_table}?{urlencode(params)}")
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    file_name = _json_table_name(table)
    if not file_name:
        return []
    rows = load_json(file_name, [])
    if not isinstance(rows, list):
        return []
    filtered = [
        row for row in rows
        if all(str(row.get(key, "")) == str(value) for key, value in normalized_filters.items())
    ]
    return filtered[:limit] if limit else filtered


def insert_row(table: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    mode = get_database_mode()
    if mode == "neon":
        actual_table = resolve_table_name(table)
        if not actual_table:
            return None
        keys = list(payload.keys())
        query = sql.SQL("insert into {} ({}) values ({}) returning *").format(
            sql.Identifier(actual_table),
            sql.SQL(", ").join(sql.Identifier(key) for key in keys),
            sql.SQL(", ").join(sql.Placeholder() for _ in keys),
        )
        values = [Json(value) if isinstance(value, (dict, list)) else value for value in payload.values()]
        try:
            with closing(get_postgres_connection()) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, values)
                    row = cursor.fetchone()
                conn.commit()
            return dict(row) if row else None
        except Exception:
            return None

    if mode == "supabase":
        actual_table = _candidates(table)[0]
        try:
            payload_result = _supabase_request(
                "POST",
                f"/rest/v1/{actual_table}",
                payload,
                headers={"Prefer": "return=representation"},
            )
            if isinstance(payload_result, list) and payload_result:
                return payload_result[0]
            return payload_result if isinstance(payload_result, dict) else None
        except Exception:
            return None

    file_name = _json_table_name(table)
    if not file_name:
        return None
    rows = load_json(file_name, [])
    if not isinstance(rows, list):
        rows = []
    rows.append(payload)
    save_json(file_name, rows)
    return payload


def update_row(table: str, match_field: str, match_value: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    mode = get_database_mode()
    if mode == "neon":
        actual_table = resolve_table_name(table)
        if not actual_table:
            return None
        keys = list(payload.keys())
        query = sql.SQL("update {} set {} where {} = %s returning *").format(
            sql.Identifier(actual_table),
            sql.SQL(", ").join(
                sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder()) for key in keys
            ),
            sql.Identifier(match_field),
        )
        values = [Json(value) if isinstance(value, (dict, list)) else value for value in payload.values()]
        values.append(match_value)
        try:
            with closing(get_postgres_connection()) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, values)
                    row = cursor.fetchone()
                conn.commit()
            return dict(row) if row else None
        except Exception:
            return None

    if mode == "supabase":
        actual_table = _candidates(table)[0]
        try:
            payload_result = _supabase_request(
                "PATCH",
                f"/rest/v1/{actual_table}?{urlencode({match_field: f'eq.{match_value}'})}",
                payload,
                headers={"Prefer": "return=representation"},
            )
            if isinstance(payload_result, list) and payload_result:
                return payload_result[0]
            return payload_result if isinstance(payload_result, dict) else None
        except Exception:
            return None

    file_name = _json_table_name(table)
    if not file_name:
        return None
    rows = load_json(file_name, [])
    if not isinstance(rows, list):
        return None
    for index, row in enumerate(rows):
        if row.get(match_field) == match_value:
            rows[index] = {**row, **payload}
            save_json(file_name, rows)
            return rows[index]
    return None


def _supabase_request(method: str, path: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    client = get_supabase_client(use_service_role=True)
    request_headers = {
        "apikey": client["key"],
        "Authorization": f"Bearer {client['key']}",
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update(headers)
    request = Request(
        f"{client['url']}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8") or str(exc)) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Supabase: {exc.reason}") from exc
