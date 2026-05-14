from __future__ import annotations

import logging
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.booking_service import (
    BOOKING_STATUSES,
    BOOKING_TYPE_FIELDS,
    BOOKING_TYPE_META,
    COMMON_BOOKING_FIELDS,
    create_booking,
    get_booking,
)
from services.pricing_service import (
    DEFAULT_MAP_CENTER,
    build_booking_route_suggestions,
    build_route_preview,
    get_namibia_towns,
    get_popular_routes,
    list_cars,
    list_routes,
)
from services.profile_service import get_saved_profile
from services.tarasi_pricing_engine import calculate_customer_quote, get_bank_details, get_booking_by_number as get_pricing_booking_by_number, get_invoice_by_booking_number


booking_bp = Blueprint("booking", __name__)
logger = logging.getLogger(__name__)


def form_fields_for(booking_type: str, cars: list[dict] | None = None):
    cars = cars if cars is not None else list_cars()
    vehicle_names = [car["name"] for car in cars]
    fields = []
    for field in COMMON_BOOKING_FIELDS:
        field_copy = dict(field)
        if field_copy["name"] == "preferred_vehicle":
            field_copy["options"] = vehicle_names
        fields.append(field_copy)
    fields.extend(BOOKING_TYPE_FIELDS.get(booking_type, []))
    return fields


def build_booking_payload(booking_type: str, routes: list[dict] | None = None):
    routes = routes if routes is not None else list_routes()
    payload = {
        "booking_type": booking_type,
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": request.form.get("email", "").strip(),
        "pickup_location": request.form.get("pickup_location", "").strip(),
        "dropoff_location": request.form.get("dropoff_location", "").strip(),
        "pickup": request.form.get("pickup_location", "").strip(),
        "dropoff": request.form.get("dropoff_location", "").strip(),
        "date": request.form.get("date", ""),
        "time": request.form.get("time", ""),
        "passengers": request.form.get("passengers", "1"),
        "luggage": request.form.get("luggage", ""),
        "preferred_vehicle": request.form.get("preferred_vehicle", ""),
        "car": request.form.get("preferred_vehicle", ""),
        "notes": request.form.get("notes", ""),
        "special_fields": {},
    }
    if session.get("user"):
        payload["account_email"] = session["user"].get("email")
        payload["account_type"] = session["user"].get("account_type")
    for field in BOOKING_TYPE_FIELDS.get(booking_type, []):
        value = request.form.get(field["name"], "")
        payload[field["name"]] = value
        payload["special_fields"][field["name"]] = value
    quote = calculate_customer_quote(
        {
            "pickup_text": payload["pickup"],
            "dropoff_text": payload["dropoff"],
            "vehicle_type": payload["preferred_vehicle"] or "sedan",
            "service_type": booking_type,
            "passengers": payload["passengers"],
            "luggage_count": 0,
            "pickup_time": payload["time"],
        }
    )
    payload["amount"] = quote["final_price"] if quote.get("final_price") else "Quote required"
    payload["metadata"] = {
        **payload.get("metadata", {}),
        "pricing_quote": quote,
        "pickup_zone": quote.get("pickup_zone"),
        "dropoff_zone": quote.get("dropoff_zone"),
    }
    return payload


def _booking_map_saved_places() -> list[dict]:
    user = session.get("user") or {}
    if not user.get("email"):
        return []
    profile = get_saved_profile({"user_email": user.get("email"), "full_name": user.get("full_name", "")})
    saved_places = []
    if profile.get("town"):
        saved_places.append({"label": "Home", "address": profile["town"]})
    saved_places.append({"label": "Airport", "address": "Hosea Kutako Airport"})
    if profile.get("region"):
        saved_places.append({"label": "Region", "address": profile["region"]})
    return saved_places


def validate_booking(booking_type: str, cars: list[dict] | None = None):
    missing = []
    for field in form_fields_for(booking_type, cars=cars):
        if field.get("required") and not request.form.get(field["name"]):
            missing.append(field["label"])
    return missing


@booking_bp.route("/book")
def book_index():
    start = time.perf_counter()
    routes = list_routes()[:6]
    cars = list_cars()[:6]
    response = render_template("book/index.html", booking_types=BOOKING_TYPE_META, routes=routes, cars=cars)
    logger.debug("booking.book_index render_time_ms=%.2f", (time.perf_counter() - start) * 1000)
    return response


@booking_bp.route("/book/<booking_type>", methods=["GET", "POST"])
def book_form(booking_type: str):
    booking_meta = BOOKING_TYPE_META.get(booking_type)
    if not booking_meta:
        flash("Booking type not found.")
        return redirect(url_for("booking.book_index"))
    routes = list_routes()
    cars = list_cars()
    if request.method == "POST":
        submit_start = time.perf_counter()
        missing = validate_booking(booking_type, cars=cars)
        if missing:
            flash("Please complete all required booking fields.")
            return redirect(url_for("booking.book_form", booking_type=booking_type))
        booking = create_booking(build_booking_payload(booking_type, routes=routes))
        logger.debug("booking.book_form submit_time_ms=%.2f booking_type=%s reference=%s", (time.perf_counter() - submit_start) * 1000, booking_type, booking["reference"])
        flash(f"Booking {booking['reference']} submitted.")
        return redirect(url_for("booking.booking_confirmation", reference=booking["reference"]))
    start = time.perf_counter()
    route_suggestions = build_booking_route_suggestions(booking_type, routes=routes)
    response = render_template(
        "book/form.html",
        booking_type=booking_type,
        booking_meta=booking_meta,
        form_fields=form_fields_for(booking_type, cars=cars),
        routes=route_suggestions,
        all_routes=routes,
        cars=cars[:6],
        map_center=DEFAULT_MAP_CENTER,
        namibia_towns=get_namibia_towns(),
        popular_routes=get_popular_routes(),
        saved_places=_booking_map_saved_places(),
        initial_route_preview=build_route_preview("", "", routes=routes),
        prefill=request.args,
    )
    logger.debug("booking.book_form render_time_ms=%.2f booking_type=%s", (time.perf_counter() - start) * 1000, booking_type)
    return response


@booking_bp.route("/booking/confirmation/<reference>")
def booking_confirmation(reference: str):
    booking = get_booking(reference)
    return render_template("book/confirmation.html", booking=booking, statuses=BOOKING_STATUSES, not_found=booking is None), (404 if booking is None else 200)

@booking_bp.route("/booking/<reference>/payment", methods=["GET", "POST"])
def booking_payment(reference: str):
    booking = get_booking(reference)
    if not booking:
        flash("Booking not found.")
        return redirect(url_for("public.home"))

    if request.method == "POST":
        method = request.form.get("payment_method")
        # Handle proof upload for EFT
        proof_file = request.files.get("proof_of_payment")
        proof_path = ""
        if proof_file and proof_file.filename:
            # Basic validation
            ext = proof_file.filename.rsplit(".", 1)[1].lower() if "." in proof_file.filename else ""
            if ext in ["png", "jpg", "jpeg", "pdf"]:
                from werkzeug.utils import secure_filename
                import os
                filename = secure_filename(f"POP_{reference}_{int(time.time())}.{ext}")
                os.makedirs("uploads/payments", exist_ok=True)
                proof_path = os.path.join("uploads/payments", filename)
                proof_file.save(proof_path)
        
        updates = {
            "payment_method": method,
            "payment_status": "Pending" if method == "EFT / Bank transfer" else booking.get("payment_status", "Unpaid"),
            "proof_of_payment": proof_path if proof_path else booking.get("proof_of_payment", "")
        }
        from services.booking_service import update_booking_payment
        update_booking_payment(reference, updates)
        flash("Payment information updated.")
        return redirect(url_for("booking.booking_payment", reference=reference))

    return render_template("book/payment.html", booking=booking)

@booking_bp.route("/booking/<reference>/invoice")
def booking_invoice(reference: str):
    booking = get_booking(reference)
    if not booking:
        pricing_booking = get_pricing_booking_by_number(reference)
        invoice = get_invoice_by_booking_number(reference)
        if pricing_booking:
            return render_template(
                "book/booking_invoice.html",
                booking=pricing_booking,
                invoice=invoice,
                bank_details=get_bank_details(),
            )
    if not booking:
        return "Invoice not found", 404
    return render_template("book/invoice.html", booking=booking)

@booking_bp.route("/booking/<reference>/receipt")
def booking_receipt(reference: str):
    booking = get_booking(reference)
    if not booking or booking.get("payment_status") != "Paid":
        return "Receipt not available yet. Payment must be confirmed first.", 403
    return render_template("book/receipt.html", booking=booking)
