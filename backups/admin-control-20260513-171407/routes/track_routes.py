from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.booking_service import BOOKING_STATUSES, get_booking, list_bookings
from services.pricing_service import DEFAULT_MAP_CENTER, build_route_preview
from services.tarasi_pricing_engine import get_booking_by_number as get_pricing_booking_by_number


track_bp = Blueprint("track", __name__)


def _status_key(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _timeline_for_status(current_status: str) -> list[dict[str, str]]:
    current_key = _status_key(current_status)
    current_index = next((index for index, item in enumerate(BOOKING_STATUSES) if _status_key(item) == current_key), 0)
    timeline = []
    for index, label in enumerate(BOOKING_STATUSES):
        state = "pending"
        if index < current_index:
            state = "complete"
        elif index == current_index:
            state = "active"
        timeline.append({"label": label, "state": state})
    return timeline


def _driver_tracking_payload(booking: dict) -> dict:
    metadata = booking.get("metadata") if isinstance(booking.get("metadata"), dict) else {}
    driver_lat = metadata.get("driver_lat")
    driver_lng = metadata.get("driver_lng")
    preview = build_route_preview(booking.get("pickup", ""), booking.get("dropoff", ""))
    has_live_driver = driver_lat not in (None, "") and driver_lng not in (None, "")
    driver_marker = None
    if has_live_driver:
        try:
            driver_marker = {
                "label": metadata.get("driver_name") or "Assigned driver",
                "lat": float(driver_lat),
                "lng": float(driver_lng),
            }
        except (TypeError, ValueError):
            driver_marker = None
            has_live_driver = False
    if has_live_driver and driver_marker:
        points = list(preview["preview"].get("route_points") or [])
        points.append([driver_marker["lat"], driver_marker["lng"]])
        center = {"lat": driver_marker["lat"], "lng": driver_marker["lng"], "label": driver_marker["label"]}
        return {
            "mode": "live",
            "center": center,
            "pickup_marker": preview["preview"].get("pickup_marker"),
            "dropoff_marker": preview["preview"].get("dropoff_marker"),
            "driver_marker": driver_marker,
            "route_points": points,
            "eta": metadata.get("driver_eta") or "ETA pending",
            "message": "Driver location is available for this assigned trip.",
            "has_coordinates": bool(points),
        }
    return {
        "mode": "preview",
        "center": preview["preview"].get("center") or DEFAULT_MAP_CENTER,
        "pickup_marker": preview["preview"].get("pickup_marker"),
        "dropoff_marker": preview["preview"].get("dropoff_marker"),
        "driver_marker": None,
        "route_points": preview["preview"].get("route_points") or [],
        "eta": "",
        "message": "Live tracking starts when driver shares location.",
        "has_coordinates": bool(preview["preview"].get("route_points")),
    }


def _tracking_summary(booking: dict) -> dict:
    payload = _driver_tracking_payload(booking)
    return {
        "timeline": _timeline_for_status(booking.get("status", "")),
        "map_preview": payload,
        "driver_card": {
            "name": booking.get("driver_name") or "Awaiting dispatch",
            "phone": booking.get("driver_phone") or "",
            "vehicle": booking.get("vehicle_name") or "Vehicle pending",
            "last_location_at": booking.get("last_location_at") or "",
            "booking_pin": booking.get("booking_pin") or "",
        },
    }


def _pricing_booking_to_track_booking(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "reference": row.get("booking_number"),
        "full_name": row.get("client_name") or "Tarasi customer",
        "status": str(row.get("status") or "pending").replace("_", " ").title(),
        "pickup": row.get("pickup_text") or "",
        "dropoff": row.get("dropoff_text") or "",
        "pickup_location": row.get("pickup_text") or "",
        "dropoff_location": row.get("dropoff_text") or "",
        "route_summary": f"{row.get('pickup_text') or ''} -> {row.get('dropoff_text') or ''}",
        "preferred_vehicle": row.get("vehicle_type") or "",
        "car": row.get("vehicle_type") or "",
        "date": row.get("travel_date") or "",
        "time": row.get("travel_time") or "",
        "driver_name": row.get("assigned_driver_name") or "",
        "driver_phone": "",
        "vehicle_name": row.get("assigned_vehicle") or row.get("vehicle_type") or "",
        "last_location_at": "",
        "booking_pin": "",
        "payment_status": row.get("payment_status") or "unpaid",
        "invoice_number": row.get("invoice_number") or "",
        "proof_url": row.get("proof_url") or "",
        "metadata": {},
    }


@track_bp.route("/track", methods=["GET", "POST"])
def track_index():
    if request.method == "POST":
        reference = request.form.get("reference", "").strip()
        if not reference:
            flash("Enter a booking reference.")
            return redirect(url_for("track.track_index"))
        return redirect(url_for("track.track_detail", reference=reference))
    return render_template("track/index.html")


@track_bp.route("/track/<reference>")
def track_detail(reference: str):
    booking = get_booking(reference)
    if booking is None:
        booking = _pricing_booking_to_track_booking(get_pricing_booking_by_number(reference))
    tracking = _tracking_summary(booking) if booking else {"timeline": [], "map_preview": {"center": DEFAULT_MAP_CENTER, "route_points": []}}
    return render_template(
        "track/detail.html",
        booking=booking,
        reference=reference,
        statuses=BOOKING_STATUSES,
        tracking=tracking,
        not_found=booking is None,
    ), (404 if booking is None else 200)


@track_bp.route("/booking/track/<reference>")
def legacy_track(reference: str):
    return redirect(url_for("track.track_detail", reference=reference))


@track_bp.route("/booking/confirm/<int:index>")
def legacy_confirm(index: int):
    bookings = list_bookings()
    if 0 <= index < len(bookings):
        return redirect(url_for("booking.booking_confirmation", reference=bookings[index]["reference"]))
    flash("Booking not found.")
    return redirect(url_for("track.track_index"))
