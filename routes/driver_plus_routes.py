from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from services.storage_service import load_json, save_json

driver_plus_bp = Blueprint("driver_plus", __name__)

DOC_DIR = Path("uploads/driver_docs")

DOC_TYPES = [
    "Profile picture",
    "ID photo",
    "Driver licence front",
    "Driver licence back",
    "PDP / professional driving permit",
    "Vehicle front photo",
    "Vehicle back photo",
    "Vehicle inside photo",
    "Vehicle licence disc",
    "Roadworthy document",
    "Insurance document",
]

SERVICE_AREAS = [
    "Windhoek", "Katutura", "Khomasdal", "Windhoek West", "Airport Route",
    "Swakopmund", "Walvis Bay", "Rundu", "Oshakati", "Long distance",
    "School transport", "Tourism routes", "Corporate transport"
]



def driver_email():
    return session.get("driver_email")


def admin_driver_records():
    data = load_json("admin_driver_accounts.json", [])
    return data if isinstance(data, list) else []


def save_admin_driver_records(data):
    save_json("admin_driver_accounts.json", data)



def drivers():
    data = load_json("drivers_profiles.json", [])
    return data if isinstance(data, list) else []


def save_drivers(data):
    save_json("drivers_profiles.json", data)


def current_driver():
    email = driver_email()
    if not email:
        return None

    admin_record = next((d for d in admin_driver_records() if d.get("email") == email and d.get("role") == "driver"), None)
    if not admin_record:
        return None

    data = drivers()
    driver = next((d for d in data if d.get("email") == email), None)

    if driver:
        driver["admin_approved"] = admin_record.get("admin_approved", False)
        driver["verification_status"] = admin_record.get("verification_status", driver.get("verification_status", "Pending admin verification"))
        driver["assigned_radius_km"] = admin_record.get("assigned_radius_km", driver.get("assigned_radius_km", 0))
        driver["assigned_vehicle"] = admin_record.get("assigned_vehicle", driver.get("assigned_vehicle", {}))
        return driver

    driver = {
        "driver_id": admin_record.get("driver_id", f"DRV-{secrets.token_hex(3).upper()}"),
        "email": email,
        "full_name": admin_record.get("full_name", "Tarasi Driver"),
        "phone": admin_record.get("phone", ""),
        "based_area": admin_record.get("based_area", ""),
        "service_type": admin_record.get("service_type", "Waiting for admin allocation"),
        "availability": "Offline",
        "verification_status": admin_record.get("verification_status", "Created by admin - documents pending"),
        "admin_approved": admin_record.get("admin_approved", False),
        "assigned_radius_km": admin_record.get("assigned_radius_km", 0),
        "assigned_vehicle": admin_record.get("assigned_vehicle", {
            "name": "Not assigned by admin",
            "plate_number": "Pending",
            "colour": "Pending",
            "condition_status": "Pending admin physical verification",
            "vehicle_owner": "Pending",
        }),
        "documents": [],
        "balance": "N$0.00",
        "total_trips": 0,
        "completed_trips": 0,
        "cancelled_trips": 0,
        "rating": "New",
        "created_at": datetime.now().isoformat(),
    }
    data.append(driver)
    save_drivers(data)
    return driver


def require_driver():
    driver = current_driver()
    if not driver:
        flash("Driver access only. Please login with the driver email and temporary PIN issued by admin.")
        return None
    return driver


def save_current_driver(updated):
    data = drivers()
    for i, d in enumerate(data):
        if d.get("email") == updated.get("email"):
            data[i] = updated
            save_drivers(data)
            return
    data.append(updated)
    save_drivers(data)

def driver_trips(driver):
    all_trips = load_json("allocated_trips.json", [])
    if not isinstance(all_trips, list):
        all_trips = []

    matched = [
        t for t in all_trips
        if t.get("driver_email") == driver.get("email")
        or t.get("driver_id") == driver.get("driver_id")
        or t.get("driver_name") == driver.get("full_name")
    ]

    if not matched:
        matched = [
            {
                "reference": "TAR-DRIVER-DEMO",
                "customer_name": "Waiting for admin assignment",
                "customer_phone": "Hidden until assigned",
                "service_class": "Monthly pickup / live order",
                "pickup_zone": driver.get("based_area") or "Admin will allocate zone",
                "dropoff_zone": "Pending",
                "pickup_time": "Pending",
                "knockoff_time": "Pending",
                "status": "Waiting for orders",
                "activation_code": "Pending",
                "fare": "Pending",
                "driver_email": driver.get("email"),
            }
        ]

    return matched



@driver_plus_bp.route("/driver/login", methods=["GET", "POST"])
def driver_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pin = request.form.get("pin", "").strip()

        record = next(
            (
                d for d in admin_driver_records()
                if d.get("email", "").lower() == email
                and str(d.get("temporary_pin", "")).strip() == pin
                and d.get("role") == "driver"
            ),
            None,
        )

        if not record:
            flash("Invalid driver login. Use the email and temporary PIN from admin.")
            return redirect(url_for("driver_plus.driver_login"))

        session.clear()
        session["driver_email"] = record["email"]
        session["driver_name"] = record.get("full_name", "Tarasi Driver")
        session["account_role"] = "driver"
        flash("Driver login successful.")
        return redirect(url_for("driver_plus.command"))

    return render_template("driver/login.html")


@driver_plus_bp.route("/driver/logout")
def driver_logout():
    session.clear()
    flash("Driver logged out.")
    return redirect(url_for("driver_plus.driver_login"))


@driver_plus_bp.route("/admin/drivers/create", methods=["GET", "POST"])
def admin_create_driver():
    if request.method == "POST":
        data = admin_driver_records()
        email = request.form.get("email", "").strip().lower()
        pin = request.form.get("temporary_pin", "").strip() or str(secrets.randbelow(900000) + 100000)

        if any(d.get("email") == email for d in data):
            flash("Driver email already exists.")
            return redirect(url_for("driver_plus.admin_create_driver"))

        data.append({
            "driver_id": f"DRV-{secrets.token_hex(3).upper()}",
            "role": "driver",
            "email": email,
            "temporary_pin": pin,
            "full_name": request.form.get("full_name", ""),
            "phone": request.form.get("phone", ""),
            "based_area": request.form.get("based_area", ""),
            "service_type": request.form.get("service_type", "Monthly pickups"),
            "admin_approved": False,
            "verification_status": "Created by admin - waiting for documents",
            "assigned_radius_km": int(request.form.get("assigned_radius_km") or 0),
            "assigned_vehicle": {
                "name": request.form.get("vehicle_name", "Not assigned"),
                "plate_number": request.form.get("plate_number", "Pending"),
                "colour": request.form.get("colour", "Pending"),
                "condition_status": "Pending physical verification",
                "vehicle_owner": request.form.get("vehicle_owner", "Company / Partner"),
            },
            "created_at": datetime.now().isoformat(),
        })
        save_admin_driver_records(data)
        flash(f"Driver created. Temporary PIN: {pin}")
        return redirect(url_for("driver_plus.admin_create_driver"))

    return render_template("driver/admin_create_driver.html", service_areas=SERVICE_AREAS)


@driver_plus_bp.route("/driver/command")
def command():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))
    trips = driver_trips(driver)
    active = next((t for t in trips if t.get("status") in ["Assigned", "On the way", "Arrived", "Picked up"]), trips[0])
    return render_template("driver/command.html", driver=driver, trips=trips, active_trip=active)


@driver_plus_bp.route("/driver/profile", methods=["GET", "POST"])
def profile():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))

    if request.method == "POST":
        driver["full_name"] = request.form.get("full_name", driver.get("full_name"))
        driver["phone"] = request.form.get("phone", driver.get("phone"))
        driver["based_area"] = request.form.get("based_area", driver.get("based_area"))
        driver["service_type"] = request.form.get("service_type", driver.get("service_type"))
        driver["verification_status"] = "Submitted for admin review"
        save_current_driver(driver)
        flash("Driver profile submitted. Admin must verify before full activation.")
        return redirect(url_for("driver_plus.command"))

    return render_template("driver/profile.html", driver=driver, service_areas=SERVICE_AREAS)


@driver_plus_bp.route("/driver/documents", methods=["GET", "POST"])
def documents():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))

    if request.method == "POST":
        doc_type = request.form.get("doc_type", "Document")
        file = request.files.get("document")

        if file and file.filename:
            DOC_DIR.mkdir(parents=True, exist_ok=True)
            filename = secure_filename(f"{driver['driver_id']}_{doc_type}_{file.filename}")
            file.save(DOC_DIR / filename)

            docs = driver.get("documents", [])
            docs.append({
                "type": doc_type,
                "filename": filename,
                "path": f"/uploads/driver_docs/{filename}",
                "status": "Pending admin verification",
                "uploaded_at": datetime.now().isoformat(),
            })
            driver["documents"] = docs
            driver["verification_status"] = "Documents pending admin review"
            save_current_driver(driver)
            flash("Document uploaded. Admin must verify it.")
        return redirect(url_for("driver_plus.documents"))

    return render_template("driver/documents.html", driver=driver, doc_types=DOC_TYPES)


@driver_plus_bp.route("/driver/availability", methods=["POST"])
def availability():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))
    driver["availability"] = request.form.get("availability", "Offline")
    driver["last_availability_update"] = datetime.now().isoformat()
    save_current_driver(driver)
    flash(f"Availability changed to {driver['availability']}.")
    return redirect(url_for("driver_plus.command"))


@driver_plus_bp.route("/driver/activate-trip", methods=["POST"])
def activate_trip():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))
    code = request.form.get("activation_code", "").strip().upper()
    reference = request.form.get("reference", "").strip()

    trips = load_json("allocated_trips.json", [])
    if not isinstance(trips, list):
        trips = []

    activated = False
    for trip in trips:
        trip_code = str(trip.get("activation_code") or trip.get("pickup_code") or "").upper()
        if trip.get("reference") == reference and trip_code == code:
            trip["status"] = "Picked up"
            trip["activated_at"] = datetime.now().isoformat()
            trip["driver_email"] = driver.get("email")
            activated = True

    if activated:
        save_json("allocated_trips.json", trips)
        driver["total_trips"] = int(driver.get("total_trips", 0)) + 1
        save_current_driver(driver)
        flash("Trip activated. Pickup time recorded.")
    else:
        flash("Wrong code or trip not found. Ask customer for the correct code.")

    return redirect(url_for("driver_plus.command"))


@driver_plus_bp.route("/driver/trip-status", methods=["POST"])
def trip_status():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))
    reference = request.form.get("reference")
    status = request.form.get("status")

    trips = load_json("allocated_trips.json", [])
    if not isinstance(trips, list):
        trips = []

    found = False
    for trip in trips:
        if trip.get("reference") == reference:
            trip["status"] = status
            trip["updated_at"] = datetime.now().isoformat()
            trip["driver_email"] = driver.get("email")
            found = True

    if found:
        save_json("allocated_trips.json", trips)
        flash("Trip status updated.")
    else:
        flash("Trip not found in allocated trips.")

    return redirect(url_for("driver_plus.command"))


@driver_plus_bp.route("/driver/wallet")
def wallet():
    driver = require_driver()
    if not driver:
        return redirect(url_for('driver_plus.driver_login'))
    trips = driver_trips(driver)
    return render_template("driver/wallet.html", driver=driver, trips=trips)
