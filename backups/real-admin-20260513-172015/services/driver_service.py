from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from .booking_service import get_booking, list_bookings, update_booking_metadata, update_booking_status
from .db_service import fetch_rows, get_database_mode, insert_row, update_row
from .storage_service import load_json, save_json

DRIVERS_FILE = "drivers_profiles.json"
ADMIN_DRIVER_FILE = "admin_driver_accounts.json"
ACTIVE_DRIVER_STATUSES = {"driver_assigned", "on_the_way", "arrived", "picked_up"}
DRIVER_WORKFLOW_STATUSES = {
    "accepted": "Driver assigned",
    "on_the_way": "On the way",
    "arrived": "Arrived",
    "picked_up": "Picked up",
    "completed": "Completed",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _status_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _rating_value(value: Any) -> str:
    if value in (None, ""):
        return "New"
    return str(value)


def normalize_driver(row: dict[str, Any]) -> dict[str, Any]:
    assigned_vehicle = row.get("assigned_vehicle") if isinstance(row.get("assigned_vehicle"), dict) else {}
    driver_id = row.get("driver_id") or row.get("id") or f"DRV-{secrets.token_hex(3).upper()}"
    vehicle_name = row.get("vehicle_name") or assigned_vehicle.get("name") or ""
    status = row.get("status") or row.get("availability") or "Offline"
    verified = row.get("verified")
    if verified is None:
        verified = bool(row.get("admin_approved"))
    documents_status = row.get("documents_status") or row.get("verification_status") or "Pending review"
    return {
        "id": driver_id,
        "driver_id": driver_id,
        "full_name": row.get("full_name") or row.get("name") or row.get("email") or "Tarasi Driver",
        "phone": row.get("phone") or "",
        "email": row.get("email") or "",
        "status": status,
        "availability": status,
        "vehicle_id": row.get("vehicle_id") or assigned_vehicle.get("vehicle_id") or "",
        "vehicle_name": vehicle_name,
        "assigned_vehicle": assigned_vehicle or ({"name": vehicle_name} if vehicle_name else {}),
        "current_lat": _coerce_float(row.get("current_lat")),
        "current_lng": _coerce_float(row.get("current_lng")),
        "last_location_at": row.get("last_location_at") or "",
        "rating": _rating_value(row.get("rating")),
        "verified": bool(verified),
        "documents_status": documents_status,
        "verification_status": documents_status,
        "admin_approved": bool(row.get("admin_approved", verified)),
        "based_area": row.get("based_area") or row.get("base_area") or "",
        "service_type": row.get("service_type") or "",
        "total_trips": int(row.get("total_trips") or 0),
        "completed_trips": int(row.get("completed_trips") or 0),
        "cancelled_trips": int(row.get("cancelled_trips") or 0),
        "balance": row.get("balance") or "N$0.00",
        "documents": row.get("documents") if isinstance(row.get("documents"), list) else [],
        "raw": row,
    }


def _driver_rows() -> list[dict[str, Any]]:
    mode = get_database_mode()
    if mode in {"neon", "supabase"}:
        rows = fetch_rows("drivers", limit=300)
        if rows:
            return rows
    rows = load_json(DRIVERS_FILE, [])
    rows = rows if isinstance(rows, list) else []
    admin_rows = load_json(ADMIN_DRIVER_FILE, [])
    if isinstance(admin_rows, list):
        seen = {str(normalize_driver(row).get("email", "")).strip().lower() for row in rows}
        for row in admin_rows:
            email = str(row.get("email", "")).strip().lower()
            if not email or email in seen or row.get("role") != "driver":
                continue
            rows.append(
                {
                    "driver_id": row.get("driver_id"),
                    "id": row.get("driver_id"),
                    "email": row.get("email"),
                    "full_name": row.get("full_name", "Tarasi Driver"),
                    "phone": row.get("phone", ""),
                    "status": "Offline",
                    "vehicle_name": ((row.get("assigned_vehicle") or {}) if isinstance(row.get("assigned_vehicle"), dict) else {}).get("name", ""),
                    "assigned_vehicle": row.get("assigned_vehicle") if isinstance(row.get("assigned_vehicle"), dict) else {},
                    "verified": bool(row.get("admin_approved")),
                    "documents_status": row.get("verification_status") or "Created by admin",
                    "verification_status": row.get("verification_status") or "Created by admin",
                    "admin_approved": bool(row.get("admin_approved")),
                    "based_area": row.get("based_area", ""),
                    "service_type": row.get("service_type", ""),
                }
            )
            seen.add(email)
    return rows


def list_drivers() -> list[dict[str, Any]]:
    return [normalize_driver(row) for row in _driver_rows()]


def get_driver(driver_identifier: str) -> dict[str, Any] | None:
    if not driver_identifier:
        return None
    probe = str(driver_identifier).strip().lower()
    for driver in list_drivers():
        if probe in {
            str(driver.get("driver_id", "")).strip().lower(),
            str(driver.get("id", "")).strip().lower(),
            str(driver.get("email", "")).strip().lower(),
        }:
            return driver
    return None


def current_driver_from_session(session: dict[str, Any]) -> dict[str, Any] | None:
    email = str(session.get("driver_email") or "").strip().lower()
    if not email:
        return None
    return get_driver(email)


def _write_driver_record(driver_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    mode = get_database_mode()
    if mode in {"neon", "supabase"}:
        updated = update_row("drivers", "driver_id", driver_id, payload)
        if updated:
            return normalize_driver(updated)
        existing = get_driver(driver_id)
        if existing:
            updated = update_row("drivers", "id", existing["id"], payload)
            if updated:
                return normalize_driver(updated)

    rows = _driver_rows()
    for index, row in enumerate(rows):
        normalized = normalize_driver(row)
        if normalized["driver_id"] == driver_id:
            updated = {**row, **payload}
            rows[index] = updated
            save_json(DRIVERS_FILE, rows)
            return normalize_driver(updated)
    return None


def assign_driver_to_booking(reference: str, driver_identifier: str) -> dict[str, Any] | None:
    driver = get_driver(driver_identifier)
    booking = get_booking(reference)
    if not driver or not booking:
        return None

    booking_pin = booking.get("booking_pin") or "".join(secrets.choice("0123456789") for _ in range(4))
    metadata = {
        "driver_id": driver.get("driver_id"),
        "driver_name": driver.get("full_name"),
        "driver_phone": driver.get("phone"),
        "driver_email": driver.get("email"),
        "vehicle_name": driver.get("vehicle_name"),
        "booking_pin": booking_pin,
        "driver_assigned_at": _now(),
    }
    updated = update_booking_metadata(reference, metadata, status="Driver assigned")
    _write_driver_record(
        driver["driver_id"],
        {
            "status": "Assigned",
            "availability": "Assigned",
            "vehicle_name": driver.get("vehicle_name"),
            "vehicle_id": driver.get("vehicle_id"),
        },
    )
    return updated


def list_driver_trips(driver: dict[str, Any]) -> list[dict[str, Any]]:
    if not driver:
        return []
    driver_id = str(driver.get("driver_id") or "").strip().lower()
    driver_email = str(driver.get("email") or "").strip().lower()
    driver_name = str(driver.get("full_name") or "").strip().lower()

    trips = []
    for booking in list_bookings():
        metadata = booking.get("metadata") if isinstance(booking.get("metadata"), dict) else {}
        booking_driver_values = {
            str(booking.get("driver_id") or "").strip().lower(),
            str(metadata.get("driver_id") or "").strip().lower(),
            str(metadata.get("driver_email") or "").strip().lower(),
            str(booking.get("driver_name") or "").strip().lower(),
            str(metadata.get("driver_name") or "").strip().lower(),
        }
        if driver_id in booking_driver_values or driver_email in booking_driver_values or driver_name in booking_driver_values:
            trips.append(booking)
    return trips


def get_driver_trip(driver: dict[str, Any], reference: str) -> dict[str, Any] | None:
    return next((trip for trip in list_driver_trips(driver) if trip.get("reference") == reference), None)


def update_driver_trip_status(reference: str, driver: dict[str, Any], action: str) -> dict[str, Any] | None:
    booking = get_driver_trip(driver, reference)
    if not booking:
        return None
    action_key = _status_key(action)
    target_status = DRIVER_WORKFLOW_STATUSES.get(action_key)
    if not target_status:
        return None

    metadata_updates = {
        "driver_id": driver.get("driver_id"),
        "driver_name": driver.get("full_name"),
        "driver_phone": driver.get("phone"),
        "driver_email": driver.get("email"),
        "vehicle_name": driver.get("vehicle_name"),
        f"driver_{action_key}_at": _now(),
    }
    update_booking_metadata(reference, metadata_updates, status=target_status)
    updated = update_booking_status(reference, target_status)

    driver_payload = {
        "status": "Available" if action_key == "completed" else ("On trip" if action_key in {"on_the_way", "arrived", "picked_up"} else "Assigned"),
        "availability": "Available" if action_key == "completed" else ("On trip" if action_key in {"on_the_way", "arrived", "picked_up"} else "Assigned"),
        "total_trips": max(int(driver.get("total_trips") or 0), 0) + (1 if action_key == "accepted" else 0),
        "completed_trips": max(int(driver.get("completed_trips") or 0), 0) + (1 if action_key == "completed" else 0),
    }
    _write_driver_record(driver["driver_id"], driver_payload)
    return updated


def update_driver_location(driver: dict[str, Any], lat: Any, lng: Any) -> tuple[bool, dict[str, Any] | str]:
    lat_value = _coerce_float(lat)
    lng_value = _coerce_float(lng)
    if lat_value is None or lng_value is None:
        return False, "Latitude and longitude are required."
    if not (-90 <= lat_value <= 90 and -180 <= lng_value <= 180):
        return False, "Coordinates are out of range."

    timestamp = _now()
    updated_driver = _write_driver_record(
        driver["driver_id"],
        {
            "current_lat": lat_value,
            "current_lng": lng_value,
            "last_location_at": timestamp,
        },
    )
    if not updated_driver:
        return False, "Driver record could not be updated."

    for trip in list_driver_trips(driver):
        if _status_key(trip.get("status")) not in ACTIVE_DRIVER_STATUSES:
            continue
        update_booking_metadata(
            trip["reference"],
            {
                "driver_lat": lat_value,
                "driver_lng": lng_value,
                "last_location_at": timestamp,
                "driver_name": driver.get("full_name"),
                "driver_phone": driver.get("phone"),
                "vehicle_name": driver.get("vehicle_name"),
            },
        )

    return True, {
        "driver_id": updated_driver["driver_id"],
        "lat": lat_value,
        "lng": lng_value,
        "last_location_at": timestamp,
    }
