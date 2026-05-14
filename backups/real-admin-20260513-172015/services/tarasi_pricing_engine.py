from __future__ import annotations

import json
import os
import uuid
from contextlib import closing
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from services.driver_service import list_drivers
from services.storage_service import load_json, save_json
from services.tarasi_distance_service import estimate_distance, normalise, resolve_zone


QUOTE_FILE = "tarasi_booking_quotes.json"
BOOKING_FILE = "tarasi_ride_bookings.json"
STATUS_FILE = "tarasi_booking_status_history.json"
PAYMENT_FILE = "tarasi_booking_payments.json"
INVOICE_FILE = "tarasi_booking_invoices.json"
SUPABASE_KEY_NAMES = ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY"]
BANK_DETAILS = {
    "bank": "First National Bank (FNB)",
    "account_name": "Tarasi Shuttle and Transfer Services CC",
    "account_number": "64289981259",
    "branch": "Maerua Mall",
    "branch_code": "282273",
    "email": "tarasishuttle@gmail.com",
}

VEHICLE_RULES = {
    "sedan": {"base_fare": 30, "per_km": 14, "minimum_fare": 100, "waiting_per_10_min": 25, "multiplier": 1.0, "night_fee": 55, "luggage_fee": 15},
    "suv": {"base_fare": 50, "per_km": 20, "minimum_fare": 180, "waiting_per_10_min": 35, "multiplier": 1.2, "night_fee": 80, "luggage_fee": 22},
    "quantum": {"base_fare": 100, "per_km": 28, "minimum_fare": 350, "waiting_per_10_min": 50, "multiplier": 1.45, "night_fee": 120, "luggage_fee": 30},
    "vip": {"base_fare": 120, "per_km": 35, "minimum_fare": 300, "waiting_per_10_min": 60, "multiplier": 1.65, "night_fee": 170, "luggage_fee": 40},
}
AIRPORT_FIXED_GUIDE = {"sedan": 350, "suv": 550, "quantum": 850, "vip": 900}
PAYOUT_RATES = {"sedan": 0.75, "suv": 0.75, "quantum": 0.76, "vip": 0.74}
COMMISSION_RATES = {"sedan": 0.14, "suv": 0.14, "quantum": 0.13, "vip": 0.15}
MIN_PROFIT_BY_SERVICE = {
    "town": 25,
    "airport": 40,
    "vip": 55,
    "school": 30,
    "tour": 80,
    "long_distance": 90,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _db_mode() -> str:
    if os.getenv("DATABASE_URL", "").strip():
        return "postgres"
    if os.getenv("SUPABASE_URL", "").strip() and any(os.getenv(name, "").strip() for name in SUPABASE_KEY_NAMES):
        return "supabase"
    return "json"


def _supabase_key() -> str | None:
    for name in SUPABASE_KEY_NAMES:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _supabase_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = _supabase_key()
    if not base_url or not key:
        raise RuntimeError("Supabase is not configured.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
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


def _pg_execute(query: str, values: tuple[Any, ...] = (), fetch: str = "all") -> Any:
    with closing(psycopg2.connect(os.getenv("DATABASE_URL", "").strip(), connect_timeout=5)) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, values)
            result = None
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            conn.commit()
            return result


def _json_rows(path: str) -> list[dict[str, Any]]:
    rows = load_json(path, [])
    return rows if isinstance(rows, list) else []


def _save_json_rows(path: str, rows: list[dict[str, Any]]) -> None:
    save_json(path, rows)


def _money(value: float) -> float:
    return round(float(value), 2)


def _quote_number() -> str:
    return f"QUO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _booking_number() -> str:
    return f"BKG-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _payment_reference() -> str:
    return f"PAY-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _invoice_number(document_type: str = "Invoice") -> str:
    prefix = "INV" if str(document_type).lower() == "invoice" else "QUO"
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


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


def _is_night_travel(travel_time: str | None) -> bool:
    if not travel_time:
        return False
    raw = str(travel_time).strip()
    try:
        hour = int(raw.split(":")[0])
    except (ValueError, IndexError):
        return False
    return hour >= 21 or hour < 5


def _airport_override(distance_data: dict[str, Any], vehicle_type: str) -> float | None:
    pickup_zone = distance_data.get("pickup_zone_data", {})
    dropoff_zone = distance_data.get("dropoff_zone_data", {})
    if pickup_zone.get("zone_type", "").startswith("airport") or dropoff_zone.get("zone_type", "").startswith("airport"):
        return float(AIRPORT_FIXED_GUIDE.get(vehicle_type, 0) or 0)
    return None


def _suggestions(dropoff: str, service_type: str) -> list[str]:
    place = normalise(dropoff)
    if "swakopmund" in place:
        return ["Walvis Bay", "Sandwich Harbour", "Dolphin cruise", "Beach hotels", "Return transfer"]
    if "etosha" in place:
        return ["Okaukuejo", "Namutoni", "Halali", "SUV/Quantum", "Dry season wildlife"]
    if "sossusvlei" in place:
        return ["Deadvlei", "Dune 45", "Sesriem", "Sunrise departure", "SUV/private shuttle"]
    if service_type == "airport":
        return ["Create booking", "Talk to support", "VIP airport option"]
    return ["Create booking", "Create quote", "Talk to support"]


def calculate_quote(payload: dict[str, Any]) -> dict[str, Any]:
    pickup = str(payload.get("pickup", "")).strip()
    dropoff = str(payload.get("dropoff", "")).strip()
    vehicle_type = str(payload.get("vehicle_type", "sedan")).strip().lower()
    if vehicle_type not in VEHICLE_RULES:
        vehicle_type = "sedan"
    if not pickup and dropoff:
        pickup = "Windhoek"
    if not dropoff and pickup:
        dropoff = "Hosea Kutako Airport" if "airport" in normalise(str(payload.get("service_type", ""))) else ""
    service_type = infer_service_type(pickup, dropoff, requested=payload.get("service_type"), vehicle_type=vehicle_type)
    passengers = max(1, int(payload.get("passengers") or 1))
    luggage_count = max(0, int(payload.get("luggage_count") or 0))
    waiting_minutes = max(0, int(payload.get("waiting_minutes") or 0))
    travel_time = str(payload.get("travel_time", "")).strip()

    distance_data = estimate_distance(pickup, dropoff)
    rules = VEHICLE_RULES[vehicle_type]
    base_fare = float(rules["base_fare"])
    distance_fee = float(distance_data["distance_km"]) * float(rules["per_km"])
    pickup_fee = float((distance_data.get("pickup_zone_data") or {}).get("pickup_fee") or 0)
    dropoff_fee = float((distance_data.get("dropoff_zone_data") or {}).get("dropoff_fee") or 0)
    zone_fee = pickup_fee + dropoff_fee
    vehicle_fee = base_fare * (float(rules["multiplier"]) - 1)
    waiting_fee = ((waiting_minutes + 9) // 10) * float(rules["waiting_per_10_min"]) if waiting_minutes else 0.0
    night_fee = float(rules["night_fee"]) if _is_night_travel(travel_time) else 0.0
    extra_luggage = max(0, luggage_count - 1)
    luggage_fee = extra_luggage * float(rules["luggage_fee"])

    airport_fee = 25.0 if service_type == "airport" else 0.0
    route_risk_fee = 0.0
    fuel_protection_fee = 0.0
    if service_type in {"tour", "long_distance"}:
        fuel_protection_fee = max(45.0, float(distance_data["distance_km"]) * 1.8)
    if any(term in normalise(dropoff) for term in ["sossusvlei", "etosha", "damaraland", "sandwich harbour"]):
        route_risk_fee += 60.0
    if service_type == "vip":
        route_risk_fee += 45.0
    if passengers > 4 and vehicle_type in {"sedan", "suv"}:
        route_risk_fee += 35.0
    service_fee = 20.0 + airport_fee + route_risk_fee + fuel_protection_fee

    subtotal = base_fare + distance_fee + zone_fee + vehicle_fee + waiting_fee + luggage_fee + night_fee + service_fee
    airport_override = _airport_override(distance_data, vehicle_type)
    if airport_override and service_type == "airport" and float(distance_data["distance_km"]) <= 60:
        base_fare = 0.0
        distance_fee = 0.0
        zone_fee = 0.0
        vehicle_fee = 0.0
        service_fee = 0.0
        subtotal = float(airport_override) + waiting_fee + luggage_fee + night_fee + route_risk_fee
    minimum_fare = float(rules["minimum_fare"])
    if airport_override:
        minimum_fare = max(minimum_fare, float(airport_override))
    if service_type in {"tour", "long_distance"}:
        minimum_fare = max(minimum_fare, 200.0)
    preliminary_price = max(subtotal, minimum_fare)

    payout_rate = PAYOUT_RATES[vehicle_type]
    commission_rate = COMMISSION_RATES[vehicle_type]
    minimum_profit = float(MIN_PROFIT_BY_SERVICE.get(service_type, 30.0))
    protected_price = preliminary_price
    while protected_price - (protected_price * payout_rate) - (protected_price * commission_rate) < minimum_profit:
        protected_price += 5.0

    if airport_override:
        protected_price = max(protected_price, float(airport_override))

    driver_payout = _money(protected_price * payout_rate)
    tarasi_commission = _money(protected_price * commission_rate)
    estimated_profit = _money(protected_price - driver_payout - tarasi_commission)
    final_price = _money(protected_price)
    price_confidence = distance_data["confidence"]

    notes = list(distance_data.get("notes", []))
    notes.append("Final confirmation depends on the exact street, waiting time, luggage, night travel and vehicle availability.")
    if airport_override:
        notes.append("Airport fixed pricing guidance applied for this route.")
    if service_type in {"tour", "long_distance"}:
        notes.append("Fuel protection is included for long-distance or tourism movement.")
    if night_fee:
        notes.append("Night surcharge applied based on travel time.")
    if route_risk_fee:
        notes.append("Route risk protection was added for VIP, gravel or tourism-style routing.")

    quote = {
        "quote_number": _quote_number(),
        "pickup_text": pickup,
        "dropoff_text": dropoff,
        "pickup_zone": distance_data["pickup_zone"],
        "dropoff_zone": distance_data["dropoff_zone"],
        "distance_km": _money(distance_data["distance_km"]),
        "duration_minutes": int(distance_data["duration_minutes"]),
        "vehicle_type": vehicle_type,
        "passengers": passengers,
        "luggage_count": luggage_count,
        "service_type": service_type,
        "base_fare": _money(base_fare),
        "distance_fee": _money(distance_fee),
        "zone_fee": _money(zone_fee),
        "vehicle_fee": _money(vehicle_fee),
        "waiting_fee": _money(waiting_fee),
        "luggage_fee": _money(luggage_fee),
        "night_fee": _money(night_fee),
        "service_fee": _money(service_fee),
        "subtotal": _money(subtotal),
        "driver_payout": driver_payout,
        "tarasi_commission": tarasi_commission,
        "estimated_profit": estimated_profit,
        "final_price": final_price,
        "price_confidence": price_confidence,
        "pricing_notes": " ".join(notes),
        "price_breakdown": {
            "base_fare": _money(base_fare),
            "distance_fee": _money(distance_fee),
            "zone_fee": _money(zone_fee),
            "vehicle_fee": _money(vehicle_fee),
            "waiting_fee": _money(waiting_fee),
            "luggage_fee": _money(luggage_fee),
            "night_fee": _money(night_fee),
            "service_fee": _money(service_fee),
            "minimum_fare_applied": final_price == _money(max(minimum_fare, final_price)),
        },
        "confidence": price_confidence,
        "notes": notes,
        "suggestions": _suggestions(dropoff, service_type),
    }
    return quote


def save_quote(quote: dict[str, Any], user_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    row = {
        "id": str(uuid.uuid4()),
        "quote_number": quote["quote_number"],
        "user_id": user_id,
        "session_id": session_id or "",
        "pickup_text": quote["pickup_text"],
        "dropoff_text": quote["dropoff_text"],
        "pickup_zone": quote["pickup_zone"],
        "dropoff_zone": quote["dropoff_zone"],
        "distance_km": quote["distance_km"],
        "duration_minutes": quote["duration_minutes"],
        "vehicle_type": quote["vehicle_type"],
        "passengers": quote["passengers"],
        "luggage_count": quote["luggage_count"],
        "service_type": quote["service_type"],
        "base_fare": quote["base_fare"],
        "distance_fee": quote["distance_fee"],
        "zone_fee": quote["zone_fee"],
        "waiting_fee": quote["waiting_fee"],
        "luggage_fee": quote["luggage_fee"],
        "night_fee": quote["night_fee"],
        "service_fee": quote["service_fee"],
        "subtotal": quote["subtotal"],
        "driver_payout": quote["driver_payout"],
        "tarasi_commission": quote["tarasi_commission"],
        "estimated_profit": quote["estimated_profit"],
        "final_price": quote["final_price"],
        "price_confidence": quote["confidence"],
        "pricing_notes": quote["pricing_notes"],
        "status": "quoted",
        "created_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_booking_quotes
                (id, quote_number, user_id, session_id, pickup_text, dropoff_text, pickup_zone, dropoff_zone, distance_km, duration_minutes, vehicle_type, passengers, luggage_count, service_type, base_fare, distance_fee, zone_fee, waiting_fee, luggage_fee, night_fee, service_fee, subtotal, driver_payout, tarasi_commission, estimated_profit, final_price, price_confidence, pricing_notes, status, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_booking_quotes",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows(QUOTE_FILE)
    rows.append(row)
    _save_json_rows(QUOTE_FILE, rows)
    return row


def list_quotes(limit: int = 100) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute("select * from tarasi_booking_quotes order by created_at desc limit %s", (limit,))
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_booking_quotes?{urlencode({'select': '*', 'order': 'created_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = _json_rows(QUOTE_FILE)
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_quote_by_number(quote_number: str) -> dict[str, Any] | None:
    if not quote_number:
        return None
    for row in list_quotes(limit=300):
        if row.get("quote_number") == quote_number:
            return row
    return None


def create_booking(payload: dict[str, Any], user_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    quote_number = str(payload.get("quote_number", "")).strip()
    quote = get_quote_by_number(quote_number)
    if not quote:
        quote = save_quote(calculate_quote(payload), user_id=user_id, session_id=session_id)
    booking = {
        "id": str(uuid.uuid4()),
        "booking_number": _booking_number(),
        "quote_id": quote.get("id"),
        "user_id": user_id,
        "session_id": session_id or "",
        "client_name": str(payload.get("client_name") or payload.get("full_name") or "Guest customer").strip(),
        "client_phone": str(payload.get("client_phone") or payload.get("phone") or "").strip(),
        "pickup_text": quote.get("pickup_text"),
        "dropoff_text": quote.get("dropoff_text"),
        "pickup_zone": quote.get("pickup_zone"),
        "dropoff_zone": quote.get("dropoff_zone"),
        "travel_date": payload.get("travel_date") or None,
        "travel_time": payload.get("travel_time") or None,
        "vehicle_type": quote.get("vehicle_type"),
        "passengers": quote.get("passengers"),
        "luggage_count": quote.get("luggage_count"),
        "service_type": quote.get("service_type"),
        "final_price": quote.get("final_price"),
        "driver_id": payload.get("driver_id"),
        "status": "pending",
        "payment_status": "unpaid",
        "proof_url": "",
        "invoice_number": "",
        "assigned_driver_id": None,
        "assigned_driver_name": "",
        "assigned_vehicle": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bookings
                (id, booking_number, quote_id, user_id, session_id, client_name, client_phone, pickup_text, dropoff_text, pickup_zone, dropoff_zone, travel_date, travel_time, vehicle_type, passengers, luggage_count, service_type, final_price, driver_id, status, payment_status, proof_url, invoice_number, assigned_driver_id, assigned_driver_name, assigned_vehicle, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(booking.values()),
                fetch="one",
            )
            booking_row = dict(result) if result else booking
        except Exception:
            booking_row = booking
    elif mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bookings",
                booking,
                extra_headers={"Prefer": "return=representation"},
            )
            booking_row = result[0] if isinstance(result, list) and result else booking
        except Exception:
            booking_row = booking
    else:
        rows = _json_rows(BOOKING_FILE)
        rows.append(booking)
        _save_json_rows(BOOKING_FILE, rows)
        booking_row = booking
    add_booking_status_history(booking_row.get("id"), "pending", "Booking created from pricing engine estimate.")
    return booking_row


def add_booking_status_history(booking_id: str | None, status: str, note: str) -> dict[str, Any]:
    row = {"id": str(uuid.uuid4()), "booking_id": booking_id, "status": status, "note": note, "created_at": _now()}
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                "insert into tarasi_booking_status_history (id, booking_id, status, note, created_at) values (%s, %s, %s, %s, %s) returning *",
                tuple(row.values()),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_booking_status_history",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows(STATUS_FILE)
    rows.append(row)
    _save_json_rows(STATUS_FILE, rows)
    return row


def list_bookings(limit: int = 100) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute("select * from tarasi_bookings order by updated_at desc limit %s", (limit,))
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bookings?{urlencode({'select': '*', 'order': 'updated_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = _json_rows(BOOKING_FILE)
    rows.sort(key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return rows[:limit]


def get_booking_by_number(booking_number: str) -> dict[str, Any] | None:
    if not booking_number:
        return None
    for row in list_bookings(limit=300):
        if row.get("booking_number") == booking_number:
            return row
    return None


def _update_booking_fields(booking_number: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    booking = get_booking_by_number(booking_number)
    if not booking:
        return None
    payload = {**payload, "updated_at": _now()}
    mode = _db_mode()
    updated_row = None
    if mode == "postgres":
        try:
            keys = list(payload.keys())
            set_sql = ", ".join(f"{key} = %s" for key in keys)
            result = _pg_execute(
                f"update tarasi_bookings set {set_sql} where booking_number = %s returning *",
                tuple(payload[key] for key in keys) + (booking_number,),
                fetch="one",
            )
            updated_row = dict(result) if result else None
        except Exception:
            updated_row = None
    elif mode == "supabase":
        try:
            result = _supabase_request(
                "PATCH",
                f"/rest/v1/tarasi_bookings?{urlencode({'booking_number': f'eq.{booking_number}'})}",
                payload,
                extra_headers={"Prefer": "return=representation"},
            )
            updated_row = result[0] if isinstance(result, list) and result else None
        except Exception:
            updated_row = None
    if updated_row is None:
        rows = _json_rows(BOOKING_FILE)
        for index, row in enumerate(rows):
            if row.get("booking_number") == booking_number:
                rows[index] = {**row, **payload}
                updated_row = rows[index]
                _save_json_rows(BOOKING_FILE, rows)
                break
    return updated_row


def update_booking_status(booking_number: str, status: str, note: str = "") -> dict[str, Any] | None:
    updated_row = _update_booking_fields(booking_number, {"status": status})
    if updated_row:
        add_booking_status_history(updated_row.get("id"), status, note or f"Status changed to {status}.")
    return updated_row


def list_payments(limit: int = 100) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute("select * from tarasi_booking_payments order by updated_at desc limit %s", (limit,))
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_booking_payments?{urlencode({'select': '*', 'order': 'updated_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
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
    proof_value = proof_url.strip() or f"TEXT:{proof_text.strip()}"
    row = {
        "id": str(uuid.uuid4()),
        "booking_id": booking.get("id"),
        "booking_number": booking_number,
        "payment_reference": _payment_reference(),
        "amount": booking.get("final_price") or 0,
        "payment_method": "bank_transfer",
        "proof_url": proof_value,
        "status": "pending",
        "admin_notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    mode = _db_mode()
    created = None
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_booking_payments
                (id, booking_id, booking_number, payment_reference, amount, payment_method, proof_url, status, admin_notes, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one",
            )
            created = dict(result) if result else None
        except Exception:
            created = None
    elif mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_booking_payments",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            created = result[0] if isinstance(result, list) and result else None
        except Exception:
            created = None
    if created is None:
        rows = _json_rows(PAYMENT_FILE)
        rows.append(row)
        _save_json_rows(PAYMENT_FILE, rows)
        created = row
    _update_booking_fields(booking_number, {"payment_status": "pending_verification", "proof_url": proof_value})
    add_booking_status_history(booking.get("id"), booking.get("status", "pending"), "Payment proof submitted for verification.")
    return created


def update_payment_status(booking_number: str, status: str, admin_notes: str = "") -> dict[str, Any] | None:
    payment = get_payment_by_booking_number(booking_number)
    if not payment:
        return None
    payload = {"status": status, "admin_notes": admin_notes, "updated_at": _now()}
    mode = _db_mode()
    updated = None
    if mode == "postgres":
        try:
            keys = list(payload.keys())
            set_sql = ", ".join(f"{key} = %s" for key in keys)
            result = _pg_execute(
                f"update tarasi_booking_payments set {set_sql} where payment_reference = %s returning *",
                tuple(payload[key] for key in keys) + (payment["payment_reference"],),
                fetch="one",
            )
            updated = dict(result) if result else None
        except Exception:
            updated = None
    elif mode == "supabase":
        try:
            payment_reference = payment["payment_reference"]
            result = _supabase_request(
                "PATCH",
                f"/rest/v1/tarasi_booking_payments?{urlencode({'payment_reference': f'eq.{payment_reference}'})}",
                payload,
                extra_headers={"Prefer": "return=representation"},
            )
            updated = result[0] if isinstance(result, list) and result else None
        except Exception:
            updated = None
    if updated is None:
        rows = _json_rows(PAYMENT_FILE)
        for index, row in enumerate(rows):
            if row.get("payment_reference") == payment.get("payment_reference"):
                rows[index] = {**row, **payload}
                updated = rows[index]
                _save_json_rows(PAYMENT_FILE, rows)
                break
    if updated:
        booking_status = "paid" if status == "approved" else ("payment_rejected" if status == "rejected" else "pending_verification")
        _update_booking_fields(booking_number, {"payment_status": booking_status})
    return updated


def list_invoices(limit: int = 100) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute("select * from tarasi_booking_invoices order by created_at desc limit %s", (limit,))
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_booking_invoices?{urlencode({'select': '*', 'order': 'created_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
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
    invoice_number = _invoice_number(document_type=document_type)
    invoice_url = f"{base_url.rstrip('/')}/booking/{booking_number}/invoice" if base_url else f"/booking/{booking_number}/invoice"
    row = {
        "id": str(uuid.uuid4()),
        "booking_id": booking.get("id"),
        "booking_number": booking_number,
        "invoice_number": invoice_number,
        "document_type": document_type,
        "client_name": booking.get("client_name") or "Tarasi customer",
        "client_phone": booking.get("client_phone") or "",
        "pickup_text": booking.get("pickup_text") or "",
        "dropoff_text": booking.get("dropoff_text") or "",
        "vehicle_type": booking.get("vehicle_type") or "",
        "service_type": booking.get("service_type") or "",
        "amount": booking.get("final_price") or 0,
        "payment_status": booking.get("payment_status") or "unpaid",
        "status": "issued",
        "qr_url": invoice_url,
        "created_at": _now(),
    }
    mode = _db_mode()
    created = None
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_booking_invoices
                (id, booking_id, booking_number, invoice_number, document_type, client_name, client_phone, pickup_text, dropoff_text, vehicle_type, service_type, amount, payment_status, status, qr_url, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one",
            )
            created = dict(result) if result else None
        except Exception:
            created = None
    elif mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_booking_invoices",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            created = result[0] if isinstance(result, list) and result else None
        except Exception:
            created = None
    if created is None:
        rows = _json_rows(INVOICE_FILE)
        rows.append(row)
        _save_json_rows(INVOICE_FILE, rows)
        created = row
    _update_booking_fields(booking_number, {"invoice_number": invoice_number})
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
    booking_zone = normalise(booking.get("pickup_zone") or booking.get("pickup_text") or "")
    vehicle_type = str(booking.get("vehicle_type") or "sedan").lower()
    candidates = []
    for driver in drivers:
        status = str(driver.get("status") or driver.get("availability") or "").lower()
        if status not in {"online", "available", "active", "assigned"}:
            continue
        if not _driver_matches_vehicle(driver, vehicle_type):
            continue
        zone_score = 1 if booking_zone and booking_zone in normalise(driver.get("based_area") or "") else 0
        rating = float(driver.get("rating") or 0) if str(driver.get("rating") or "").replace(".", "", 1).isdigit() else 0
        candidates.append((zone_score, rating, driver))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    driver = candidates[0][2]
    updated = _update_booking_fields(
        booking_number,
        {
            "assigned_driver_id": driver.get("id") or driver.get("driver_id"),
            "assigned_driver_name": driver.get("full_name") or driver.get("name") or "",
            "assigned_vehicle": driver.get("vehicle_name") or (driver.get("assigned_vehicle") or {}).get("name", ""),
            "status": "driver_assigned",
        },
    )
    if updated:
        add_booking_status_history(updated.get("id"), "driver_assigned", f"Assigned driver {updated.get('assigned_driver_name') or 'Tarasi Driver'}.")
    return updated


def get_bank_details() -> dict[str, str]:
    return dict(BANK_DETAILS)
