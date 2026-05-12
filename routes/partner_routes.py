from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.storage_service import load_json, save_json

partner_bp = Blueprint("partner", __name__)

AREAS = [
    "Windhoek", "Katutura", "Khomasdal", "Airport Route", "Swakopmund",
    "Walvis Bay", "Rundu", "Oshakati", "School Routes", "Corporate Routes",
    "Tourism Routes", "Long Distance"
]


def _load(name):
    data = load_json(name, [])
    return data if isinstance(data, list) else []


def _partner_email():
    return session.get("partner_email")


def _partners():
    return _load("partner_companies.json")


def _save_partners(data):
    save_json("partner_companies.json", data)


def _current_partner():
    email = _partner_email()
    if not email:
        return None
    return next((p for p in _partners() if p.get("email") == email), None)


def _require_partner():
    partner = _current_partner()
    if not partner:
        flash("Partner company access only. Login with your partner account.")
        return None
    return partner


def _partner_rows(filename, partner_id):
    return [row for row in _load(filename) if row.get("partner_id") == partner_id]


def _append_row(filename, row):
    data = _load(filename)
    data.append(row)
    save_json(filename, data)


@partner_bp.route("/partners/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = _partners()
        email = request.form.get("email", "").strip().lower()

        if any(p.get("email") == email for p in data):
            flash("Partner email already registered. Please login.")
            return redirect(url_for("partner.login"))

        partner = {
            "partner_id": f"PAR-{secrets.token_hex(3).upper()}",
            "company_name": request.form.get("company_name", ""),
            "email": email,
            "phone": request.form.get("phone", ""),
            "town": request.form.get("town", ""),
            "service_area": request.form.get("service_area", ""),
            "temporary_pin": request.form.get("temporary_pin", "") or str(secrets.randbelow(900000) + 100000),
            "status": "Pending Tarasi approval",
            "created_at": datetime.now().isoformat(),
            "role": "partner_company",
        }
        data.append(partner)
        _save_partners(data)

        flash(f"Partner application created. Temporary PIN: {partner['temporary_pin']}")
        return redirect(url_for("partner.login"))

    return render_template("partners/register.html", areas=AREAS)


@partner_bp.route("/partners/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pin = request.form.get("pin", "").strip()

        partner = next(
            (p for p in _partners() if p.get("email") == email and str(p.get("temporary_pin")) == pin),
            None,
        )

        if not partner:
            flash("Invalid partner login.")
            return redirect(url_for("partner.login"))

        session.clear()
        session["partner_email"] = partner["email"]
        session["partner_id"] = partner["partner_id"]
        session["partner_name"] = partner["company_name"]
        session["account_role"] = "partner"
        flash("Partner login successful.")
        return redirect(url_for("partner.dashboard"))

    return render_template("partners/login.html")


@partner_bp.route("/partners/logout")
def logout():
    session.clear()
    flash("Partner logged out.")
    return redirect(url_for("partner.login"))


@partner_bp.route("/partners")
@partner_bp.route("/partners/dashboard")
def dashboard():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    partner_id = partner["partner_id"]
    fleet = _partner_rows("partner_fleet.json", partner_id)
    drivers = _partner_rows("partner_drivers.json", partner_id)
    staff = _partner_rows("partner_staff.json", partner_id)
    bookings = _partner_rows("partner_bookings.json", partner_id)

    metrics = {
        "fleet_count": len(fleet),
        "drivers_count": len(drivers),
        "staff_count": len(staff),
        "bookings_count": len(bookings),
        "pending_bookings": len([b for b in bookings if b.get("status") in ["Pending", "Assigned", "New"]]),
        "revenue_estimate": sum(float(str(b.get("amount", 0)).replace("N$", "").replace(",", "") or 0) for b in bookings if str(b.get("amount", "0")).replace("N$", "").replace(",", "").isdigit()),
    }

    return render_template(
        "partners/dashboard.html",
        partner=partner,
        fleet=fleet[:6],
        drivers=drivers[:6],
        staff=staff[:6],
        bookings=bookings[:8],
        metrics=metrics,
    )


@partner_bp.route("/partners/fleet", methods=["GET", "POST"])
def fleet():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    if request.method == "POST":
        _append_row("partner_fleet.json", {
            "vehicle_id": f"PV-{secrets.token_hex(3).upper()}",
            "partner_id": partner["partner_id"],
            "company_name": partner["company_name"],
            "vehicle_name": request.form.get("vehicle_name", ""),
            "plate_number": request.form.get("plate_number", ""),
            "colour": request.form.get("colour", ""),
            "seats": request.form.get("seats", ""),
            "vehicle_type": request.form.get("vehicle_type", ""),
            "condition_status": "Pending Tarasi physical verification",
            "admin_verified": False,
            "created_at": datetime.now().isoformat(),
        })
        flash("Fleet vehicle added. Tarasi admin must verify condition before dispatch.")
        return redirect(url_for("partner.fleet"))

    return render_template("partners/fleet.html", partner=partner, fleet=_partner_rows("partner_fleet.json", partner["partner_id"]))


@partner_bp.route("/partners/drivers", methods=["GET", "POST"])
def drivers():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    fleet = _partner_rows("partner_fleet.json", partner["partner_id"])

    if request.method == "POST":
        pin = request.form.get("temporary_pin", "") or str(secrets.randbelow(900000) + 100000)
        _append_row("partner_drivers.json", {
            "driver_id": f"PDRV-{secrets.token_hex(3).upper()}",
            "partner_id": partner["partner_id"],
            "company_name": partner["company_name"],
            "full_name": request.form.get("full_name", ""),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", ""),
            "temporary_pin": pin,
            "assigned_vehicle_id": request.form.get("assigned_vehicle_id", ""),
            "based_area": request.form.get("based_area", ""),
            "verification_status": "Pending Tarasi review",
            "created_at": datetime.now().isoformat(),
        })
        flash(f"Partner driver created. Temporary PIN: {pin}")
        return redirect(url_for("partner.drivers"))

    return render_template("partners/drivers.html", partner=partner, drivers=_partner_rows("partner_drivers.json", partner["partner_id"]), fleet=fleet, areas=AREAS)


@partner_bp.route("/partners/staff", methods=["GET", "POST"])
def staff():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    if request.method == "POST":
        pin = request.form.get("temporary_pin", "") or str(secrets.randbelow(900000) + 100000)
        _append_row("partner_staff.json", {
            "staff_id": f"PST-{secrets.token_hex(3).upper()}",
            "partner_id": partner["partner_id"],
            "company_name": partner["company_name"],
            "full_name": request.form.get("full_name", ""),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", ""),
            "role": request.form.get("role", "Support staff"),
            "temporary_pin": pin,
            "status": "Active",
            "created_at": datetime.now().isoformat(),
        })
        flash(f"Staff account created. Temporary PIN: {pin}")
        return redirect(url_for("partner.staff"))

    return render_template("partners/staff.html", partner=partner, staff=_partner_rows("partner_staff.json", partner["partner_id"]))


@partner_bp.route("/partners/bookings", methods=["GET", "POST"])
def bookings():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    fleet = _partner_rows("partner_fleet.json", partner["partner_id"])
    drivers = _partner_rows("partner_drivers.json", partner["partner_id"])

    if request.method == "POST":
        _append_row("partner_bookings.json", {
            "booking_id": f"PB-{secrets.token_hex(4).upper()}",
            "partner_id": partner["partner_id"],
            "company_name": partner["company_name"],
            "customer_name": request.form.get("customer_name", ""),
            "customer_phone": request.form.get("customer_phone", ""),
            "pickup": request.form.get("pickup", ""),
            "dropoff": request.form.get("dropoff", ""),
            "date": request.form.get("date", ""),
            "time": request.form.get("time", ""),
            "service_type": request.form.get("service_type", ""),
            "assigned_driver_id": request.form.get("assigned_driver_id", ""),
            "assigned_vehicle_id": request.form.get("assigned_vehicle_id", ""),
            "amount": request.form.get("amount", "0"),
            "status": "New",
            "created_at": datetime.now().isoformat(),
        })
        flash("Partner booking created.")
        return redirect(url_for("partner.bookings"))

    return render_template(
        "partners/bookings.html",
        partner=partner,
        bookings=_partner_rows("partner_bookings.json", partner["partner_id"]),
        fleet=fleet,
        drivers=drivers,
    )


@partner_bp.route("/partners/reports")
def reports():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    bookings = _partner_rows("partner_bookings.json", partner["partner_id"])
    drivers = _partner_rows("partner_drivers.json", partner["partner_id"])
    fleet = _partner_rows("partner_fleet.json", partner["partner_id"])

    report = {
        "daily_bookings": len(bookings),
        "weekly_bookings": len(bookings),
        "monthly_bookings": len(bookings),
        "drivers": len(drivers),
        "fleet": len(fleet),
        "revenue": sum(float(str(b.get("amount", 0)).replace("N$", "").replace(",", "") or 0) for b in bookings if str(b.get("amount", "0")).replace("N$", "").replace(",", "").isdigit()),
    }

    return render_template("partners/reports.html", partner=partner, report=report, bookings=bookings)


@partner_bp.route("/partners/statement")
def statement():
    partner = _require_partner()
    if not partner:
        return redirect(url_for("partner.login"))

    bookings = _partner_rows("partner_bookings.json", partner["partner_id"])
    return render_template("partners/statement.html", partner=partner, bookings=bookings)
