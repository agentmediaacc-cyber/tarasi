from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for

from services.admin_service import (
    add_booking_note,
    assign_booking_driver,
    get_admin_shell,
    get_audit_context,
    get_booking_detail_context,
    get_bookings_context,
    get_content_context,
    get_customers_context,
    get_dashboard_context,
    get_drivers_context,
    get_fleet_context,
    get_payments_context,
    get_reports_context,
    get_routes_context,
    get_support_context,
    get_system_health_context,
    get_tours_context,
    update_customer_block,
    update_driver_action,
    update_support_ticket,
)
from services.booking_service import BOOKING_STATUSES, update_booking_metadata, update_booking_status


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _render_admin(template_name: str, active_section: str, **context):
    context["admin_shell"] = get_admin_shell(active_section)
    return render_template(template_name, **context)


@admin_bp.route("")
def dashboard():
    return _render_admin("admin/dashboard.html", "dashboard", **get_dashboard_context())


@admin_bp.route("/bookings")
def bookings():
    status_filter = request.args.get("status", "all")
    return _render_admin("admin/bookings.html", "bookings", **get_bookings_context(status_filter=status_filter))


@admin_bp.route("/bookings/<reference>")
def booking_detail(reference: str):
    context = get_booking_detail_context(reference)
    booking = context.get("booking")
    return _render_admin("admin/booking_detail.html", "bookings", not_found=booking is None, **context), (404 if booking is None else 200)


@admin_bp.route("/bookings/<reference>/status", methods=["POST"])
def update_status(reference: str):
    status = request.form.get("status", "").strip()
    if status not in BOOKING_STATUSES:
        flash("Invalid booking status.")
        return redirect(url_for("admin.booking_detail", reference=reference))
    booking = update_booking_status(reference, status)
    flash(f"Booking {reference} updated." if booking else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/assign-driver", methods=["GET", "POST"])
def assign_driver(reference: str):
    if request.method == "GET":
        return booking_detail(reference)
    driver_identifier = request.form.get("driver_id", "").strip()
    ok = assign_booking_driver(reference, driver_identifier)
    flash("Driver assigned to booking." if ok else "Driver assignment is unavailable or the selected driver was not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/note", methods=["POST"])
def add_note(reference: str):
    note = request.form.get("note", "").strip()
    ok = add_booking_note(reference, note)
    flash("Admin note saved." if ok else "Admin note could not be saved.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/approve-cancellation", methods=["POST"])
def approve_cancellation(reference: str):
    booking = update_booking_metadata(reference, {"cancelled_at": datetime.now().isoformat(timespec="seconds")}, status="Cancelled")
    flash(f"Cancellation approved for {reference}." if booking else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/reject-cancellation", methods=["POST"])
def reject_cancellation(reference: str):
    context = get_booking_detail_context(reference)
    booking = context.get("booking") or {}
    previous_status = booking.get("raw", {}).get("metadata", {}).get("previous_status") or booking.get("status") or "Confirmed"
    updated = update_booking_metadata(
        reference,
        {
            "cancellation_rejected_at": datetime.now().isoformat(timespec="seconds"),
            "cancel_request_note": "",
        },
        status=previous_status,
    )
    flash(f"Cancellation rejected for {reference}." if updated else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/drivers", methods=["GET", "POST"])
def drivers():
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        driver_id = request.form.get("driver_id", "").strip()
        if action == "create":
            payload = {
                "driver_id": request.form.get("new_driver_id", "").strip(),
                "full_name": request.form.get("full_name", "").strip(),
                "email": request.form.get("email", "").strip(),
                "phone": request.form.get("phone", "").strip(),
                "based_area": request.form.get("based_area", "").strip(),
                "service_type": request.form.get("service_type", "").strip(),
                "verification_status": "Created by admin",
                "admin_approved": False,
            }
            ok = update_driver_action("", "create", payload=payload)
            flash("Driver created." if ok else "Driver creation is unavailable without real database access.")
        elif action in {"approve", "suspend"}:
            ok = update_driver_action(driver_id, action)
            flash(f"Driver {action}d." if ok else "Driver action could not be completed.")
        elif action == "assign_vehicle":
            vehicle_name = request.form.get("vehicle_name", "").strip()
            assigned_vehicle = {"name": vehicle_name} if vehicle_name else {}
            ok = update_driver_action(driver_id, action, payload={"assigned_vehicle": assigned_vehicle})
            flash("Vehicle assigned." if ok else "Vehicle assignment could not be completed.")
        return redirect(url_for("admin.drivers"))
    return _render_admin("admin/drivers.html", "drivers", **get_drivers_context())


@admin_bp.route("/users")
@admin_bp.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        action = request.form.get("action", "").strip()
        ok = update_customer_block(email, blocked=(action == "block"))
        flash("Customer updated." if ok else "Customer action could not be completed.")
        return redirect(url_for("admin.customers"))
    return _render_admin("admin/customers.html", "customers", **get_customers_context())


@admin_bp.route("/fleet")
def fleet():
    return _render_admin("admin/fleet.html", "fleet", **get_fleet_context())


@admin_bp.route("/routes")
def routes_catalog():
    return _render_admin("admin/routes.html", "routes", **get_routes_context())


@admin_bp.route("/tours")
def tours():
    return _render_admin("admin/tours.html", "tours", **get_tours_context())


@admin_bp.route("/support", methods=["GET", "POST"])
def support():
    if request.method == "POST":
        reference = request.form.get("reference", "").strip()
        payload = {
            "status": request.form.get("status", "").strip(),
            "assigned_to": request.form.get("assigned_to", "").strip(),
        }
        payload = {key: value for key, value in payload.items() if value}
        ok = update_support_ticket(reference, payload)
        flash("Ticket updated." if ok else "Support ticket update could not be completed.")
        return redirect(url_for("admin.support"))
    return _render_admin("admin/support.html", "support", **get_support_context())


@admin_bp.route("/payments")
def payments():
    context = get_payments_context()
    if request.args.get("format") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["reference", "customer", "method", "description", "amount", "status", "created_at"])
        for row in context["payments"]:
            writer.writerow([row["reference"], row["customer"], row["method"], row["description"], row["amount"], row["status"], row["created_at"]])
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=tarasi-payments.csv"
        return response
    return _render_admin("admin/payments.html", "payments", **context)


@admin_bp.route("/reports")
def reports():
    return _render_admin("admin/reports.html", "reports", **get_reports_context())


@admin_bp.route("/system-health")
def system_health():
    return _render_admin("admin/system_health.html", "system_health", **get_system_health_context())


@admin_bp.route("/content")
def content():
    return _render_admin("admin/content.html", "content", **get_content_context())


@admin_bp.route("/audit-logs")
def audit_logs():
    return _render_admin("admin/audit_logs.html", "audit_logs", **get_audit_context())

@admin_bp.route("/payments/verify/<reference>", methods=["POST"])
def verify_payment(reference: str):
    from services.booking_service import update_booking_payment
    booking = update_booking_payment(reference, {"payment_status": "Paid"})
    flash(f"Payment for {reference} verified successfully." if booking else "Booking not found.")
    return redirect(url_for("admin.payments"))

@admin_bp.route("/payments/reject/<reference>", methods=["POST"])
def reject_payment(reference: str):
    from services.booking_service import update_booking_payment
    booking = update_booking_payment(reference, {"payment_status": "Failed"})
    flash(f"Payment for {reference} rejected." if booking else "Booking not found.")
    return redirect(url_for("admin.payments"))

@admin_bp.route("/refunds")
def refunds():
    return _render_admin("admin/reports.html", "reports", **get_reports_context())

@admin_bp.route("/alerts")
def alerts():
    from services.admin_service import get_alerts_context
    return _render_admin("admin/alerts.html", "alerts", **get_alerts_context())


from datetime import datetime
import random
import string
from flask import request, render_template

def _tarasi_invoice_code():
    stamp = datetime.now().strftime("%Y%m%d")
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"TAR-INV-{stamp}-{rand}"

@admin_bp.route("/invoices/create", methods=["GET", "POST"])
def create_invoice():
    if request.method == "POST":
        invoice = {
            "invoice_code": _tarasi_invoice_code(),
            "created_at": datetime.now().strftime("%d %b %Y, %H:%M"),
            "client_name": request.form.get("client_name", "").strip(),
            "contact_number": request.form.get("contact_number", "").strip(),
            "passengers": request.form.get("passengers", "1").strip(),
            "service_type": request.form.get("service_type", "").strip(),
            "pickup": request.form.get("pickup", "").strip(),
            "dropoff": request.form.get("dropoff", "").strip(),
            "service_date": request.form.get("service_date", "").strip(),
            "service_time": request.form.get("service_time", "").strip(),
            "amount": float(request.form.get("amount") or 0),
        }
        return render_template("admin/invoice_view.html", invoice=invoice, admin_shell=get_admin_shell("invoices"))

    return render_template("admin/invoice_create.html", admin_shell=get_admin_shell("invoices"))
