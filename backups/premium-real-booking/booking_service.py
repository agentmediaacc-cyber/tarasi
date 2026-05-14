from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from .db_service import get_neon_connection, resolve_table_name
from .storage_service import load_json, save_json


BOOKINGS_FILE = "bookings.json"
BOOKING_STATUSES = [
    "Booking received",
    "Confirmed",
    "Driver assigned",
    "Arrived",
    "On the way",
    "Picked up",
    "Completed",
    "Cancellation requested",
    "Cancelled",
]

PAYMENT_STATUSES = [
    "Unpaid",
    "Pending",
    "Paid",
    "Failed",
    "Refunded",
    "Partially refunded",
]

BOOKING_TYPE_META = {
    "once-off": {"title": "Once-off ride", "tagline": "Fast one-way shuttle or private ride", "icon": "01", "route_type": "One-way", "cta": "Book once-off ride"},
    "return": {"title": "Return trip", "tagline": "Departure and return in one booking", "icon": "02", "route_type": "Round trip", "cta": "Book return trip"},
    "monthly": {"title": "Monthly transport", "tagline": "Reliable recurring plans for families and teams", "icon": "03", "route_type": "Subscription", "cta": "Start monthly plan"},
    "school": {"title": "School kids transport", "tagline": "Safe school pickups with guardian controls", "icon": "04", "route_type": "School", "cta": "Book school transport"},
    "airport": {"title": "Airport transfer", "tagline": "Arrival and departure transfers across Namibia", "icon": "05", "route_type": "Airport", "cta": "Book airport transfer"},
    "tourist": {"title": "Tourist package", "tagline": "Desert, coast and safari transfers with add-ons", "icon": "06", "route_type": "Tourism", "cta": "Book tourist package"},
    "vip": {"title": "VIP/private hire", "tagline": "Executive privacy, premium fleet, full-day options", "icon": "07", "route_type": "Executive", "cta": "Book VIP transport"},
    "business": {"title": "Business/staff transport", "tagline": "Staff shuttles, airport pickups and billing support", "icon": "08", "route_type": "Corporate", "cta": "Book business transport"},
    "event": {"title": "Event/wedding transport", "tagline": "Guest movement, return trips and pickup clusters", "icon": "09", "route_type": "Events", "cta": "Book event transport"},
    "long-distance": {"title": "Long-distance shuttle", "tagline": "Intercity Namibia routes with stopovers", "icon": "10", "route_type": "Long distance", "cta": "Book long-distance shuttle"},
}

COMMON_BOOKING_FIELDS = [
    {"name": "full_name", "label": "Full name", "type": "text", "required": True},
    {"name": "phone", "label": "Phone", "type": "text", "required": True},
    {"name": "email", "label": "Email", "type": "email", "required": False},
    {"name": "pickup_location", "label": "Pickup location", "type": "text", "required": True},
    {"name": "dropoff_location", "label": "Drop-off location", "type": "text", "required": True},
    {"name": "date", "label": "Date", "type": "date", "required": True},
    {"name": "time", "label": "Time", "type": "time", "required": True},
    {"name": "passengers", "label": "Passengers", "type": "number", "required": True, "min": 1},
    {"name": "luggage", "label": "Luggage", "type": "text", "required": False},
    {"name": "preferred_vehicle", "label": "Preferred vehicle", "type": "select", "required": False, "options": []},
    {"name": "notes", "label": "Notes", "type": "textarea", "required": False},
]

BOOKING_TYPE_FIELDS = {
    "once-off": [],
    "return": [
        {"name": "departure_date", "label": "Departure date", "type": "date", "required": True},
        {"name": "departure_time", "label": "Departure time", "type": "time", "required": True},
        {"name": "return_date", "label": "Return date", "type": "date", "required": True},
        {"name": "return_time", "label": "Return time", "type": "time", "required": True},
    ],
    "monthly": [
        {"name": "start_date", "label": "Start date", "type": "date", "required": True},
        {"name": "end_date", "label": "End date", "type": "date", "required": True},
        {"name": "weekdays", "label": "Weekdays selection", "type": "text", "required": True, "placeholder": "Mon, Tue, Wed, Thu, Fri"},
        {"name": "morning_pickup_time", "label": "Morning pickup time", "type": "time", "required": True},
        {"name": "afternoon_return_time", "label": "Afternoon return time", "type": "time", "required": True},
        {"name": "number_of_passengers", "label": "Number of passengers", "type": "number", "required": True, "min": 1},
        {"name": "company_or_family_name", "label": "Company or family name", "type": "text", "required": True},
    ],
    "school": [
        {"name": "parent_guardian_name", "label": "Parent or guardian name", "type": "text", "required": True},
        {"name": "child_full_name", "label": "Child full name", "type": "text", "required": True},
        {"name": "child_grade", "label": "Child grade", "type": "text", "required": True},
        {"name": "school_name", "label": "School name", "type": "text", "required": True},
        {"name": "morning_pickup", "label": "Morning pickup", "type": "text", "required": True},
        {"name": "afternoon_dropoff", "label": "Afternoon drop-off", "type": "text", "required": True},
        {"name": "emergency_contact", "label": "Emergency contact", "type": "text", "required": True},
        {"name": "weekdays", "label": "Weekdays", "type": "text", "required": True},
        {"name": "monthly_payment_option", "label": "Monthly payment option", "type": "select", "required": True, "options": ["Bank transfer", "Wallet", "Invoice"]},
        {"name": "safety_notes", "label": "Safety notes", "type": "textarea", "required": False},
    ],
    "airport": [
        {"name": "flight_number", "label": "Flight number", "type": "text", "required": True},
        {"name": "arrival_or_departure", "label": "Arrival or departure", "type": "select", "required": True, "options": ["Arrival", "Departure"]},
        {"name": "airline", "label": "Airline", "type": "text", "required": True},
        {"name": "meet_and_greet", "label": "Meet-and-greet option", "type": "select", "required": True, "options": ["Yes", "No"]},
        {"name": "extra_luggage", "label": "Extra luggage", "type": "text", "required": False},
    ],
    "tourist": [
        {"name": "destination", "label": "Destination", "type": "text", "required": True},
        {"name": "hotel_or_lodge_pickup", "label": "Hotel or lodge pickup", "type": "text", "required": True},
        {"name": "tour_duration", "label": "Tour duration", "type": "text", "required": True},
        {"name": "need_tour_guide", "label": "Need tour guide", "type": "select", "required": True, "options": ["Yes", "No"]},
        {"name": "need_activity_package", "label": "Need activity package", "type": "select", "required": True, "options": ["Yes", "No"]},
        {"name": "special_requests", "label": "Special requests", "type": "textarea", "required": False},
    ],
    "vip": [
        {"name": "executive_vehicle", "label": "Executive vehicle", "type": "text", "required": True},
        {"name": "privacy_request", "label": "Privacy request", "type": "textarea", "required": False},
        {"name": "security_request", "label": "Security request", "type": "textarea", "required": False},
        {"name": "hire_option", "label": "Hourly or full-day option", "type": "select", "required": True, "options": ["Hourly", "Full day"]},
    ],
    "business": [
        {"name": "company_name", "label": "Company name", "type": "text", "required": True},
        {"name": "employee_count", "label": "Employee count", "type": "number", "required": True, "min": 1},
        {"name": "recurring_schedule", "label": "Recurring schedule", "type": "text", "required": True},
        {"name": "billing_contact", "label": "Billing contact", "type": "text", "required": True},
    ],
    "event": [
        {"name": "event_type", "label": "Event type", "type": "text", "required": True},
        {"name": "venue", "label": "Venue", "type": "text", "required": True},
        {"name": "multiple_pickup_points", "label": "Multiple pickup points", "type": "textarea", "required": False},
        {"name": "return_after_event", "label": "Return after event", "type": "select", "required": True, "options": ["Yes", "No"]},
    ],
    "long-distance": [
        {"name": "route_or_town", "label": "Route or town", "type": "text", "required": True},
        {"name": "stopover_requests", "label": "Stopover requests", "type": "textarea", "required": False},
        {"name": "group_booking", "label": "Group booking", "type": "select", "required": True, "options": ["Yes", "No"]},
    ],
}


def normalize_booking(booking: dict[str, Any], index: int | None = None) -> dict[str, Any]:
    normalized = dict(booking)
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else normalized.get("special_fields")
    metadata = metadata if isinstance(metadata, dict) else {}
    normalized["reference"] = normalized.get("reference") or f"TAR-LEGACY-{(index or 0) + 1:04d}"
    normalized["booking_type"] = normalized.get("booking_type", "once-off")
    normalized["status"] = normalized.get("status", "Booking received")
    normalized["full_name"] = normalized.get("full_name") or normalized.get("name", "")
    normalized["phone"] = normalized.get("phone", "")
    normalized["pickup_location"] = normalized.get("pickup_location") or normalized.get("pickup", "")
    normalized["pickup"] = normalized.get("pickup") or normalized["pickup_location"]
    normalized["dropoff_location"] = normalized.get("dropoff_location") or normalized.get("dropoff", "")
    normalized["dropoff"] = normalized.get("dropoff") or normalized["dropoff_location"]
    normalized["preferred_vehicle"] = normalized.get("preferred_vehicle") or normalized.get("car", "")
    normalized["car"] = normalized.get("car") or normalized["preferred_vehicle"]
    normalized["route_summary"] = f"{normalized.get('pickup', 'Pickup')} -> {normalized.get('dropoff', 'Drop-off')}"
    normalized["passengers"] = str(normalized.get("passengers", 1))
    normalized["storage_source"] = normalized.get("storage_source", "json_fallback")
    normalized["payment_status"] = normalized.get("payment_status", "Unpaid")
    normalized["payment_method"] = normalized.get("payment_method", "Cash")
    normalized["payment_reference"] = normalized.get("payment_reference", "")
    normalized["paid_at"] = normalized.get("paid_at", "")
    normalized["invoice_number"] = normalized.get("invoice_number", "")
    normalized["receipt_number"] = normalized.get("receipt_number", "")
    normalized["refund_status"] = normalized.get("refund_status", "")
    normalized["proof_of_payment"] = normalized.get("proof_of_payment", "")
    normalized["vendor_id"] = normalized.get("vendor_id", "")
    normalized["vendor_name"] = normalized.get("vendor_name", "Tarasi Chauffeur")
    normalized["driver_id"] = metadata.get("driver_id") or normalized.get("driver_id", "")
    normalized["driver_name"] = metadata.get("driver_name") or normalized.get("driver_name", "")
    normalized["driver_phone"] = metadata.get("driver_phone") or normalized.get("driver_phone", "")
    normalized["vehicle_name"] = metadata.get("vehicle_name") or normalized.get("vehicle_name") or normalized.get("preferred_vehicle", "")
    normalized["driver_lat"] = metadata.get("driver_lat", normalized.get("driver_lat"))
    normalized["driver_lng"] = metadata.get("driver_lng", normalized.get("driver_lng"))
    normalized["last_location_at"] = metadata.get("last_location_at") or normalized.get("last_location_at", "")
    normalized["booking_pin"] = metadata.get("booking_pin") or normalized.get("booking_pin", "")
    normalized["metadata"] = metadata
    normalized["special_fields"] = metadata or normalized.get("special_fields", {})
    return normalized


def neon_bookings_ready() -> bool:
    return bool(resolve_table_name("bookings"))


def _status_to_db(status: str) -> str:
    return status.lower().replace(" ", "_")


def _status_from_db(status: str | None) -> str:
    raw = (status or "booking_received").replace("_", " ").strip()
    return raw.title() if raw else "Booking Received"


def _row_to_booking(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    booking = {
        "reference": row.get("reference"),
        "booking_type": row.get("booking_type"),
        "full_name": row.get("customer_name"),
        "name": row.get("customer_name"),
        "phone": row.get("phone"),
        "email": row.get("email"),
        "pickup_location": row.get("pickup_location"),
        "pickup": row.get("pickup_location"),
        "dropoff_location": row.get("dropoff_location"),
        "dropoff": row.get("dropoff_location"),
        "date": row.get("pickup_date").isoformat() if row.get("pickup_date") else "",
        "time": str(row.get("pickup_time")) if row.get("pickup_time") else "",
        "return_date": row.get("return_date").isoformat() if row.get("return_date") else "",
        "return_time": str(row.get("return_time")) if row.get("return_time") else "",
        "passengers": row.get("passengers", 1),
        "luggage": row.get("luggage", ""),
        "preferred_vehicle": row.get("preferred_vehicle", ""),
        "car": row.get("preferred_vehicle", ""),
        "estimated_price": row.get("estimated_price"),
        "status": _status_from_db(row.get("status")),
        "payment_status": row.get("payment_status", "Unpaid"),
        "payment_method": row.get("payment_method") or (metadata or {}).get("payment_method", "Cash"),
        "payment_reference": row.get("payment_reference") or (metadata or {}).get("payment_reference", ""),
        "paid_at": row.get("paid_at").isoformat() if row.get("paid_at") else (metadata or {}).get("paid_at", ""),
        "invoice_number": (metadata or {}).get("invoice_number", ""),
        "receipt_number": (metadata or {}).get("receipt_number", ""),
        "refund_status": (metadata or {}).get("refund_status", ""),
        "proof_of_payment": (metadata or {}).get("proof_of_payment", ""),
        "storage_source": row.get("storage_source", "neon"),

        "notes": row.get("notes", ""),
        "request_change_note": (metadata or {}).get("request_change_note", ""),
        "cancel_request_note": (metadata or {}).get("cancel_request_note", ""),
        "driver_id": (metadata or {}).get("driver_id", ""),
        "driver_name": (metadata or {}).get("driver_name", ""),
        "driver_phone": (metadata or {}).get("driver_phone", ""),
        "vehicle_name": (metadata or {}).get("vehicle_name", row.get("preferred_vehicle", "")),
        "driver_lat": (metadata or {}).get("driver_lat"),
        "driver_lng": (metadata or {}).get("driver_lng"),
        "last_location_at": (metadata or {}).get("last_location_at", ""),
        "booking_pin": (metadata or {}).get("booking_pin", ""),
        "previous_status": (metadata or {}).get("previous_status", ""),
        "cancelled_at": (metadata or {}).get("cancelled_at", ""),
        "cancellation_rejected_at": (metadata or {}).get("cancellation_rejected_at", ""),
        "is_test_booking": bool((metadata or {}).get("is_test_booking")),
        "special_fields": metadata or {},
        "metadata": metadata or {},
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else "",
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else "",
    }
    return normalize_booking(booking)


def list_bookings() -> list[dict[str, Any]]:
    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(f"select * from {table_name} order by created_at desc")
                    rows = cursor.fetchall()
            return [_row_to_booking(dict(row)) for row in rows]
        except Exception:
            pass
    bookings = load_json(BOOKINGS_FILE, [])
    normalized = [normalize_booking(item, index) for index, item in enumerate(bookings if isinstance(bookings, list) else [])]
    save_json(BOOKINGS_FILE, normalized)
    return normalized


def generate_booking_reference() -> str:
    year = datetime.now().year
    prefix = f"TAR-{year}-"
    max_number = 0
    for booking in list_bookings():
        reference = str(booking.get("reference", ""))
        if reference.startswith(prefix):
            suffix = reference.replace(prefix, "", 1)
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))
    return f"{prefix}{max_number + 1:04d}"


def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
    booking = normalize_booking(
        {
            "reference": generate_booking_reference(),
            "status": payload.get("status", "Booking received"),
            "payment_status": payload.get("payment_status", "Pending"),
            "created_at": datetime.now().isoformat(),
            "storage_source": "neon" if neon_bookings_ready() else "json_fallback",
            "setup_required_message": "Neon tables are not available yet. JSON fallback is active." if not neon_bookings_ready() else "",
            **payload,
        }
    )
    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"""
                        insert into {table_name} (
                            reference, customer_name, phone, email, booking_type, pickup_location, dropoff_location,
                            pickup_date, pickup_time, return_date, return_time, passengers, luggage, preferred_vehicle,
                            estimated_price, status, payment_status, storage_source, notes, metadata
                        ) values (
                            %(reference)s, %(customer_name)s, %(phone)s, %(email)s, %(booking_type)s, %(pickup_location)s, %(dropoff_location)s,
                            %(pickup_date)s, %(pickup_time)s, %(return_date)s, %(return_time)s, %(passengers)s, %(luggage)s, %(preferred_vehicle)s,
                            %(estimated_price)s, %(status)s, %(payment_status)s, %(storage_source)s, %(notes)s, %(metadata)s
                        )
                        returning *
                        """,
                        {
                            "reference": booking["reference"],
                            "customer_name": booking["full_name"],
                            "phone": booking["phone"],
                            "email": booking.get("email") or None,
                            "booking_type": booking["booking_type"],
                            "pickup_location": booking.get("pickup_location"),
                            "dropoff_location": booking.get("dropoff_location"),
                            "pickup_date": booking.get("date") or None,
                            "pickup_time": booking.get("time") or None,
                            "return_date": booking.get("return_date") or None,
                            "return_time": booking.get("return_time") or None,
                            "passengers": int(booking.get("passengers") or 1),
                            "luggage": booking.get("luggage"),
                            "preferred_vehicle": booking.get("preferred_vehicle"),
                            "estimated_price": _numeric_or_none(booking.get("amount")),
                            "status": _status_to_db(booking["status"]),
                            "payment_status": str(booking.get("payment_status", "pending")).lower(),
                            "storage_source": "neon",
                            "notes": booking.get("notes"),
                            "metadata": Json(booking.get("special_fields") or booking.get("metadata") or {}),
                        },
                    )
                    row = cursor.fetchone()
                conn.commit()
            result = _row_to_booking(dict(row))
            from services.notification_service import trigger_booking_event
            trigger_booking_event("booking_created", result)
            return result
        except Exception:
            booking["storage_source"] = "json_fallback"
    bookings = list_bookings()
    bookings.append(booking)
    save_json(BOOKINGS_FILE, bookings)
    from services.notification_service import trigger_booking_event
    trigger_booking_event("booking_created", booking)
    return booking


def get_booking(reference: str) -> dict[str, Any] | None:
    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(f"select * from {table_name} where reference = %s limit 1", (reference,))
                    row = cursor.fetchone()
            return _row_to_booking(dict(row)) if row else None
        except Exception:
            pass
    return next((booking for booking in list_bookings() if booking.get("reference") == reference), None)


def get_booking_for_email(reference: str, email: str) -> dict[str, Any] | None:
    booking = get_booking(reference)
    if not booking:
        return None
    if str(booking.get("email", "")).strip().lower() == str(email).strip().lower():
        return booking
    if str(booking.get("account_email", "")).strip().lower() == str(email).strip().lower():
        return booking
    return None


def update_booking_status(reference: str, status: str) -> dict[str, Any] | None:
    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"update {table_name} set status = %s, updated_at = now() where reference = %s returning *",
                        (_status_to_db(status), reference),
                    )
                    row = cursor.fetchone()
                conn.commit()
            result = _row_to_booking(dict(row)) if row else None
            if result and status == "Confirmed":
                from services.notification_service import trigger_booking_event
                trigger_booking_event("booking_confirmed", result)
            return result
        except Exception:
            pass
    bookings = list_bookings()
    for booking in bookings:
        if booking.get("reference") == reference:
            booking["status"] = status
            booking["updated_at"] = datetime.now().isoformat()
            save_json(BOOKINGS_FILE, bookings)
            if status == "Confirmed":
                from services.notification_service import trigger_booking_event
                trigger_booking_event("booking_confirmed", booking)
            return booking
    return None


def append_booking_request(reference: str, request_type: str, note: str, status: str | None = None) -> dict[str, Any] | None:
    booking = get_booking(reference)
    if not booking:
        return None
    metadata = dict(booking.get("metadata") or booking.get("special_fields") or {})
    if request_type == "cancel_request":
        metadata["previous_status"] = booking.get("status", "Confirmed")
    metadata[f"{request_type}_note"] = note
    metadata[f"{request_type}_requested_at"] = datetime.now().isoformat()
    notes = booking.get("notes", "")
    note_line = f"{request_type.replace('_', ' ').title()}: {note}".strip()
    combined_notes = f"{notes}\n{note_line}".strip() if notes else note_line

    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"""
                        update {table_name}
                        set metadata = %s, notes = %s, status = %s, updated_at = now()
                        where reference = %s
                        returning *
                        """,
                        (
                            Json(metadata),
                            combined_notes,
                            _status_to_db(status or booking.get("status", "Booking received")),
                            reference,
                        ),
                    )
                    row = cursor.fetchone()
                conn.commit()
            return _row_to_booking(dict(row)) if row else None
        except Exception:
            pass

    bookings = list_bookings()
    for item in bookings:
        if item.get("reference") == reference:
            item["metadata"] = metadata
            item["special_fields"] = metadata
            item["notes"] = combined_notes
            if status:
                item["status"] = status
            item["updated_at"] = datetime.now().isoformat()
            save_json(BOOKINGS_FILE, bookings)
            return item
    return None


def update_booking_metadata(reference: str, metadata_updates: dict[str, Any], status: str | None = None) -> dict[str, Any] | None:
    booking = get_booking(reference)
    if not booking:
        return None
    metadata = dict(booking.get("metadata") or booking.get("special_fields") or {})
    metadata.update(metadata_updates)

    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            if not table_name:
                raise RuntimeError("Bookings table is unavailable.")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"""
                        update {table_name}
                        set metadata = %s, status = %s, updated_at = now()
                        where reference = %s
                        returning *
                        """,
                        (
                            Json(metadata),
                            _status_to_db(status or booking.get("status", "Booking received")),
                            reference,
                        ),
                    )
                    row = cursor.fetchone()
                conn.commit()
            return _row_to_booking(dict(row)) if row else None
        except Exception:
            pass

    bookings = list_bookings()
    for item in bookings:
        if item.get("reference") == reference:
            item["metadata"] = metadata
            item["special_fields"] = metadata
            if status:
                item["status"] = status
            item["updated_at"] = datetime.now().isoformat()
            save_json(BOOKINGS_FILE, bookings)
            return item
    return None


def _numeric_or_none(value: Any):
    if value in (None, "", "Quote required"):
        return None
    if isinstance(value, (int, float)):
        return value
    cleaned = str(value).replace("N$", "").replace(",", "").replace("From ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

def update_booking_payment(reference: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    booking = get_booking(reference)
    if not booking:
        return None
    
    # Generate invoice/receipt numbers if missing and paid
    if updates.get("payment_status") == "Paid":
        if not booking.get("invoice_number"):
            updates["invoice_number"] = f"INV-{reference.replace('TAR-', '')}"
        if not booking.get("receipt_number"):
            updates["receipt_number"] = f"RCP-{reference.replace('TAR-', '')}"
        if not updates.get("paid_at"):
            updates["paid_at"] = datetime.now().isoformat()

    metadata = dict(booking.get("metadata") or booking.get("special_fields") or {})
    
    # Fields that might be in DB or Metadata
    db_fields = ["payment_status", "payment_method", "payment_reference"]
    
    db_updates = {}
    for field in db_fields:
        if field in updates:
            db_updates[field] = updates[field]
    
    for k, v in updates.items():
        if k not in db_fields:
            metadata[k] = v

    if neon_bookings_ready():
        try:
            table_name = resolve_table_name("bookings")
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Construct dynamic update for DB fields
                    set_clauses = ["metadata = %s", "updated_at = now()"]
                    params = [Json(metadata)]
                    for k, v in db_updates.items():
                        set_clauses.append(f"{k} = %s")
                        params.append(v)
                    params.append(reference)
                    
                    query = f"update {table_name} set {', '.join(set_clauses)} where reference = %s returning *"
                    cursor.execute(query, tuple(params))
                    row = cursor.fetchone()
                conn.commit()
            result = _row_to_booking(dict(row)) if row else None
            if result and updates.get("payment_status") == "Paid":
                from services.notification_service import trigger_booking_event
                trigger_booking_event("payment_verified", result)
            return result
        except Exception as e:
            print(f"DB update failed: {e}")

    bookings = list_bookings()
    for item in bookings:
        if item.get("reference") == reference:
            item.update(updates)
            item["metadata"] = metadata
            item["special_fields"] = metadata
            item["updated_at"] = datetime.now().isoformat()
            save_json(BOOKINGS_FILE, bookings)
            if updates.get("payment_status") == "Paid":
                from services.notification_service import trigger_booking_event
                trigger_booking_event("payment_verified", item)
            return item
    return None
