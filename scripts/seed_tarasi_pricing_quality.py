from __future__ import annotations

import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(".env")

from services.db_service import fetch_rows, get_database_mode, get_postgres_connection, insert_row, resolve_table_name, update_row


DEFAULT_RULES = [
    {"rule_name": "default_sedan_base_fare", "rule_type": "base_fare", "vehicle_type": "sedan", "value": 35},
    {"rule_name": "default_sedan_price_per_km", "rule_type": "price_per_km", "vehicle_type": "sedan", "value": 12},
    {"rule_name": "default_sedan_minimum_fare", "rule_type": "minimum_fare", "vehicle_type": "sedan", "value": 55},
    {"rule_name": "default_sedan_waiting_fee", "rule_type": "waiting_fee", "vehicle_type": "sedan", "value": 10},
    {"rule_name": "default_sedan_luggage_fee", "rule_type": "luggage_fee", "vehicle_type": "sedan", "value": 10},
    {"rule_name": "default_sedan_night_fee", "rule_type": "night_fee", "vehicle_type": "sedan", "value": 25},
    {"rule_name": "default_suv_multiplier", "rule_type": "vehicle_multiplier", "vehicle_type": "suv", "value": 1.25},
    {"rule_name": "default_quantum_multiplier", "rule_type": "vehicle_multiplier", "vehicle_type": "quantum", "value": 1.55},
    {"rule_name": "default_vip_multiplier", "rule_type": "vehicle_multiplier", "vehicle_type": "vip", "value": 1.9},
    {"rule_name": "default_airport_fee", "rule_type": "airport_fee", "vehicle_type": "all", "value": 120},
]

LANDMARK_ALIASES = {
    "Kleine Kuppe": ["Grove Mall", "The Grove", "Grove Virgin Active"],
    "Olympia": ["Maerua Mall"],
    "CBD": ["Wernhil", "Avani Windhoek", "Hilton Windhoek", "Central Hospital"],
    "Prosperita": ["Windhoek Country Club", "Prosperita Industrial", "B1 City"],
    "Katutura": ["Katutura Hospital", "Northern Industrial"],
    "Pioneers Park": ["UNAM Main Campus"],
    "Windhoek West": ["NUST"],
    "Eros Airport": ["Eros Airport"],
    "Hosea Kutako Airport": ["Hosea Kutako Airport"],
    "Goreangab": ["Brakwater", "Lafrenz"],
}


def _now() -> str:
    return datetime.now().isoformat()


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_obvious_test_rule(row: dict) -> bool:
    haystack = " ".join(
        [
            str(row.get("rule_name") or ""),
            str(row.get("description") or ""),
            str(row.get("vehicle_type") or ""),
        ]
    ).lower()
    return any(term in haystack for term in ["test", "ops", "write test"])


def _is_obvious_test_zone(row: dict) -> bool:
    haystack = " ".join(
        [
            str(row.get("zone_name") or ""),
            str(row.get("suburb_area") or ""),
            str(row.get("description") or ""),
        ]
    ).lower()
    return any(term in haystack for term in ["test zone", "ops test", "windhoek test", "test area"])


def _ensure_aliases_column() -> bool:
    if get_database_mode() != "neon" or not resolve_table_name("pricing_zones"):
        return False
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE pricing_zones ADD COLUMN IF NOT EXISTS aliases JSONB DEFAULT '[]'::jsonb")
        conn.commit()
    return True


def _merge_aliases(existing: object, additions: list[str]) -> list[str]:
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except Exception:
            existing = [existing]
    existing_list = existing if isinstance(existing, list) else []
    seen: set[str] = set()
    merged: list[str] = []
    for item in existing_list + additions:
        text = str(item or "").strip()
        if not text:
            continue
        key = _normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def deactivate_test_rules() -> int:
    count = 0
    for row in fetch_rows("pricing_rules", limit=500, order_by="created_at desc nulls last"):
        if row.get("is_active") and _is_obvious_test_rule(row):
            updated = update_row("pricing_rules", "id", row["id"], {"is_active": False, "updated_at": _now()})
            if updated:
                count += 1
    return count


def deactivate_test_zones() -> int:
    count = 0
    for row in fetch_rows("pricing_zones", limit=500, order_by="created_at desc nulls last"):
        if row.get("is_active") and _is_obvious_test_zone(row):
            updated = update_row("pricing_zones", "id", row["id"], {"is_active": False, "updated_at": _now()})
            if updated:
                count += 1
    return count


def upsert_default_rules() -> tuple[int, int]:
    created = 0
    updated = 0
    rows = fetch_rows("pricing_rules", limit=500, order_by="created_at desc nulls last")
    for rule in DEFAULT_RULES:
        matches = [
            row for row in rows
            if _normalize_text(row.get("rule_type")) == _normalize_text(rule["rule_type"])
            and _normalize_text(row.get("vehicle_type") or "all") == _normalize_text(rule["vehicle_type"])
            and not _is_obvious_test_rule(row)
        ]
        payload = {
            **rule,
            "description": "Tarasi default operational pricing rule",
            "is_active": True,
            "updated_at": _now(),
        }
        if matches:
            target = matches[0]
            if update_row("pricing_rules", "id", target["id"], payload):
                updated += 1
        else:
            payload["created_at"] = payload["updated_at"]
            if insert_row("pricing_rules", payload):
                created += 1
    return created, updated


def update_zone_aliases() -> tuple[int, int]:
    alias_updates = 0
    zone_rows_touched = 0
    rows = fetch_rows("pricing_zones", limit=500, order_by="zone_name asc")
    by_name = {_normalize_text(row.get("zone_name")): row for row in rows}
    for zone_name, aliases in LANDMARK_ALIASES.items():
        row = by_name.get(_normalize_text(zone_name))
        if not row:
            continue
        merged = _merge_aliases(row.get("aliases"), aliases)
        updated = update_row("pricing_zones", "id", row["id"], {"aliases": merged, "updated_at": _now()})
        if updated:
            zone_rows_touched += 1
            alias_updates += len(merged)
    return zone_rows_touched, alias_updates


def main() -> None:
    if get_database_mode() != "neon":
        raise SystemExit("Neon DATABASE_URL is required for pricing quality seeding.")
    _ensure_aliases_column()
    deactivated_rules = deactivate_test_rules()
    deactivated_zones = deactivate_test_zones()
    created_rules, updated_rules = upsert_default_rules()
    zone_rows_touched, alias_updates = update_zone_aliases()
    active_rules = len(fetch_rows("pricing_rules", filters={"is_active": True}, limit=500))
    active_zones = len(fetch_rows("pricing_zones", filters={"is_active": True}, limit=500))
    print(
        {
            "active_pricing_rules_count": active_rules,
            "deactivated_test_rules_count": deactivated_rules,
            "deactivated_test_zones_count": deactivated_zones,
            "created_default_rules": created_rules,
            "updated_default_rules": updated_rules,
            "zones_updated": zone_rows_touched,
            "aliases_updated": alias_updates,
            "active_zones_count": active_zones,
        }
    )


if __name__ == "__main__":
    main()
