from __future__ import annotations

from datetime import datetime
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from services.auth_service import current_user, require_driver
from services.driver_dashboard_service import (
    get_driver_dashboard_context, 
    record_driver_event, 
    update_live_location
)
from services.driver_service import (
    update_driver_trip_status, 
    get_driver, 
    update_row as update_driver_row
)
from services.booking_service import update_booking_status

driver_bp = Blueprint("driver", __name__, url_prefix="/driver")

@driver_bp.route("/dashboard")
@require_driver
def dashboard():
    user = current_user()
    context = get_driver_dashboard_context(user["user_id"])
    if not context.get("available"):
        flash(context.get("error", "Access denied."))
        return redirect(url_for("public.index"))
    return render_template("driver/dashboard.html", **context)

@driver_bp.route("/trips")
@require_driver
def trips():
    user = current_user()
    context = get_driver_dashboard_context(user["user_id"])
    return render_template("driver/trips.html", **context)

@driver_bp.route("/status", methods=["POST"])
@require_driver
def update_status():
    user = current_user()
    status = request.form.get("status", "Offline")
    driver = get_driver(user["email"])
    if driver:
        update_driver_row("drivers", "driver_id", driver["driver_id"], {"status": status})
        flash(f"Status updated to {status}")
    return redirect(url_for("driver.dashboard"))

@driver_bp.route("/location/update", methods=["POST"])
@require_driver
def location_update():
    user = current_user()
    data = request.get_json() or {}
    
    lat = data.get("lat")
    lng = data.get("lng")
    speed = data.get("speed")
    booking_id = data.get("booking_id")
    
    driver = get_driver(user["email"])
    if driver and lat and lng:
        update_live_location(
            driver["driver_id"], 
            lat, lng, 
            speed=speed, 
            booking_id=booking_id
        )
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400

@driver_bp.route("/trips/<reference>/<action>", methods=["POST"])
@require_driver
def trip_action(reference: str, action: str):
    user = current_user()
    driver = get_driver(user["email"])
    if not driver:
        return jsonify({"ok": False, "error": "Driver not found"}), 404
        
    # Actions: accept, reject, start, arrived-pickup, picked-up, arrived-dropoff, complete
    ok = update_driver_trip_status(reference, driver, action)
    
    if ok:
        record_driver_event(driver["driver_id"], reference, action)
        flash(f"Trip status updated: {action.replace('-', ' ').title()}")
    else:
        flash("Failed to update trip status.")
        
    return redirect(url_for("driver.dashboard"))

@driver_bp.route("/trips/<reference>/navigate")
@require_driver
def navigate(reference: str):
    user = current_user()
    context = get_driver_dashboard_context(user["user_id"])
    # Find the specific trip
    trip = next((t for t in context.get("active_trips", []) if t["reference"] == reference), None)
    if not trip:
        flash("Trip not found.")
        return redirect(url_for("driver.dashboard"))
        
    return render_template("driver/navigation.html", trip=trip, driver=context["driver"])
