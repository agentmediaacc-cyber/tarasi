from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from api.admin_api import admin_snapshot
from api.booking_api import booking_snapshot
from api.driver_api import driver_snapshot
from api.profile_api import profile_snapshot
from services.db_service import get_db_status, fetch_rows
from services.driver_service import current_driver_from_session, update_driver_location
from services.homepage_service import get_featured_fleet, get_featured_tours, get_featured_transport_routes, homepage_has_live_data
from services.tarasi_pricing_engine import (
    assign_best_driver,
    create_invoice_for_booking,
    create_payment_proof,
    get_bank_details,
    get_booking_by_number as get_pricing_booking_by_number,
    get_invoice_by_booking_number,
    get_payment_by_booking_number,
    update_payment_status,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/health")
def api_health():
    return jsonify({"ok": True, "db": get_db_status()})


@api_bp.route("/homepage")
def api_homepage():
    return jsonify(
        {
            "ok": True,
            "has_live_data": homepage_has_live_data(),
            "routes": get_featured_transport_routes(limit=6),
            "tours": get_featured_tours(limit=4),
            "fleet": get_featured_fleet(limit=4),
        }
    )


@api_bp.route("/bookings")
def api_bookings():
    return jsonify(booking_snapshot())


@api_bp.route("/bookings/<reference>")
def api_booking_detail(reference: str):
    booking = booking_snapshot(reference)
    if not booking:
        booking = get_pricing_booking_by_number(reference)
        if booking:
            booking["reference"] = booking.get("booking_number")
            payment = get_payment_by_booking_number(reference)
            invoice = get_invoice_by_booking_number(reference)
            booking["payment"] = payment
            booking["invoice"] = invoice
    return jsonify(booking or {"error": "not_found"}), (200 if booking else 404)


@api_bp.route("/routes")
def api_routes():
    return jsonify(get_featured_transport_routes(limit=20))


@api_bp.route("/fleet")
def api_fleet():
    return jsonify(get_featured_fleet(limit=20))


@api_bp.route("/tours")
def api_tours():
    return jsonify(get_featured_tours(limit=20))


@api_bp.route("/support")
def api_support():
    return jsonify(fetch_rows("support_tickets", limit=20))


@api_bp.route("/driver/location", methods=["POST"])
def api_driver_location():
    driver = current_driver_from_session(session)
    if not driver:
        return jsonify({"ok": False, "error": "driver_login_required"}), 401

    payload = request.get_json(silent=True) or request.form
    driver_id = str(payload.get("driver_id", "")).strip()
    if driver_id and driver_id != str(driver.get("driver_id")):
        return jsonify({"ok": False, "error": "driver_mismatch"}), 403

    ok, result = update_driver_location(driver, payload.get("lat"), payload.get("lng"))
    if not ok:
        return jsonify({"ok": False, "error": result}), 400
    return jsonify({"ok": True, "location": result})

@api_bp.route("/payments/<reference>")
def api_payment_detail(reference: str):
    from api.booking_api import booking_snapshot
    booking = booking_snapshot(reference)
    if not booking:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        "reference": booking.get("reference"),
        "status": booking.get("payment_status"),
        "method": booking.get("payment_method"),
        "amount": booking.get("amount")
    })

@api_bp.route("/wallet")
def api_wallet():
    from services.profile_service import get_profile_dashboard
    dashboard = get_profile_dashboard(session)
    return jsonify(dashboard.get("wallet", {}))

@api_bp.route("/invoices/<reference>")
def api_invoice_detail(reference: str):
    from api.booking_api import booking_snapshot
    booking = booking_snapshot(reference)
    if not booking:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        "invoice_number": booking.get("invoice_number"),
        "amount": booking.get("amount"),
        "status": booking.get("payment_status")
    })

@api_bp.route("/notifications")
def api_notifications():
    from services.notification_service import list_user_notifications
    user_email = session.get("user_email") or ""
    if not user_email:
        return jsonify([])
    return jsonify(list_user_notifications(user_email))

@api_bp.route("/notifications/read-all", methods=["POST"])
def api_notifications_read_all():
    from services.notification_service import mark_all_read
    user_email = session.get("user_email") or ""
    if not user_email:
        return jsonify({"ok": False}), 403
    mark_all_read(user_email)
    return jsonify({"ok": True})

@api_bp.route("/notifications/<id>/read", methods=["POST"])
def api_notification_read(id: str):
    from services.notification_service import mark_notification_read
    mark_notification_read(id)
    return jsonify({"ok": True})


@api_bp.route("/bookings/<booking_number>/payment-proof", methods=["POST"])
def api_booking_payment_proof(booking_number: str):
    payload = request.get_json(silent=True) or {}
    payment = create_payment_proof(
        booking_number,
        proof_url=str(payload.get("proof_url", "")).strip(),
        proof_text=str(payload.get("proof_text", "")).strip(),
    )
    if not payment:
        return jsonify({"ok": False, "error": "booking_not_found"}), 404
    return jsonify({"ok": True, "payment_reference": payment["payment_reference"], "payment": payment})


@api_bp.route("/bookings/<booking_number>/invoice", methods=["POST"])
def api_booking_create_invoice(booking_number: str):
    invoice = create_invoice_for_booking(booking_number, base_url=request.host_url.rstrip("/"))
    if not invoice:
        return jsonify({"ok": False, "error": "booking_not_found"}), 404
    return jsonify(
        {
            "ok": True,
            "invoice_number": invoice["invoice_number"],
            "invoice_url": f"/booking/{booking_number}/invoice",
            "invoice": invoice,
        }
    )


@api_bp.route("/bookings/<booking_number>/invoice")
def api_booking_get_invoice(booking_number: str):
    invoice = get_invoice_by_booking_number(booking_number)
    if not invoice:
        return jsonify({"ok": False, "error": "invoice_not_found"}), 404
    return jsonify({"ok": True, "invoice": invoice, "invoice_url": f"/booking/{booking_number}/invoice"})


@api_bp.route("/bookings/<booking_number>/assign-driver", methods=["POST"])
def api_booking_assign_driver(booking_number: str):
    booking = assign_best_driver(booking_number)
    if not booking:
        return jsonify({"ok": False, "error": "no_driver_available"}), 404
    return jsonify({"ok": True, "booking": booking})


@api_bp.route("/admin/bookings/<booking_number>/payment/approve", methods=["POST"])
def api_admin_booking_payment_approve(booking_number: str):
    payment = update_payment_status(booking_number, "approved", "Approved from admin pricing dashboard.")
    if not payment:
        return jsonify({"ok": False, "error": "payment_not_found"}), 404
    return jsonify({"ok": True, "payment": payment})


@api_bp.route("/admin/bookings/<booking_number>/payment/reject", methods=["POST"])
def api_admin_booking_payment_reject(booking_number: str):
    payload = request.get_json(silent=True) or {}
    payment = update_payment_status(
        booking_number,
        "rejected",
        str(payload.get("admin_notes", "Rejected from admin pricing dashboard.")).strip(),
    )
    if not payment:
        return jsonify({"ok": False, "error": "payment_not_found"}), 404
    return jsonify({"ok": True, "payment": payment})
