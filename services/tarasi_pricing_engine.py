from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from services.db_service import fetch_rows, get_database_mode, insert_row, resolve_table_name, update_row
from services.driver_service import list_drivers
from services.storage_service import load_json, save_json
from services.tarasi_distance_service import estimate_distance, match_zone, normalise
from services.tarasi_map_service import geocode_address


QUOTE_FILE = "tarasi_booking_quotes.json"
PAYMENT_FILE = "tarasi_booking_payments.json"
INVOICE_FILE = "tarasi_booking_invoices.json"
BANK_DETAILS = {
    "bank": "First National Bank (FNB)",
    "account_name": "Tarasi Shuttle and Transfer Services CC",
    "account_number": "64289981259",
    "branch": "Maerua Mall",
    "branch_code": "282273",
    "email": "tarasishuttle@gmail.com",
}
_CACHE_TTL_SECONDS = 60
_CACHE: dict[str, dict[str, Any]] = {
    "pricing_rules": {"loaded_at": None, "data": []},
    "pricing_zones": {"loaded_at": None, "data": []},
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _quote_number() -> str:
    return f"QUO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _invoice_number(document_type: str = "Invoice") -> str:
    prefix = "INV" if str(document_type).lower() == "invoice" else "QUO"
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _booking_number() -> str:
    return f"TAR-{datetime.now().strftime('%Y')}-{str(uuid.uuid4())[:8].upper()}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_rows(path: str) -> list[dict[str, Any]]:
    rows = load_json(path, [])
    return rows if isinstance(rows, list) else []


def _save_json_rows(path: str, rows: list[dict[str, Any]]) -> None:
    save_json(path, rows)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _cache_valid(cache_name: str) -> bool:
    loaded_at = _CACHE[cache_name]["loaded_at"]
    if not loaded_at:
        return False
    return (datetime.now() - loaded_at).total_seconds() < _CACHE_TTL_SECONDS


def _cache_set(cache_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _CACHE[cache_name]["loaded_at"] = datetime.now()
    _CACHE[cache_name]["data"] = rows
    return rows


def _split_trip_text(payload: dict[str, Any]) -> tuple[str, str]:
    pickup = str(payload.get("pickup_text") or payload.get("pickup") or "").strip()
    dropoff = str(payload.get("dropoff_text") or payload.get("dropoff") or "").strip()
    if pickup and not dropoff:
        lowered = pickup.lower()
        if " to " in lowered:
            left, right = pickup.split(" to ", 1)
            pickup = left.strip()
            dropoff = right.strip()
    return pickup, dropoff


def infer_service_type(pickup: str, dropoff: str, requested: str | None = None, vehicle_type: str | None = None) -> str:
    if requested:
        return str(requested).strip().lower()
    trip_text = f"{pickup} {dropoff}".lower()
    if "airport" in trip_text or "hosea kutako" in trip_text or "eros airport" in trip_text:
        return "airport"
    if vehicle_type == "vip":
        return "vip"
    if any(term in trip_text for term in ["swakopmund", "walvis bay", "sossusvlei", "etosha", "otjiwarongo", "okahandja"]):
        return "long_distance"
    return "town"


def _is_night_trip(pickup_time: str | None) -> bool:
    raw = str(pickup_time or "").strip()
    if not raw:
        return False
    try:
        hour = int(raw.split(":")[0])
    except (TypeError, ValueError, IndexError):
        return False
    return hour >= 21 or hour < 5


def get_active_pricing_rules() -> list[dict[str, Any]]:
    if _cache_valid("pricing_rules"):
        return list(_CACHE["pricing_rules"]["data"])
    if get_database_mode() not in {"neon", "supabase"} or not resolve_table_name("pricing_rules"):
        return _cache_set("pricing_rules", [])
    rows = fetch_rows("pricing_rules", filters={"is_active": True}, limit=200, order_by="updated_at desc nulls last")
    return _cache_set("pricing_rules", rows or [])


def get_active_pricing_zones() -> list[dict[str, Any]]:
    if _cache_valid("pricing_zones"):
        return list(_CACHE["pricing_zones"]["data"])
    if get_database_mode() not in {"neon", "supabase"} or not resolve_table_name("pricing_zones"):
        return _cache_set("pricing_zones", [])
    rows = fetch_rows("pricing_zones", filters={"is_active": True}, limit=200, order_by="zone_name asc")
    return _cache_set("pricing_zones", rows or [])


def _matching_rule_value(rule_names: list[str], vehicle_type: str, default: float = 0.0) -> float:
    rules = get_active_pricing_rules()
    desired_types = [str(name).strip().lower() for name in rule_names]
    vehicle_candidates = [vehicle_type]
    if vehicle_type != "sedan":
        vehicle_candidates.append("sedan")
    vehicle_candidates.extend(["all", "default", ""])
    for candidate_vehicle in vehicle_candidates:
        for row in rules:
            rule_type = str(row.get("rule_type") or row.get("rule_name") or "").strip().lower()
            row_vehicle = str(row.get("vehicle_type") or "all").strip().lower()
            if rule_type in desired_types and row_vehicle == candidate_vehicle:
                return _safe_float(row.get("value"), default)
    return default


def _service_type_fee(service_type: str, vehicle_type: str) -> float:
    keys = [
        f"service_type_fee_{service_type}",
        f"service_type_{service_type}_fee",
        f"{service_type}_service_fee",
        f"{service_type}_fee",
    ]
    return _matching_rule_value(keys, vehicle_type, 0.0)


def match_zone_by_text_or_radius(address_text: str | None, lat: float | None, lng: float | None) -> dict[str, Any] | None:
    return match_zone(text=address_text, lat=lat, lng=lng)


def _airport_route(pickup_text: str, dropoff_text: str, pickup_zone: dict[str, Any] | None, dropoff_zone: dict[str, Any] | None) -> bool:
    zone_names = f"{(pickup_zone or {}).get('name', '')} {(dropoff_zone or {}).get('name', '')}"
    return "airport" in normalise(f"{pickup_text} {dropoff_text} {zone_names}")


def _geocode_payload(pickup_text: str, dropoff_text: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    pickup_lat = payload.get("pickup_lat")
    pickup_lng = payload.get("pickup_lng")
    dropoff_lat = payload.get("dropoff_lat")
    dropoff_lng = payload.get("dropoff_lng")

    pickup_geo = None
    dropoff_geo = None
    if pickup_lat not in (None, "") and pickup_lng not in (None, ""):
        pickup_geo = {
            "display_name": pickup_text,
            "lat": _safe_float(pickup_lat),
            "lng": _safe_float(pickup_lng),
            "suburb_area": "",
            "confidence": "high",
        }
    elif pickup_text:
        pickup_geo = geocode_address(pickup_text)

    if dropoff_lat not in (None, "") and dropoff_lng not in (None, ""):
        dropoff_geo = {
            "display_name": dropoff_text,
            "lat": _safe_float(dropoff_lat),
            "lng": _safe_float(dropoff_lng),
            "suburb_area": "",
            "confidence": "high",
        }
    elif dropoff_text:
        dropoff_geo = geocode_address(dropoff_text)

    return pickup_geo, dropoff_geo


def _zone_field(zone: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    if not zone:
        return default
    raw_zone = zone.get("raw") if isinstance(zone.get("raw"), dict) else zone
    return _safe_float(raw_zone.get(key), default)


def _admin_breakdown(quote: dict[str, Any], pickup_zone_fee: float, dropoff_zone_fee: float, service_type_fee: float, multiplier_value: float, minimum_fare: float) -> dict[str, Any]:
    return {
        "pickup_zone_fee": _money(pickup_zone_fee),
        "dropoff_zone_fee": _money(dropoff_zone_fee),
        "service_type_fee": _money(service_type_fee),
        "vehicle_multiplier_value": multiplier_value,
        "minimum_fare": _money(minimum_fare),
        "used_default_rule": quote.get("used_default_rule", False),
    }


def calculate_taximeter_quote(payload: dict[str, Any]) -> dict[str, Any]:
    pickup_text, dropoff_text = _split_trip_text(payload)
    vehicle_type = str(payload.get("vehicle_type") or payload.get("preferred_vehicle") or "sedan").strip().lower() or "sedan"
    service_type = infer_service_type(
        pickup_text,
        dropoff_text,
        requested=payload.get("service_type") or payload.get("pricing_service_type"),
        vehicle_type=vehicle_type,
    )
    passengers = max(1, _safe_int(payload.get("passengers"), 1))
    luggage_count = max(0, _safe_int(payload.get("luggage_count"), 0))
    waiting_minutes = max(0, _safe_int(payload.get("waiting_minutes"), 0))
    pickup_time = str(payload.get("pickup_time") or payload.get("travel_time") or payload.get("time") or "").strip()
    notes: list[str] = []

    pickup_geo, dropoff_geo = _geocode_payload(pickup_text, dropoff_text, payload)
    pickup_lat = _safe_float((pickup_geo or {}).get("lat"))
    pickup_lng = _safe_float((pickup_geo or {}).get("lng"))
    dropoff_lat = _safe_float((dropoff_geo or {}).get("lat"))
    dropoff_lng = _safe_float((dropoff_geo or {}).get("lng"))

    pickup_zone = match_zone_by_text_or_radius(pickup_text, pickup_lat, pickup_lng)
    if not pickup_zone and (pickup_geo or {}).get("suburb_area"):
        pickup_zone = match_zone_by_text_or_radius((pickup_geo or {}).get("suburb_area"), pickup_lat, pickup_lng)
    dropoff_zone = match_zone_by_text_or_radius(dropoff_text, dropoff_lat, dropoff_lng)
    if not dropoff_zone and (dropoff_geo or {}).get("suburb_area"):
        dropoff_zone = match_zone_by_text_or_radius((dropoff_geo or {}).get("suburb_area"), dropoff_lat, dropoff_lng)

    if pickup_geo and pickup_geo.get("display_name") and pickup_geo["display_name"] != pickup_text:
        notes.append(f"Pickup matched to {pickup_geo['display_name']}.")
    if dropoff_geo and dropoff_geo.get("display_name") and dropoff_geo["display_name"] != dropoff_text:
        notes.append(f"Drop-off matched to {dropoff_geo['display_name']}.")
    if pickup_zone and pickup_zone.get("matched_by") == "radius":
        notes.append(f"Pickup used closest mapped zone: {pickup_zone.get('name')}.")
    if dropoff_zone and dropoff_zone.get("matched_by") == "radius":
        notes.append(f"Drop-off used closest mapped zone: {dropoff_zone.get('name')}.")

    distance_data = estimate_distance(
        pickup_text,
        dropoff_text,
        pickup_coords=(pickup_lat, pickup_lng) if pickup_lat is not None and pickup_lng is not None else None,
        dropoff_coords=(dropoff_lat, dropoff_lng) if dropoff_lat is not None and dropoff_lng is not None else None,
    )
    notes.extend(distance_data.get("notes", []))

    used_default_rule = not pickup_zone and not dropoff_zone
    if used_default_rule:
        notes.append("No zone match was found. Tarasi used the active default pricing rules.")

    base_fare = _zone_field(pickup_zone or dropoff_zone, "base_fare", _matching_rule_value(["base_fare"], vehicle_type, 0.0))
    price_per_km = _zone_field(pickup_zone or dropoff_zone, "price_per_km", _matching_rule_value(["price_per_km", "per_km", "km_rate"], vehicle_type, 0.0))
    minimum_fare = max(
        _zone_field(pickup_zone or dropoff_zone, "minimum_fare", 0.0),
        _matching_rule_value(["minimum_fare"], vehicle_type, 0.0),
    )
    luggage_unit_fee = max(
        _zone_field(pickup_zone or dropoff_zone, "luggage_fee", 0.0),
        _matching_rule_value(["luggage_fee"], vehicle_type, 0.0),
    )
    waiting_unit_fee = max(
        _zone_field(pickup_zone or dropoff_zone, "waiting_fee", 0.0),
        _matching_rule_value(["waiting_fee", "waiting_per_10_min"], vehicle_type, 0.0),
    )
    night_fee_value = max(
        _zone_field(pickup_zone or dropoff_zone, "night_fee", 0.0),
        _matching_rule_value(["night_fee"], vehicle_type, 0.0),
    )
    airport_fee_value = max(
        _zone_field(pickup_zone or dropoff_zone, "airport_fee", 0.0),
        _matching_rule_value(["airport_fee"], vehicle_type, 0.0),
    )
    pickup_zone_fee = _matching_rule_value(["pickup_zone_fee"], vehicle_type, 0.0)
    dropoff_zone_fee = _matching_rule_value(["dropoff_zone_fee"], vehicle_type, 0.0)
    vehicle_multiplier_value = max(_matching_rule_value(["vehicle_multiplier", "multiplier"], vehicle_type, 1.0), 1.0)
    service_type_fee = _service_type_fee(service_type, vehicle_type)

    distance_km = _money(distance_data.get("distance_km"))
    duration_minutes = _safe_int(distance_data.get("duration_minutes"), 0)
    distance_fee = _money(distance_km * price_per_km)
    zone_fee = _money(pickup_zone_fee + dropoff_zone_fee)
    airport_fee = _money(airport_fee_value if _airport_route(pickup_text, dropoff_text, pickup_zone, dropoff_zone) else 0.0)
    luggage_fee = _money(luggage_count * luggage_unit_fee)
    waiting_fee = _money(((waiting_minutes + 9) // 10) * waiting_unit_fee if waiting_minutes else 0.0)
    night_fee = _money(night_fee_value if _is_night_trip(pickup_time) else 0.0)

    subtotal_before_multiplier = _money(
        base_fare
        + distance_fee
        + zone_fee
        + airport_fee
        + luggage_fee
        + waiting_fee
        + night_fee
        + service_type_fee
    )
    vehicle_multiplier = _money(subtotal_before_multiplier * max(vehicle_multiplier_value - 1.0, 0.0))
    subtotal = _money(subtotal_before_multiplier + vehicle_multiplier)
    final_price = _money(max(subtotal, minimum_fare))

    price_confidence = str(distance_data.get("confidence") or "low")
    if used_default_rule:
        price_confidence = "low"
    elif pickup_geo is None or dropoff_geo is None:
        price_confidence = "low" if price_confidence == "high" else price_confidence
    elif pickup_zone and pickup_zone.get("matched_by") == "radius":
        price_confidence = "low"
    elif dropoff_zone and dropoff_zone.get("matched_by") == "radius":
        price_confidence = "low"

    if final_price <= 0:
        notes.append("No active pricing configuration could produce a fare for this route yet.")
    short_note = notes[0] if notes else ("Estimated from active Tarasi pricing zones and rules." if final_price > 0 else "Pricing configuration is incomplete for this route.")

    quote = {
        "quote_number": _quote_number(),
        "pickup_text": pickup_text,
        "dropoff_text": dropoff_text,
        "pickup_zone": (pickup_zone or {}).get("name", ""),
        "dropoff_zone": (dropoff_zone or {}).get("name", ""),
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "vehicle_type": vehicle_type,
        "service_type": service_type,
        "passengers": passengers,
        "luggage_count": luggage_count,
        "base_fare": _money(base_fare),
        "distance_fee": distance_fee,
        "zone_fee": zone_fee,
        "airport_fee": airport_fee,
        "luggage_fee": luggage_fee,
        "waiting_fee": waiting_fee,
        "night_fee": night_fee,
        "vehicle_multiplier": vehicle_multiplier,
        "subtotal": subtotal,
        "final_price": final_price,
        "price_confidence": price_confidence,
        "pricing_notes": " ".join(note for note in notes if note).strip(),
        "short_note": short_note,
        "price_breakdown": {
            "base_fare": _money(base_fare),
            "distance_fee": distance_fee,
            "zone_fee": zone_fee,
            "airport_fee": airport_fee,
            "luggage_fee": luggage_fee,
            "waiting_fee": waiting_fee,
            "night_fee": night_fee,
            "vehicle_multiplier": vehicle_multiplier,
            "service_type_fee": _money(service_type_fee),
            "subtotal": subtotal,
            "final_price": final_price,
        },
        "confidence": price_confidence,
        "notes": notes,
        "suggestions": ["Create booking", "Try another route", "Talk to support"] if final_price > 0 else ["Update pricing rules", "Add zones"],
        "pickup_match": pickup_geo,
        "dropoff_match": dropoff_geo,
        "pickup_zone_data": pickup_zone or {},
        "dropoff_zone_data": dropoff_zone or {},
        "used_default_rule": used_default_rule,
    }
    quote["admin_breakdown"] = _admin_breakdown(
        quote,
        pickup_zone_fee=pickup_zone_fee,
        dropoff_zone_fee=dropoff_zone_fee,
        service_type_fee=service_type_fee,
        multiplier_value=vehicle_multiplier_value,
        minimum_fare=minimum_fare,
    )
    return quote


def calculate_customer_quote(payload: dict[str, Any]) -> dict[str, Any]:
    quote = calculate_taximeter_quote(payload)
    return quote


def calculate_quote(payload: dict[str, Any]) -> dict[str, Any]:
    return calculate_customer_quote(payload)


def save_quote(quote: dict[str, Any], user_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    safe_quote = _json_safe(quote)
    row = {
        "quote_number": safe_quote["quote_number"],
        "user_id": user_id or "",
        "session_id": session_id or "",
        "customer_name": safe_quote.get("client_name") or "",
        "email": safe_quote.get("email") or "",
        "phone": safe_quote.get("client_phone") or safe_quote.get("phone") or "",
        "pickup_text": safe_quote["pickup_text"],
        "dropoff_text": safe_quote["dropoff_text"],
        "pickup_zone": safe_quote["pickup_zone"],
        "dropoff_zone": safe_quote["dropoff_zone"],
        "distance_km": safe_quote["distance_km"],
        "duration_minutes": safe_quote["duration_minutes"],
        "vehicle_type": safe_quote["vehicle_type"],
        "passengers": safe_quote.get("passengers", 1),
        "luggage_count": safe_quote.get("luggage_count", 0),
        "service_type": safe_quote["service_type"],
        "base_fare": safe_quote["base_fare"],
        "distance_fee": safe_quote["distance_fee"],
        "zone_fee": _money(safe_quote.get("zone_fee", 0) + safe_quote.get("airport_fee", 0)),
        "waiting_fee": safe_quote["waiting_fee"],
        "luggage_fee": safe_quote["luggage_fee"],
        "night_fee": safe_quote["night_fee"],
        "service_fee": _money(safe_quote.get("vehicle_multiplier", 0) + safe_quote.get("price_breakdown", {}).get("service_type_fee", 0)),
        "subtotal": safe_quote["subtotal"],
        "amount": safe_quote["final_price"],
        "final_price": safe_quote["final_price"],
        "currency": "NAD",
        "price_confidence": safe_quote["price_confidence"],
        "pricing_notes": safe_quote["pricing_notes"],
        "status": "quoted",
        "pdf_url": safe_quote.get("pdf_url") or "",
        "metadata": safe_quote,
        "created_at": _now(),
        "updated_at": _now(),
    }
    if get_database_mode() in {"neon", "supabase"} and resolve_table_name("quotes"):
        created = insert_row("quotes", row)
        if created:
            return created
    json_row = {"id": str(uuid.uuid4()), **row}
    rows = _json_rows(QUOTE_FILE)
    rows.append(json_row)
    _save_json_rows(QUOTE_FILE, rows)
    return json_row


def list_quotes(limit: int = 100) -> list[dict[str, Any]]:
    if get_database_mode() in {"neon", "supabase"} and resolve_table_name("quotes"):
        return fetch_rows("quotes", limit=limit, order_by="created_at desc nulls last")
    rows = _json_rows(QUOTE_FILE)
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_quote_by_number(quote_number: str) -> dict[str, Any] | None:
    if not quote_number:
        return None
    rows = fetch_rows("quotes", filters={"quote_number": quote_number}, limit=1) if resolve_table_name("quotes") else []
    if rows:
        return rows[0]
    for row in list_quotes(limit=300):
        if row.get("quote_number") == quote_number:
            return row
    return None


def create_booking(payload: dict[str, Any], user_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    from services.booking_service import create_booking as create_core_booking

    quote_number = str(payload.get("quote_number") or "").strip()
    quote = get_quote_by_number(quote_number)
    if not quote:
        quote = save_quote(calculate_customer_quote(payload), user_id=user_id, session_id=session_id)

    booking_reference = _booking_number()
    booking_payload = {
        "reference": booking_reference,
        "booking_type": payload.get("booking_type") or quote.get("service_type") or "once-off",
        "full_name": str(payload.get("client_name") or payload.get("full_name") or "Guest customer").strip(),
        "phone": str(payload.get("client_phone") or payload.get("phone") or "").strip(),
        "email": str(payload.get("email") or "").strip(),
        "pickup_location": quote.get("pickup_text") or payload.get("pickup"),
        "dropoff_location": quote.get("dropoff_text") or payload.get("dropoff"),
        "pickup": quote.get("pickup_text") or payload.get("pickup"),
        "dropoff": quote.get("dropoff_text") or payload.get("dropoff"),
        "date": payload.get("travel_date") or payload.get("date") or "",
        "time": payload.get("travel_time") or payload.get("pickup_time") or payload.get("time") or "",
        "passengers": quote.get("passengers") or payload.get("passengers") or 1,
        "luggage": f"{quote.get('luggage_count', 0)} bag(s)",
        "preferred_vehicle": quote.get("vehicle_type") or payload.get("vehicle_type") or "sedan",
        "amount": quote.get("final_price") or payload.get("final_price") or 0,
        "notes": payload.get("notes") or "",
        "metadata": {
            "quote_number": quote.get("quote_number"),
            "pickup_zone": quote.get("pickup_zone"),
            "dropoff_zone": quote.get("dropoff_zone"),
            "distance_km": quote.get("distance_km"),
            "duration_minutes": quote.get("duration_minutes"),
            "service_type": quote.get("service_type"),
            "pricing_notes": quote.get("pricing_notes"),
            "session_id": session_id or "",
            "user_id": user_id or "",
        },
    }
    booking = create_core_booking(booking_payload)
    booking["booking_number"] = booking.get("reference") or booking_reference
    booking["final_price"] = quote.get("final_price") or booking_payload["amount"]
    booking["payment_status"] = booking.get("payment_status") or "Unpaid"
    booking["quote_number"] = quote.get("quote_number")
    return booking


def add_booking_status_history(booking_id: str | None, status: str, note: str) -> dict[str, Any]:
    row = {"id": str(uuid.uuid4()), "booking_id": booking_id, "status": status, "note": note, "created_at": _now()}
    rows = load_json("tarasi_booking_status_history.json", [])
    if not isinstance(rows, list):
        rows = []
    rows.append(row)
    save_json("tarasi_booking_status_history.json", rows)
    return row


def list_bookings(limit: int = 100) -> list[dict[str, Any]]:
    from services.booking_service import list_bookings as list_core_bookings

    rows = list_core_bookings()
    normalized = []
    for row in rows[:limit]:
        normalized.append(
            {
                "booking_number": row.get("reference"),
                "reference": row.get("reference"),
                "quote_id": (row.get("metadata") or {}).get("quote_number"),
                "client_name": row.get("full_name"),
                "client_phone": row.get("phone"),
                "pickup_text": row.get("pickup"),
                "dropoff_text": row.get("dropoff"),
                "pickup_zone": (row.get("metadata") or {}).get("pickup_zone", ""),
                "dropoff_zone": (row.get("metadata") or {}).get("dropoff_zone", ""),
                "travel_date": row.get("date"),
                "travel_time": row.get("time"),
                "vehicle_type": row.get("preferred_vehicle"),
                "passengers": row.get("passengers"),
                "luggage_count": _safe_int(str(row.get("luggage") or "0").split(" ")[0], 0),
                "service_type": (row.get("metadata") or {}).get("service_type", "town"),
                "final_price": row.get("amount"),
                "status": row.get("status"),
                "payment_status": row.get("payment_status"),
                "invoice_number": row.get("invoice_number", ""),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return normalized


def get_booking_by_number(booking_number: str) -> dict[str, Any] | None:
    from services.booking_service import get_booking

    booking = get_booking(booking_number)
    if not booking:
        return None
    booking["booking_number"] = booking.get("reference")
    booking["final_price"] = booking.get("amount")
    return booking


def update_booking_status(booking_number: str, status: str, note: str = "") -> dict[str, Any] | None:
    from services.booking_service import update_booking_status as update_core_booking_status

    updated = update_core_booking_status(booking_number, status)
    if updated and note:
        metadata = dict(updated.get("metadata") or {})
        history = metadata.get("pricing_status_notes") if isinstance(metadata.get("pricing_status_notes"), list) else []
        history.append({"status": status, "note": note, "created_at": _now()})
        update_row("bookings", "reference", booking_number, {"metadata": {**metadata, "pricing_status_notes": history}})
        updated["metadata"] = {**metadata, "pricing_status_notes": history}
    return updated


def list_payments(limit: int = 100) -> list[dict[str, Any]]:
    rows = _json_rows(PAYMENT_FILE)
    rows.sort(key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return rows[:limit]


def get_payment_by_booking_number(booking_number: str) -> dict[str, Any] | None:
    for row in list_payments(limit=300):
        if row.get("booking_number") == booking_number:
            return row
    return None


def create_payment_proof(booking_number: str, proof_url: str = "", proof_text: str = "") -> dict[str, Any] | None:
    booking = get_booking_by_number(booking_number)
    if not booking:
        return None
    row = {
        "id": str(uuid.uuid4()),
        "booking_number": booking_number,
        "payment_reference": f"PAY-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        "amount": booking.get("final_price") or 0,
        "payment_method": "bank_transfer",
        "proof_url": proof_url.strip() or f"TEXT:{proof_text.strip()}",
        "status": "pending",
        "admin_notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    rows = _json_rows(PAYMENT_FILE)
    rows.append(row)
    _save_json_rows(PAYMENT_FILE, rows)
    update_row("bookings", "reference", booking_number, {"payment_status": "Pending"})
    return row


def update_payment_status(booking_number: str, status: str, admin_notes: str = "") -> dict[str, Any] | None:
    payments = _json_rows(PAYMENT_FILE)
    for index, row in enumerate(payments):
        if row.get("booking_number") == booking_number:
            payments[index] = {**row, "status": status, "admin_notes": admin_notes, "updated_at": _now()}
            _save_json_rows(PAYMENT_FILE, payments)
            update_row("bookings", "reference", booking_number, {"payment_status": "Paid" if status == "approved" else "Failed"})
            return payments[index]
    return None


def list_invoices(limit: int = 100) -> list[dict[str, Any]]:
    if get_database_mode() in {"neon", "supabase"} and resolve_table_name("invoices"):
        return fetch_rows("invoices", limit=limit, order_by="created_at desc nulls last")
    rows = _json_rows(INVOICE_FILE)
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_invoice_by_booking_number(booking_number: str) -> dict[str, Any] | None:
    for row in list_invoices(limit=300):
        if row.get("booking_number") == booking_number:
            return row
    return None


def create_invoice_for_booking(booking_number: str, document_type: str = "Invoice", base_url: str = "") -> dict[str, Any] | None:
    booking = get_booking_by_number(booking_number)
    if not booking:
        return None
    existing = get_invoice_by_booking_number(booking_number)
    if existing:
        return existing
    invoice_url = f"{base_url.rstrip('/')}/booking/{booking_number}/invoice" if base_url else f"/booking/{booking_number}/invoice"
    row = {
        "booking_number": booking_number,
        "invoice_number": _invoice_number(document_type=document_type),
        "customer_name": booking.get("full_name") or booking.get("client_name") or "Tarasi customer",
        "amount": booking.get("final_price") or booking.get("amount") or 0,
        "currency": "NAD",
        "status": booking.get("payment_status") or "Unpaid",
        "pdf_url": invoice_url,
        "created_at": _now(),
        "updated_at": _now(),
    }
    created = None
    if get_database_mode() in {"neon", "supabase"} and resolve_table_name("invoices"):
        payload = {key: value for key, value in row.items() if key != "booking_number"}
        created = insert_row("invoices", payload)
        if created is not None:
            created["booking_number"] = booking_number
    if created is None:
        json_row = {"id": str(uuid.uuid4()), **row}
        rows = _json_rows(INVOICE_FILE)
        rows.append(json_row)
        _save_json_rows(INVOICE_FILE, rows)
        created = json_row
    metadata = dict(booking.get("metadata") or {})
    metadata["invoice_number"] = created["invoice_number"]
    update_row("bookings", "reference", booking_number, {"metadata": metadata})
    return created


def _driver_matches_vehicle(driver: dict[str, Any], vehicle_type: str) -> bool:
    haystack = " ".join(
        [
            str(driver.get("service_type") or ""),
            str(driver.get("vehicle_name") or ""),
            str((driver.get("assigned_vehicle") or {}).get("name") if isinstance(driver.get("assigned_vehicle"), dict) else ""),
        ]
    ).lower()
    if vehicle_type == "vip":
        return "vip" in haystack or "executive" in haystack or bool(driver.get("admin_approved"))
    return vehicle_type in haystack or vehicle_type in str(driver.get("service_type") or "").lower()


def assign_best_driver(booking_number: str) -> dict[str, Any] | None:
    booking = get_booking_by_number(booking_number)
    if not booking:
        return None
    drivers = list_drivers()
    booking_zone = normalise((booking.get("metadata") or {}).get("pickup_zone") or booking.get("pickup") or "")
    vehicle_type = str(booking.get("preferred_vehicle") or booking.get("vehicle_type") or "sedan").lower()
    candidates = []
    for driver in drivers:
        status = str(driver.get("status") or driver.get("availability") or "").lower()
        if status not in {"online", "available", "active", "assigned"}:
            continue
        if not _driver_matches_vehicle(driver, vehicle_type):
            continue
        zone_score = 1 if booking_zone and booking_zone in normalise(driver.get("based_area") or "") else 0
        rating = _safe_float(driver.get("rating"), 0.0)
        candidates.append((zone_score, rating, driver))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    driver = candidates[0][2]
    metadata = dict(booking.get("metadata") or {})
    metadata.update(
        {
            "driver_id": driver.get("id") or driver.get("driver_id"),
            "driver_name": driver.get("full_name") or driver.get("name") or "",
            "vehicle_name": driver.get("vehicle_name") or (driver.get("assigned_vehicle") or {}).get("name", ""),
        }
    )
    updated = update_row("bookings", "reference", booking_number, {"status": "Driver assigned", "metadata": metadata})
    if updated:
        updated["booking_number"] = updated.get("reference")
    return updated


def get_bank_details() -> dict[str, str]:
    return dict(BANK_DETAILS)
