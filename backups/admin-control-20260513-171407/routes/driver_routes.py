from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.driver_service import current_driver_from_session, get_driver_trip, list_driver_trips, update_driver_trip_status


driver_bp = Blueprint("driver", __name__, url_prefix="/driver")


def _require_driver():
    driver = current_driver_from_session(session)
    if not driver:
        flash("Driver login is required.")
        return None
    return driver


@driver_bp.route("")
def dashboard():
    driver = _require_driver()
    if not driver:
        return redirect(url_for("driver_plus.driver_login"))
    trips = list_driver_trips(driver)
    assigned = [item for item in trips if str(item.get("status", "")).lower().replace(" ", "_") in {"driver_assigned", "on_the_way", "arrived", "picked_up"}]
    return render_template("driver/dashboard.html", driver=driver, bookings=trips, assigned=assigned)


@driver_bp.route("/trips")
def trips():
    driver = _require_driver()
    if not driver:
        return redirect(url_for("driver_plus.driver_login"))
    return render_template("driver/trips.html", driver=driver, bookings=list_driver_trips(driver))


@driver_bp.route("/trips/<reference>")
def trip_detail(reference: str):
    driver = _require_driver()
    if not driver:
        return redirect(url_for("driver_plus.driver_login"))
    booking = get_driver_trip(driver, reference)
    return render_template("driver/trip_detail.html", driver=driver, booking=booking, not_found=booking is None), (404 if booking is None else 200)


@driver_bp.route("/trips/<reference>/status", methods=["POST"])
def trip_status(reference: str):
    driver = _require_driver()
    if not driver:
        return redirect(url_for("driver_plus.driver_login"))
    status = request.form.get("status", "").strip()
    booking = update_driver_trip_status(reference, driver, status)
    flash(f"Trip {reference} updated." if booking else "Trip not found.")
    return redirect(url_for("driver.trip_detail", reference=reference))
