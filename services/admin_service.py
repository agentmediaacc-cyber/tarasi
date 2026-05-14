from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from flask import url_for

from services.booking_service import list_bookings
from services.db_service import count_rows, fetch_rows, get_database_mode, get_db_status, get_schema_status, insert_row, resolve_table_name, update_row

# Simple in-memory cache for dashboard metrics (60 seconds)
_DASHBOARD_CACHE = {"data": None, "timestamp": None}

def _get_cached_metrics():
    now = datetime.now()
    if _DASHBOARD_CACHE["data"] and _DASHBOARD_CACHE["timestamp"]:
        if (now - _DASHBOARD_CACHE["timestamp"]).total_seconds() < 60:
            return _DASHBOARD_CACHE["data"]
    return None

def _set_cached_metrics(data):
    _DASHBOARD_CACHE["data"] = data
    _DASHBOARD_CACHE["timestamp"] = datetime.now()
from services.driver_service import assign_driver_to_booking, list_drivers
from services.tarasi_pricing_engine import (
    get_invoice_by_booking_number,
    get_payment_by_booking_number,
    list_bookings as list_pricing_bookings,
    list_quotes,
)
from services.supabase_service import get_supabase_health


STATUS_GROUPS = {
    "pending": {"booking_received"},
    "confirmed": {"confirmed"},
    "active": {"driver_assigned", "on_the_way", "arrived", "picked_up"},
    "completed": {"completed"},
    "cancellation_requested": {"cancellation_requested"},
    "cancelled": {"cancelled"},
}


def _real_backend_ready() -> bool:
    status = get_db_status()
    return status.get("database") in {"neon", "supabase"} and bool(status.get("connected"))


def _safe_rows(table: str, limit: int | None = None, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not _real_backend_ready():
        return []
    rows = fetch_rows(table, filters=filters, limit=limit)
    return rows if isinstance(rows, list) else []


def _status_from_db(status: Any) -> str:
    raw = str(status or "").replace("_", " ").strip()
    return raw.title() if raw else "Unknown"


def _status_key(value: Any) -> str:
    return str(value or "").lower().replace(" ", "_")


def _amount_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("N$", "").replace(",", "").replace("From ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _money(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"N${value:,.2f}"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raw = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _normalize_booking(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    pickup = row.get("pickup") or row.get("pickup_location") or row.get("from") or ""
    dropoff = row.get("dropoff") or row.get("dropoff_location") or row.get("to") or ""
    status = row.get("status")
    if row.get("customer_name") is not None:
        status = _status_from_db(status)
    return {
        "reference": row.get("reference") or row.get("booking_reference") or "",
        "full_name": row.get("full_name") or row.get("customer_name") or row.get("name") or "",
        "email": row.get("email") or row.get("account_email") or "",
        "phone": row.get("phone") or "",
        "booking_type": row.get("booking_type") or "unknown",
        "pickup": pickup,
        "dropoff": dropoff,
        "date": row.get("date") or (row.get("pickup_date").isoformat() if hasattr(row.get("pickup_date"), "isoformat") else row.get("pickup_date")) or "",
        "time": str(row.get("time") or row.get("pickup_time") or ""),
        "status": status or "Unknown",
        "status_key": _status_key(status),
        "payment_status": row.get("payment_status") or "",
        "amount": row.get("amount") or row.get("estimated_price") or "",
        "amount_value": _amount_number(row.get("amount") or row.get("estimated_price")),
        "driver_name": row.get("driver_name") or metadata.get("driver_name") or "",
        "driver_id": row.get("driver_id") or metadata.get("driver_id") or "",
        "driver_phone": row.get("driver_phone") or metadata.get("driver_phone") or "",
        "vehicle_name": row.get("preferred_vehicle") or row.get("car") or metadata.get("vehicle_name") or "",
        "booking_pin": row.get("booking_pin") or metadata.get("booking_pin") or "",
        "last_location_at": row.get("last_location_at") or metadata.get("last_location_at") or "",
        "admin_note": metadata.get("admin_note", ""),
        "cancel_request_note": row.get("cancel_request_note") or metadata.get("cancel_request_note", ""),
        "request_change_note": row.get("request_change_note") or metadata.get("request_change_note", ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "raw": row,
    }


def _normalize_driver(row: dict[str, Any]) -> dict[str, Any]:
    assigned_vehicle = row.get("assigned_vehicle") if isinstance(row.get("assigned_vehicle"), dict) else {}
    return {
        "id": row.get("id") or row.get("driver_id") or "",
        "driver_id": row.get("driver_id") or row.get("id") or "",
        "full_name": row.get("full_name") or row.get("name") or row.get("email") or "Driver",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
        "based_area": row.get("based_area") or row.get("base_area") or "",
        "service_type": row.get("service_type") or "",
        "availability": row.get("availability") or row.get("status") or "Unknown",
        "verification_status": row.get("verification_status") or "",
        "documents_status": row.get("documents_status") or row.get("verification_status") or "",
        "admin_approved": bool(row.get("admin_approved")),
        "assigned_vehicle": assigned_vehicle,
        "assigned_vehicle_name": assigned_vehicle.get("name") or row.get("vehicle_name") or "",
        "vehicle_name": row.get("vehicle_name") or assigned_vehicle.get("name") or "",
        "vehicle_id": row.get("vehicle_id") or assigned_vehicle.get("vehicle_id") or "",
        "status": row.get("status") or row.get("availability") or "Unknown",
        "current_lat": row.get("current_lat"),
        "current_lng": row.get("current_lng"),
        "last_location_at": row.get("last_location_at") or "",
        "verified": bool(row.get("verified") or row.get("admin_approved")),
        "rating": row.get("rating") or "",
        "balance": row.get("balance") or "",
        "total_trips": row.get("total_trips") or 0,
        "documents": row.get("documents") if isinstance(row.get("documents"), list) else [],
        "raw": row,
    }


def _normalize_customer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": row.get("full_name") or row.get("name") or row.get("email") or "Customer",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
        "town": row.get("town") or row.get("city") or "",
        "wallet_balance": row.get("wallet_balance") or "",
        "loyalty_points": row.get("loyalty_points") or 0,
        "blocked": bool(row.get("blocked") or row.get("is_blocked")),
        "saved_places": row.get("saved_places") if isinstance(row.get("saved_places"), list) else [],
        "raw": row,
    }


def _normalize_vehicle(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "driver_id": row.get("driver_id"),
        "name": row.get("name") or row.get("vehicle_type") or "Vehicle",
        "vehicle_type": row.get("vehicle_type") or "",
        "plate_number": row.get("plate_number") or "",
        "status": row.get("status") or "Unknown",
        "seats": row.get("seats") or "",
        "luggage": row.get("luggage_capacity") or row.get("luggage") or "",
        "aircon": row.get("aircon"),
        "image_url": row.get("image_url") or "",
        "fleet_group_id": row.get("fleet_group_id") or "",
        "image": row.get("image") or "",
        "assigned_driver": row.get("assigned_driver") or row.get("driver_name") or "",
        "maintenance_status": row.get("maintenance_status") or row.get("condition_status") or "",
        "service_date": row.get("service_date") or "",
        "insurance_expiry": row.get("insurance_expiry") or "",
        "roadworthy_expiry": row.get("roadworthy_expiry") or "",
        "raw": row,
    }


def _normalize_route(row: dict[str, Any]) -> dict[str, Any]:
    pickup = row.get("pickup") or row.get("from") or ""
    dropoff = row.get("dropoff") or row.get("to") or ""
    return {
        "pickup": pickup,
        "dropoff": dropoff,
        "base_price": row.get("base_price") or "",
        "extra_passenger_price": row.get("price_per_extra_passenger") or row.get("extra_passenger_price") or "",
        "vehicle_type": row.get("vehicle_type") or "",
        "route_category": row.get("route_type") or row.get("route_category") or "",
        "active": row.get("active", True),
        "route_label": f"{pickup} to {dropoff}".strip(),
        "raw": row,
    }


def _normalize_tour(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row.get("title") or "Tour",
        "slug": row.get("slug") or "",
        "price": row.get("price") or row.get("price_from") or "",
        "duration": row.get("duration") or "",
        "pickup_locations": row.get("pickup_locations") if isinstance(row.get("pickup_locations"), list) else [],
        "itinerary": row.get("itinerary") if isinstance(row.get("itinerary"), list) else [],
        "included_items": row.get("included") or row.get("includes") or [],
        "published": row.get("published", True),
        "summary": row.get("summary") or row.get("description") or "",
        "raw": row,
    }


def _normalize_support(row: dict[str, Any]) -> dict[str, Any]:
    category = row.get("category") or row.get("issue_type") or row.get("subject") or "Support"
    return {
        "reference": row.get("reference") or row.get("id") or "",
        "id": row.get("id"),
        "name": row.get("name") or row.get("full_name") or row.get("email") or "Support requester",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
        "category": category,
        "status": row.get("status") or "Open",
        "priority": row.get("priority") or ("High" if "emergency" in str(category).lower() else "Standard"),
        "assigned_to": row.get("assigned_to") or "",
        "message": row.get("message") or row.get("description") or "",
        "created_at": row.get("created_at"),
        "raw": row,
    }


def _normalize_payment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "reference": row.get("reference") or row.get("booking_reference") or row.get("invoice_no") or "",
        "customer": row.get("customer") or row.get("client") or row.get("email") or row.get("description") or "Payment row",
        "method": row.get("method") or row.get("payment_method") or "",
        "description": row.get("description") or row.get("service") or "",
        "amount": row.get("amount") or row.get("estimated_price") or "",
        "amount_value": _amount_number(row.get("amount") or row.get("estimated_price")),
        "status": row.get("status") or row.get("payment_status") or "Unknown",
        "proof": row.get("proof") or row.get("proof_of_payment") or (row.get("metadata") or {}).get("proof_of_payment") or "",
        "created_at": row.get("created_at") or row.get("date"),
        "raw": row,
    }


def _normalize_invoice(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "invoice_no": row.get("invoice_no") or row.get("invoice_number") or "",
        "client": row.get("client") or row.get("customer_name") or "",
        "service": row.get("service") or "",
        "amount": row.get("amount") or "",
        "date": row.get("date") or row.get("created_at") or "",
        "raw": row,
    }


def _normalize_pricing_quote(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "quote_number": row.get("quote_number") or "",
        "route": f"{row.get('pickup_text') or ''} to {row.get('dropoff_text') or ''}".strip(),
        "pickup_zone": row.get("pickup_zone") or "",
        "dropoff_zone": row.get("dropoff_zone") or "",
        "vehicle_type": row.get("vehicle_type") or "",
        "final_price": row.get("final_price"),
        "driver_payout": row.get("driver_payout"),
        "tarasi_commission": row.get("tarasi_commission"),
        "estimated_profit": row.get("estimated_profit"),
        "price_confidence": row.get("price_confidence") or "",
        "status": row.get("status") or "quoted",
        "created_at": row.get("created_at"),
        "raw": row,
    }


def _normalize_pricing_booking(row: dict[str, Any]) -> dict[str, Any]:
    payment = get_payment_by_booking_number(row.get("booking_number") or "")
    invoice = get_invoice_by_booking_number(row.get("booking_number") or "")
    return {
        "booking_number": row.get("booking_number") or "",
        "route": f"{row.get('pickup_text') or ''} to {row.get('dropoff_text') or ''}".strip(),
        "pickup_zone": row.get("pickup_zone") or "",
        "dropoff_zone": row.get("dropoff_zone") or "",
        "vehicle_type": row.get("vehicle_type") or "",
        "final_price": row.get("final_price"),
        "status": row.get("status") or "pending",
        "payment_status": row.get("payment_status") or "unpaid",
        "proof_url": row.get("proof_url") or (payment or {}).get("proof_url") or "",
        "invoice_number": row.get("invoice_number") or (invoice or {}).get("invoice_number") or "",
        "assigned_driver_name": row.get("assigned_driver_name") or "",
        "assigned_vehicle": row.get("assigned_vehicle") or "",
        "price_confidence": "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "raw": row,
    }


def _normalize_audit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row.get("timestamp") or row.get("created_at") or "",
        "user": row.get("user") or row.get("email") or "System",
        "action": row.get("action") or row.get("message") or "",
        "raw": row,
    }


def _metric(label: str, value: Any, available: bool, tone: str = "default") -> dict[str, Any]:
    return {"label": label, "value": value if available else "Unavailable", "available": available, "tone": tone}


def _admin_sections() -> list[dict[str, Any]]:
    return [
        {"label": "Dashboard", "endpoint": "admin.dashboard", "icon": "◉", "id": "dashboard"},
        {"label": "Operations", "endpoint": "admin.alerts", "icon": "🔔", "id": "alerts"},
        {"label": "Bookings", "endpoint": "admin.bookings", "icon": "▣", "id": "bookings"},
        {"label": "Live Trips", "href": f"{url_for('admin.bookings')}#live-trips", "icon": "⌖", "id": "live_trips"},
        {"label": "Drivers", "endpoint": "admin.drivers", "icon": "◎", "id": "drivers"},
        {"label": "Customers", "endpoint": "admin.customers", "icon": "◌", "id": "customers"},
        {"label": "Fleet", "endpoint": "admin.fleet", "icon": "◫", "id": "fleet"},
        {"label": "Pricing OS", "endpoint": "admin.pricing_dashboard", "icon": "¤", "id": "pricing"},
        {"label": "Routes", "endpoint": "admin.routes_catalog", "icon": "↔", "id": "routes"},
        {"label": "Tours", "endpoint": "admin.tours", "icon": "◇", "id": "tours"},
        {"label": "Support", "endpoint": "admin.support", "icon": "✦", "id": "support"},
        {"label": "Bot OS", "endpoint": "bot.admin_dashboard", "icon": "◈", "id": "bot"},
        {"label": "Payments", "endpoint": "admin.payments", "icon": "$", "id": "payments"},
        {"label": "Reports", "endpoint": "admin.reports", "icon": "◬", "id": "reports"},
        {"label": "Homepage", "endpoint": "admin.content", "icon": "☰", "id": "content"},
        {"label": "System", "endpoint": "admin.system_health", "icon": "▲", "id": "system_health"},
        {"label": "Audit Logs", "endpoint": "admin.audit_logs", "icon": "≡", "id": "audit_logs"},
    ]


def get_admin_shell(active_section: str) -> dict[str, Any]:
    db_status = get_db_status()
    sections = _admin_sections()
    for item in sections:
        item["target"] = item.get("href") or url_for(item["endpoint"])
        item["active"] = item["id"] == active_section
    return {
        "active_section": active_section,
        "sections": sections,
        "db_status": db_status,
        "real_data_ready": _real_backend_ready(),
        "mode": get_database_mode(),
    }


def _real_data_notice() -> str | None:
    if _real_backend_ready():
        return None
    if get_database_mode() == "json_dev_fallback":
        return "JSON fallback mode is active for local development. Admin workflows use local dev records instead of live Neon/Supabase data."
    return "Executive data is unavailable because Neon/Supabase is not connected in this environment. Admin pages are rendering empty operational states instead of fallback metrics."


def _bookings(limit: int = 100) -> list[dict[str, Any]]:
    rows = _safe_rows("bookings", limit=limit)
    return [_normalize_booking(row) for row in rows]


def _drivers(limit: int = 100) -> list[dict[str, Any]]:
    rows = _safe_rows("drivers", limit=limit)
    users = _safe_rows("tarasi_users", limit=max(limit * 2, 200))
    vehicles = _safe_rows("vehicles", limit=max(limit * 2, 200))
    users_by_user_id = {str(row.get("supabase_user_id") or ""): row for row in users if row.get("supabase_user_id")}
    users_by_email = {str(row.get("email") or "").strip().lower(): row for row in users if row.get("email")}
    vehicles_by_driver_id = {}
    for vehicle in vehicles:
        driver_id = str(vehicle.get("driver_id") or "").strip()
        if driver_id:
            vehicles_by_driver_id[driver_id] = vehicle

    enriched: list[dict[str, Any]] = []
    for row in rows:
        user = users_by_user_id.get(str(row.get("user_id") or "")) or users_by_email.get(str(row.get("email") or "").strip().lower())
        vehicle = vehicles_by_driver_id.get(str(row.get("id") or row.get("driver_id") or "").strip())
        merged = dict(row)
        if user:
            merged.setdefault("full_name", user.get("full_name"))
            merged.setdefault("email", user.get("email"))
            merged.setdefault("phone", user.get("phone"))
        if vehicle:
            merged.setdefault("vehicle_id", vehicle.get("id"))
            merged.setdefault("vehicle_name", vehicle.get("name"))
            merged.setdefault("assigned_vehicle", {"vehicle_id": vehicle.get("id"), "name": vehicle.get("name")})
        enriched.append(_normalize_driver(merged))
    return enriched


def _customers(limit: int = 100) -> list[dict[str, Any]]:
    return [_normalize_customer(row) for row in _safe_rows("profiles", limit=limit)]


def _fleet(limit: int = 100) -> list[dict[str, Any]]:
    vehicles = _safe_rows("vehicles", limit=limit)
    drivers = _safe_rows("drivers", limit=max(limit * 2, 200))
    users = _safe_rows("tarasi_users", limit=max(limit * 2, 200))
    driver_names = {}
    users_by_user_id = {str(row.get("supabase_user_id") or ""): row for row in users if row.get("supabase_user_id")}
    for driver in drivers:
        user = users_by_user_id.get(str(driver.get("user_id") or ""))
        driver_names[str(driver.get("id") or driver.get("driver_code") or "")] = (
            (user or {}).get("full_name") or driver.get("driver_code") or "Assigned driver"
        )
    normalized = []
    for row in vehicles:
        record = dict(row)
        driver_id = str(row.get("driver_id") or "").strip()
        if driver_id and not record.get("assigned_driver"):
            record["assigned_driver"] = driver_names.get(driver_id, "")
        normalized.append(_normalize_vehicle(record))
    return normalized


def _routes(limit: int = 50) -> list[dict[str, Any]]:
    return [_normalize_route(row) for row in _safe_rows("routes", limit=limit)]


def _tours(limit: int = 50) -> list[dict[str, Any]]:
    return [_normalize_tour(row) for row in _safe_rows("tours", limit=limit)]


def _support(limit: int = 100) -> list[dict[str, Any]]:
    return [_normalize_support(row) for row in _safe_rows("support_tickets", limit=limit)]


def _payments(limit: int = 100) -> list[dict[str, Any]]:
    return [_normalize_payment(row) for row in _safe_rows("payments", limit=limit)]


def _extra_table_rows(table: str, limit: int = 200) -> list[dict[str, Any]]:
    return _safe_rows(table, limit=limit)


def _homepage_content_sections() -> dict[str, dict[str, Any]]:
    rows = _safe_rows("homepage_content", limit=100)
    sections: dict[str, dict[str, Any]] = {}
    sorted_rows = sorted(
        rows,
        key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
        reverse=True,
    )
    for row in sorted_rows:
        section_name = str(row.get("section_name") or "").strip()
        if not section_name or section_name in sections:
            continue
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        sections[section_name] = content
    return sections


WINDHOEK_ZONE_SEEDS = [
    {"zone_name": "CBD", "suburb_area": "CBD / Town", "base_fare": 35, "price_per_km": 14, "airport_fee": 220, "minimum_fare": 95, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5703, "longitude": 17.0832, "map_radius_km": 3.0, "is_active": True},
    {"zone_name": "Katutura", "suburb_area": "Katutura", "base_fare": 40, "price_per_km": 14, "airport_fee": 230, "minimum_fare": 100, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5364, "longitude": 17.0603, "map_radius_km": 4.5, "is_active": True},
    {"zone_name": "Wanaheda", "suburb_area": "Wanaheda", "base_fare": 40, "price_per_km": 14, "airport_fee": 235, "minimum_fare": 100, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5438, "longitude": 17.0675, "map_radius_km": 3.8, "is_active": True},
    {"zone_name": "Khomasdal", "suburb_area": "Khomasdal", "base_fare": 38, "price_per_km": 14, "airport_fee": 225, "minimum_fare": 98, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5488, "longitude": 17.0403, "map_radius_km": 3.8, "is_active": True},
    {"zone_name": "Hochland Park", "suburb_area": "Hochland Park", "base_fare": 38, "price_per_km": 14, "airport_fee": 230, "minimum_fare": 98, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5887, "longitude": 17.0564, "map_radius_km": 3.5, "is_active": True},
    {"zone_name": "Pioneers Park", "suburb_area": "Pioneers Park", "base_fare": 38, "price_per_km": 14, "airport_fee": 230, "minimum_fare": 98, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.6034, "longitude": 17.0838, "map_radius_km": 3.4, "is_active": True},
    {"zone_name": "Eros", "suburb_area": "Eros", "base_fare": 36, "price_per_km": 14, "airport_fee": 225, "minimum_fare": 95, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5608, "longitude": 17.0977, "map_radius_km": 3.0, "is_active": True},
    {"zone_name": "Klein Windhoek", "suburb_area": "Klein Windhoek", "base_fare": 36, "price_per_km": 14, "airport_fee": 220, "minimum_fare": 95, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5638, "longitude": 17.0981, "map_radius_km": 3.1, "is_active": True},
    {"zone_name": "Olympia", "suburb_area": "Olympia", "base_fare": 37, "price_per_km": 14, "airport_fee": 225, "minimum_fare": 97, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5845, "longitude": 17.1043, "map_radius_km": 3.2, "is_active": True},
    {"zone_name": "Kleine Kuppe", "suburb_area": "Kleine Kuppe", "base_fare": 37, "price_per_km": 14, "airport_fee": 225, "minimum_fare": 97, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5974, "longitude": 17.1008, "map_radius_km": 3.0, "is_active": True},
    {"zone_name": "Goreangab", "suburb_area": "Goreangab", "base_fare": 42, "price_per_km": 14, "airport_fee": 235, "minimum_fare": 102, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5214, "longitude": 17.0282, "map_radius_km": 4.0, "is_active": True},
    {"zone_name": "Rocky Crest", "suburb_area": "Rocky Crest", "base_fare": 40, "price_per_km": 14, "airport_fee": 232, "minimum_fare": 100, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5701, "longitude": 17.0372, "map_radius_km": 3.8, "is_active": True},
    {"zone_name": "Otjomuise", "suburb_area": "Otjomuise", "base_fare": 41, "price_per_km": 14, "airport_fee": 233, "minimum_fare": 101, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5926, "longitude": 17.0294, "map_radius_km": 4.0, "is_active": True},
    {"zone_name": "Cimbebasia", "suburb_area": "Cimbebasia", "base_fare": 39, "price_per_km": 14, "airport_fee": 230, "minimum_fare": 99, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.6102, "longitude": 17.0507, "map_radius_km": 3.8, "is_active": True},
    {"zone_name": "Auasblick", "suburb_area": "Auasblick", "base_fare": 39, "price_per_km": 14, "airport_fee": 228, "minimum_fare": 99, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5945, "longitude": 17.1190, "map_radius_km": 3.0, "is_active": True},
    {"zone_name": "Prosperita", "suburb_area": "Prosperita", "base_fare": 38, "price_per_km": 14, "airport_fee": 228, "minimum_fare": 98, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.6208, "longitude": 17.0788, "map_radius_km": 3.3, "is_active": True},
    {"zone_name": "Windhoek West", "suburb_area": "Windhoek West", "base_fare": 37, "price_per_km": 14, "airport_fee": 225, "minimum_fare": 97, "night_fee": 50, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.5701, "longitude": 17.0588, "map_radius_km": 3.2, "is_active": True},
    {"zone_name": "Hosea Kutako Airport", "suburb_area": "Hosea Kutako Airport", "base_fare": 80, "price_per_km": 16, "airport_fee": 250, "minimum_fare": 250, "night_fee": 65, "luggage_fee": 20, "waiting_fee": 30, "latitude": -22.4799, "longitude": 17.4709, "map_radius_km": 6.0, "is_active": True},
    {"zone_name": "Eros Airport", "suburb_area": "Eros Airport", "base_fare": 45, "price_per_km": 14, "airport_fee": 90, "minimum_fare": 120, "night_fee": 55, "luggage_fee": 15, "waiting_fee": 25, "latitude": -22.6122, "longitude": 17.0804, "map_radius_km": 2.0, "is_active": True},
]


def ensure_windhoek_zones() -> dict[str, Any]:
    if not _real_backend_ready() or not resolve_table_name("pricing_zones"):
        return {"seeded": 0, "available": False}
    existing = _safe_rows("pricing_zones", limit=5)
    if existing:
        return {"seeded": 0, "available": True}
    seeded = 0
    for row in WINDHOEK_ZONE_SEEDS:
        created = insert_row("pricing_zones", {**row, "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()})
        if created:
            seeded += 1
    return {"seeded": seeded, "available": True}


def _today_and_month_counts(bookings: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    if not _real_backend_ready():
        return None, None
    now = datetime.now()
    today_count = 0
    month_count = 0
    for booking in bookings:
        booking_dt = _dt(booking.get("created_at")) or _dt(booking.get("date"))
        if not booking_dt:
            continue
        if booking_dt.date() == now.date():
            today_count += 1
        if booking_dt.year == now.year and booking_dt.month == now.month:
            month_count += 1
    return today_count, month_count


def log_admin_action(action: str, table_name: str = None, record_id: str = None, old_value: Any = None, new_value: Any = None):
    """
    Records an admin action into the audit_logs table.
    """
    from flask import session, request
    user = session.get("user") or {}
    admin_email = user.get("email")
    admin_user_id = user.get("user_id")
    
    payload = {
        "admin_user_id": admin_user_id,
        "admin_email": admin_email,
        "action": action,
        "table_name": table_name,
        "record_id": str(record_id) if record_id else None,
        "old_value": old_value,
        "new_value": new_value,
        "ip_address": request.remote_addr if request else None,
        "user_agent": request.user_agent.string if request else None,
        "created_at": datetime.now().isoformat()
    }
    
    insert_row("audit_logs", payload)


def get_dashboard_summary() -> dict[str, Any]:
    """Lightweight summary for API or fast initial load."""
    cached = _get_cached_metrics()
    if cached:
        return cached

    available = _real_backend_ready()
    if not available:
        return {"available": False, "metrics": []}

    total_bookings = count_rows("bookings")
    active_rides = count_rows("bookings", filters={"status": "driver_assigned"}) + \
                   count_rows("bookings", filters={"status": "on_the_way"}) + \
                   count_rows("bookings", filters={"status": "arrived"}) + \
                   count_rows("bookings", filters={"status": "picked_up"})
    
    total_customers = count_rows("profiles")
    total_drivers = count_rows("drivers")
    open_tickets = count_rows("support_tickets", filters={"status": "open"})
    total_payments = count_rows("payments")
    available_vehicles = count_rows("fleet", filters={"status": "available"})

    metrics = [
        _metric("Total bookings", total_bookings, available, "gold"),
        _metric("Active rides", active_rides, available, "teal"),
        _metric("Customers", total_customers, available),
        _metric("Drivers", total_drivers, available),
        _metric("Open tickets", open_tickets, available, "rose" if open_tickets > 5 else "default"),
        _metric("Available vehicles", available_vehicles, available),
        _metric("Total payments", total_payments, available),
    ]
    
    data = {
        "metrics": metrics,
        "available": available,
        "timestamp": datetime.now().isoformat()
    }
    _set_cached_metrics(data)
    return data


def get_dashboard_context() -> dict[str, Any]:
    summary = get_dashboard_summary()
    
    # Fetch recent items for the tables
    bookings = _bookings(limit=8)
    support_rows = _support(limit=6)
    payments = _payments(limit=6)
    audit_logs = _extra_table_rows("audit_logs", limit=10)

    available = summary["available"]

    return {
        "metrics": summary["metrics"],
        "bookings": bookings,
        "live_trips": [item for item in bookings if item["status_key"] in STATUS_GROUPS["active"]],
        "support_rows": support_rows,
        "payments": payments,
        "drivers_online": sum(
            1
            for item in _drivers(limit=200)
            if str(item.get("status") or item.get("availability") or "").strip().lower() in {"online", "available", "active"}
        ),
        "audit_logs": [_normalize_audit(row) for row in audit_logs],
        "notice": _real_data_notice(),
        "available": available,
        "system_status": "REAL DATABASE CONNECTED" if available else "FALLBACK MODE",
    }


def get_bookings_context(status_filter: str = "all") -> dict[str, Any]:
    bookings = _bookings()
    if status_filter == "active":
        filtered = [item for item in bookings if item["status_key"] in STATUS_GROUPS["active"]]
    elif status_filter in STATUS_GROUPS:
        filtered = [item for item in bookings if item["status_key"] in STATUS_GROUPS[status_filter]]
    else:
        filtered = bookings

    by_type = {
        "school": [item for item in bookings if item.get("booking_type") == "school"][:8],
        "monthly": [item for item in bookings if item.get("booking_type") == "monthly"][:8],
        "airport": [item for item in bookings if item.get("booking_type") == "airport"][:8],
        "vip": [item for item in bookings if item.get("booking_type") == "vip"][:8],
        "business": [item for item in bookings if item.get("booking_type") == "business"][:8],
    }
    return {
        "bookings": filtered,
        "status_filter": status_filter,
        "statuses": ["Booking received", "Confirmed", "Driver assigned", "On the way", "Arrived", "Picked up", "Completed", "Cancellation requested", "Cancelled"],
        "drivers": _drivers(),
        "live_trips": [item for item in bookings if item["status_key"] in STATUS_GROUPS["active"]],
        "by_type": by_type,
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_booking_detail_context(reference: str) -> dict[str, Any]:
    booking = next((item for item in _bookings() if item["reference"] == reference), None)
    return {
        "booking": booking,
        "drivers": _drivers(),
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_drivers_context() -> dict[str, Any]:
    drivers = _drivers()
    fleet = _fleet()
    bookings = _bookings()
    documents = _extra_table_rows("driver_documents")
    
    # Attach documents to drivers
    docs_by_driver = {}
    for doc in documents:
        did = str(doc.get("driver_id"))
        if did not in docs_by_driver:
            docs_by_driver[did] = []
        docs_by_driver[did].append(doc)
    
    for driver in drivers:
        did = str(driver.get("driver_id") or driver.get("id"))
        driver["documents"] = docs_by_driver.get(did, [])

    active_by_driver = Counter(item.get("driver_id") or item.get("driver_name") for item in bookings if item["status_key"] in STATUS_GROUPS["active"])
    return {
        "drivers": drivers,
        "fleet": fleet,
        "driver_metrics": {
            "approved": sum(1 for item in drivers if item.get("admin_approved") or item.get("verified")),
            "suspended": sum(1 for item in drivers if "suspend" in str(item.get("verification_status", "")).lower()),
            "active_trips": sum(active_by_driver.values()),
        } if _real_backend_ready() else {},
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_customers_context() -> dict[str, Any]:
    customers = _customers()
    bookings = _bookings()
    support_rows = _support()
    bookings_by_email = Counter(item.get("email") for item in bookings if item.get("email"))
    tickets_by_email = Counter(item.get("email") for item in support_rows if item.get("email"))
    enriched = []
    for customer in customers:
        email = customer.get("email")
        customer["booking_count"] = bookings_by_email.get(email, 0)
        customer["ticket_count"] = tickets_by_email.get(email, 0)
        enriched.append(customer)
    return {
        "customers": enriched,
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_fleet_context() -> dict[str, Any]:
    return {
        "fleet": _fleet(),
        "fleet_groups": _extra_table_rows("fleet_groups"),
        "drivers": _drivers(limit=200),
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_routes_context() -> dict[str, Any]:
    return {"routes": _routes(), "notice": _real_data_notice(), "available": _real_backend_ready()}


def get_tours_context() -> dict[str, Any]:
    return {"tours": _tours(), "notice": _real_data_notice(), "available": _real_backend_ready()}


def get_support_context() -> dict[str, Any]:
    tickets = _support()
    return {
        "tickets": tickets,
        "complaints": [item for item in tickets if "complaint" in item["category"].lower()],
        "lost_items": [item for item in tickets if "lost" in item["category"].lower()],
        "emergency": [item for item in tickets if "emergency" in item["category"].lower()],
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_payments_context() -> dict[str, Any]:
    payments = _payments()
    
    # If no payments records, use bookings with payment info
    if not payments:
        bookings = _bookings()
        payments = [_normalize_payment(b) for b in bookings if b.get("payment_status") != "Unpaid" or b.get("amount")]

    refunds = [_normalize_payment(row) for row in _extra_table_rows("refunds")]
    wallets = _extra_table_rows("wallets") or _extra_table_rows("wallet_transactions")
    coupons = _extra_table_rows("coupons") or _extra_table_rows("campaigns")
    invoices = [_normalize_invoice(row) for row in _extra_table_rows("invoices")]
    return {
        "payments": payments,
        "refunds": refunds,
        "wallets": wallets,
        "coupons": coupons,
        "invoices": invoices,
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_reports_context() -> dict[str, Any]:
    bookings = _bookings()
    drivers = _drivers()
    support_rows = _support()
    available = _real_backend_ready()
    route_counts = Counter(f"{item.get('pickup')} to {item.get('dropoff')}" for item in bookings if item.get("pickup") and item.get("dropoff"))
    booking_type_counts = Counter(item.get("booking_type") for item in bookings if item.get("booking_type"))
    driver_trip_counts = Counter(item.get("driver_name") or item.get("driver_id") for item in bookings if item.get("driver_name") or item.get("driver_id"))
    daily_counts = Counter((_dt(item.get("created_at")) or _dt(item.get("date")) or datetime.min).date().isoformat() for item in bookings if _dt(item.get("created_at")) or _dt(item.get("date")))
    return {
        "daily_bookings": sorted(daily_counts.items(), reverse=True)[:7],
        "revenue_estimate": _money(sum(item["amount_value"] for item in bookings if item["amount_value"] is not None)) if available else "Unavailable",
        "top_routes": route_counts.most_common(6),
        "booking_type_breakdown": booking_type_counts.most_common(),
        "driver_performance": [{"driver": name, "trips": count} for name, count in driver_trip_counts.most_common(6)],
        "customer_growth": len(_customers()) if available else None,
        "support_volume": len(support_rows) if available else None,
        "notice": _real_data_notice(),
        "available": available,
        "drivers": drivers,
    }


def get_system_health_context() -> dict[str, Any]:
    db_status = get_db_status()
    schema_status = get_schema_status()
    supabase_health = get_supabase_health()
    expected = ["bookings", "profiles", "drivers", "fleet", "routes", "tours", "support_tickets", "payments", "audit_logs", "invoices"]
    table_presence = [
        {"table": name, "resolved": resolve_table_name(name) if _real_backend_ready() else None}
        for name in expected
    ]
    return {
        "db_status": db_status,
        "schema_status": schema_status,
        "supabase_health": supabase_health,
        "table_presence": table_presence,
        "last_checked": datetime.now().isoformat(timespec="seconds"),
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_content_context() -> dict[str, Any]:
    sections = _homepage_content_sections()
    return {
        "content_sections": sections,
        "hero_section": sections.get("hero_section", {}),
        "promotions": sections.get("promotions", {}),
        "routes": _routes()[:8],
        "fleet": _fleet()[:8],
        "tours": _tours()[:8],
        "notifications": _extra_table_rows("notifications"),
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_audit_context() -> dict[str, Any]:
    audit_logs = [_normalize_audit(row) for row in _extra_table_rows("audit_logs")]
    admin_users = _extra_table_rows("admin_users")
    return {
        "audit_logs": audit_logs,
        "admin_users": admin_users,
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def get_pricing_context() -> dict[str, Any]:
    zone_seed_status = ensure_windhoek_zones()
    raw_quotes = list_quotes(limit=100)
    raw_bookings = list_pricing_bookings(limit=100)
    quote_rows = [_normalize_pricing_quote(row) for row in raw_quotes]
    quote_confidence_by_id = {str(row.get("id")): row.get("price_confidence", "") for row in raw_quotes}
    booking_rows = []
    for row in raw_bookings:
        booking = _normalize_pricing_booking(row)
        booking["price_confidence"] = quote_confidence_by_id.get(str(row.get("quote_id")), "")
        booking_rows.append(booking)
    
    zones = _extra_table_rows("pricing_zones")
    rules = _extra_table_rows("pricing_rules")
    
    total_quotes = len(quote_rows)
    total_bookings = len(booking_rows)
    total_profit = sum(float(row.get("estimated_profit") or 0) for row in quote_rows)
    avg_confidence = ", ".join(sorted({row.get("price_confidence") for row in quote_rows if row.get("price_confidence")})) or "n/a"
    rule_lookup = {
        str(row.get("rule_name") or row.get("name") or row.get("rule_type") or row.get("id") or ""): row
        for row in rules
    }
    return {
        "quotes": quote_rows[:20],
        "pricing_bookings": booking_rows[:20],
        "pricing_zones": zones,
        "pricing_rules": rules,
        "pricing_rule_lookup": rule_lookup,
        "pricing_metrics": {
            "total_quotes": total_quotes,
            "total_bookings": total_bookings,
            "estimated_profit": _money(total_profit) if quote_rows else "N$0.00",
            "confidence_mix": avg_confidence,
        },
        "zone_seeded": zone_seed_status.get("seeded", 0),
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }


def assign_booking_driver(reference: str, driver_identifier: str) -> bool:
    ok = bool(assign_driver_to_booking(reference, driver_identifier))
    if ok:
        from services.booking_service import get_booking
        from services.notification_service import trigger_booking_event
        booking = get_booking(reference)
        if booking:
            trigger_booking_event("driver_assigned", booking)
    return ok


def add_booking_note(reference: str, note: str) -> bool:
    if not _real_backend_ready() or not note.strip():
        return False
    booking = next((item for item in _bookings() if item["reference"] == reference), None)
    if not booking:
        return False
    metadata = dict(booking["raw"].get("metadata") or {})
    metadata["admin_note"] = note.strip()
    metadata["admin_note_updated_at"] = datetime.now().isoformat(timespec="seconds")
    updated = update_row("bookings", "reference", reference, {"metadata": metadata})
    return bool(updated)


def update_driver_action(driver_id: str, action: str, payload: dict[str, Any] | None = None) -> bool:
    payload = payload or {}
    if action == "create":
        driver_payload = {
            "driver_id": payload.get("driver_id") or payload.get("new_driver_id") or payload.get("id") or f"DRV-{datetime.now().strftime('%H%M%S')}",
            "id": payload.get("driver_id") or payload.get("new_driver_id") or payload.get("id") or f"DRV-{datetime.now().strftime('%H%M%S')}",
            "full_name": payload.get("full_name", ""),
            "email": payload.get("email", ""),
            "phone": payload.get("phone", ""),
            "status": payload.get("status", "Offline"),
            "vehicle_id": payload.get("vehicle_id", ""),
            "vehicle_name": payload.get("vehicle_name") or "",
            "current_lat": payload.get("current_lat"),
            "current_lng": payload.get("current_lng"),
            "last_location_at": payload.get("last_location_at", ""),
            "rating": payload.get("rating", "New"),
            "verified": bool(payload.get("verified") or payload.get("admin_approved")),
            "documents_status": payload.get("documents_status") or payload.get("verification_status") or "Created by admin",
            "verification_status": payload.get("documents_status") or payload.get("verification_status") or "Created by admin",
            "admin_approved": bool(payload.get("admin_approved")),
            "assigned_vehicle": payload.get("assigned_vehicle", {}),
            "based_area": payload.get("based_area", ""),
            "service_type": payload.get("service_type", ""),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        created = insert_row("drivers", driver_payload)
        return bool(created)
    if not _real_backend_ready() and get_database_mode() != "json_dev_fallback":
        return False
    if action == "approve":
        updated = update_row("drivers", "driver_id", driver_id, {"admin_approved": True, "verified": True, "verification_status": "Approved", "documents_status": "Approved"})
        return bool(updated)
    if action == "suspend":
        updated = update_row("drivers", "driver_id", driver_id, {"admin_approved": False, "verified": False, "verification_status": "Suspended", "documents_status": "Suspended"})
        return bool(updated)
    if action == "assign_vehicle":
        assigned_vehicle = payload.get("assigned_vehicle", {})
        updated = update_row("drivers", "driver_id", driver_id, {"assigned_vehicle": assigned_vehicle, "vehicle_name": assigned_vehicle.get("name", "")})
        return bool(updated)
    return False


def update_customer_block(email: str, blocked: bool) -> bool:
    if not _real_backend_ready() or not email:
        return False
    updated = update_row("profiles", "email", email, {"blocked": blocked})
    return bool(updated)


def update_support_ticket(reference: str, payload: dict[str, Any]) -> bool:
    if not _real_backend_ready() or not reference:
        return False
    rows = fetch_rows("support_tickets", filters={"id": reference}, limit=1)
    match_field = "id" if rows else "reference"
    updated = update_row("support_tickets", match_field, reference, payload)
    return bool(updated)

def get_alerts_context() -> dict[str, Any]:
    from services.notification_service import list_admin_alerts
    alerts = list_admin_alerts()
    return {
        "alerts": alerts,
        "notice": _real_data_notice(),
        "available": _real_backend_ready(),
    }
