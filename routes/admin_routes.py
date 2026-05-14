from __future__ import annotations

import csv
import json
import random
import base64
import os
import string
from datetime import datetime
from io import StringIO, BytesIO
from urllib.parse import quote_plus

from flask import Blueprint, flash, jsonify, make_response, redirect, render_template, request, session, url_for

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
    get_pricing_context,
    get_reports_context,
    get_routes_context,
    get_support_context,
    get_system_health_context,
    get_tours_context,
    log_admin_action,
    update_customer_block,
    update_driver_action,
    update_support_ticket,
)
from services.booking_service import BOOKING_STATUSES, update_booking_metadata, update_booking_status
from services.db_service import fetch_rows, insert_row, resolve_table_name, update_row
from services.tarasi_pricing_engine import (
    assign_best_driver,
    calculate_quote,
    create_booking,
    create_invoice_for_booking,
    update_payment_status,
)


from services.tarasi_live_support import (
    admin_join_chat,
    close_chat,
    get_chat_messages,
    get_open_support_chats,
    get_support_chat,
    get_unread_notifications,
    mark_notification_read,
    release_to_bot,
    save_support_message,
)


from services.tarasi_bot_storage import (
    create_knowledge_item,
    deactivate_knowledge_item,
    get_active_knowledge,
    get_dashboard_summary,
    update_knowledge_item,
)


from services.auth_service import require_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _render_admin(template_name: str, active_section: str, **context):
    context["admin_shell"] = get_admin_shell(active_section)
    return render_template(template_name, **context)


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_urls(raw: str | None) -> list[str]:
    return [item.strip() for item in str(raw or "").replace("\n", ",").split(",") if item.strip()]


def _sync_tarasi_user(payload: dict[str, str], supabase_user_id: str | None = None) -> dict | None:
    email = str(payload.get("email") or "").strip().lower()
    if not email:
        return None
    user_payload = {
        "supabase_user_id": supabase_user_id or payload.get("user_id") or "",
        "full_name": payload.get("full_name") or "",
        "email": email,
        "phone": payload.get("phone") or "",
        "account_type": payload.get("account_type") or "Driver",
        "status": payload.get("status") or "active",
        "updated_at": datetime.now().isoformat(),
    }
    existing = fetch_rows("tarasi_users", filters={"email": email}, limit=1)
    if existing:
        return update_row("tarasi_users", "email", email, user_payload)
    user_payload["created_at"] = user_payload["updated_at"]
    return insert_row("tarasi_users", user_payload)


def _save_document_links(table: str, owner_field: str, owner_id: str, document_type: str, urls: list[str]) -> int:
    saved = 0
    for url in urls:
        created = insert_row(
            table,
            {
                owner_field: owner_id,
                "document_type": document_type,
                "document_url": url,
                "status": "active",
                "created_at": datetime.now().isoformat(),
            },
        )
        if created:
            saved += 1
    return saved


def _bot_knowledge_items() -> list[dict]:
    rows = []
    for row in fetch_rows("bot_training_data", limit=100):
        rows.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "category": row.get("category") or "general",
                "keywords": row.get("keywords") or [],
                "content": row.get("content") or "",
                "priority": row.get("priority") or 5,
                "updated_at": row.get("updated_at") or row.get("created_at") or "",
                "source_table": "bot_training_data",
                "linked_id": row.get("linked_id"),
            }
        )
    return rows


@admin_bp.route("")
@require_admin
def dashboard():
    return _render_admin("admin/dashboard.html", "dashboard", **get_dashboard_context())


@admin_bp.route("/api/dashboard/summary")
@require_admin
def admin_dashboard_summary():
    from services.admin_service import get_dashboard_summary
    return jsonify(get_dashboard_summary())


@admin_bp.route("/api/dashboard/live")
@require_admin
def admin_dashboard_live():
    from services.admin_service import STATUS_GROUPS, _bookings, _drivers, _support
    live_bookings = _bookings(limit=20)
    active_rides = [b for b in live_bookings if b.get("status_key") in STATUS_GROUPS["active"]]
    support_rows = _support(limit=20)
    drivers_online = sum(
        1
        for driver in _drivers(limit=200)
        if str(driver.get("status") or driver.get("availability") or "").strip().lower() in {"online", "available", "active"}
    )
    return jsonify({
        "active_rides": active_rides,
        "support_queue": len([row for row in support_rows if str(row.get("status") or "").lower() != "resolved"]),
        "drivers_online": drivers_online,
        "timestamp": datetime.now().isoformat()
    })


@admin_bp.route("/bookings")
@require_admin
def bookings():
    status_filter = request.args.get("status", "all")
    # For the main list, we can still afford a bit more but keep it reasonable
    return _render_admin("admin/bookings.html", "bookings", **get_bookings_context(status_filter=status_filter))


@admin_bp.route("/bookings/<reference>")
@require_admin
def booking_detail(reference: str):
    context = get_booking_detail_context(reference)
    booking = context.get("booking")
    return _render_admin("admin/booking_detail.html", "bookings", not_found=booking is None, **context), (404 if booking is None else 200)


@admin_bp.route("/bookings/<reference>/status", methods=["POST"])
@require_admin
def update_status(reference: str):
    status = request.form.get("status", "").strip()
    if status not in BOOKING_STATUSES:
        flash("Invalid booking status.")
        return redirect(url_for("admin.booking_detail", reference=reference))
    booking = update_booking_status(reference, status)
    flash(f"Booking {reference} updated." if booking else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/assign-driver", methods=["GET", "POST"])
@require_admin
def assign_driver(reference: str):
    if request.method == "GET":
        return booking_detail(reference)
    driver_identifier = request.form.get("driver_id", "").strip()
    ok = assign_booking_driver(reference, driver_identifier)
    flash("Driver assigned to booking." if ok else "Driver assignment is unavailable or the selected driver was not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/note", methods=["POST"])
@require_admin
def add_note(reference: str):
    note = request.form.get("note", "").strip()
    ok = add_booking_note(reference, note)
    flash("Admin note saved." if ok else "Admin note could not be saved.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/approve-cancellation", methods=["POST"])
@require_admin
def approve_cancellation(reference: str):
    booking = update_booking_metadata(reference, {"cancelled_at": datetime.now().isoformat(timespec="seconds")}, status="Cancelled")
    flash(f"Cancellation approved for {reference}." if booking else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/<reference>/reject-cancellation", methods=["POST"])
@require_admin
def reject_cancellation(reference: str):
    booking = update_booking_metadata(reference, {"cancel_request_note": "", "cancelled_at": None}, status="Confirmed")
    flash(f"Cancellation rejected for {reference}." if booking else "Booking not found.")
    return redirect(url_for("admin.booking_detail", reference=reference))


@admin_bp.route("/bookings/create", methods=["POST"])
@require_admin
def bookings_create_manual():
    payload = request.form.to_dict()
    # Use pricing engine to get an estimate if not provided
    if not payload.get("final_price"):
        quote = calculate_quote(payload)
        payload["final_price"] = quote["final_price"]
        payload["quote_id"] = quote["quote_number"]
    
    booking = create_booking(payload)
    if booking:
        log_admin_action("created_manual_booking", "bookings", booking.get("booking_number"), new_value=booking)
        flash(f"Manual booking {booking.get('booking_number')} created.")
    else:
        flash("Failed to create manual booking.")
    return redirect(url_for("admin.bookings"))


@admin_bp.route("/drivers", methods=["GET", "POST"])
@require_admin
def drivers():
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        driver_id = request.form.get("driver_id", "").strip()
        if action in {"approve", "suspend"} and driver_id:
            ok = update_driver_action(driver_id, action)
            flash(f"Driver {action}d successfully." if ok else f"Driver could not be {action}d.")
        else:
            return drivers_save()
    return _render_admin("admin/drivers.html", "drivers", **get_drivers_context())


@admin_bp.route("/drivers/save", methods=["POST"])
@require_admin
def drivers_save():
    from services.driver_auth_service import create_driver_account
    from services.supabase_service import get_supabase_config_status
    driver_id = request.form.get("driver_id")
    vehicle_id = request.form.get("vehicle_id") or None
    payload = {
        "full_name": request.form.get("full_name"),
        "email": request.form.get("email"),
        "phone": request.form.get("phone"),
        "password": request.form.get("password"),
        "license_number": request.form.get("license_number"),
        "driver_code": request.form.get("driver_code"),
        "service_type": request.form.get("service_type"),
        "vehicle_id": vehicle_id,
        "status": request.form.get("status", "Offline"),
        "rating": request.form.get("rating"),
    }

    if driver_id:
        driver_rows = fetch_rows("drivers", filters={"driver_code": driver_id}, limit=1) or fetch_rows("drivers", filters={"id": driver_id}, limit=1)
        existing_driver = driver_rows[0] if driver_rows else None
        if not existing_driver:
            flash("Driver not found.")
            return redirect(url_for("admin.drivers"))
        driver_payload = {
            "driver_code": payload.get("driver_code") or existing_driver.get("driver_code"),
            "license_number": payload.get("license_number"),
            "phone": payload.get("phone"),
            "status": payload.get("status"),
            "rating": float(payload["rating"]) if payload.get("rating") not in (None, "") else existing_driver.get("rating"),
            "updated_at": datetime.now().isoformat(),
        }
        ok = update_row("drivers", "id", existing_driver["id"], driver_payload)
        user_row = _sync_tarasi_user(payload | {"account_type": "Driver"})
        if vehicle_id:
            update_row("vehicles", "id", vehicle_id, {"driver_id": existing_driver["id"], "updated_at": datetime.now().isoformat()})
        doc_count = _save_document_links("driver_documents", "driver_id", existing_driver["id"], "driver_profile", _split_urls(request.form.get("document_urls")))
        action = "updated"
        message = f"Driver {action} successfully."
    else:
        action = "created"
        auth_result = None
        if payload.get("password") and get_supabase_config_status().get("configured"):
            auth_ok, auth_result = create_driver_account(payload)
            if auth_ok:
                driver_id = auth_result
                created_driver = fetch_rows("drivers", filters={"driver_code": driver_id}, limit=1)
                driver_row = created_driver[0] if created_driver else None
                _sync_tarasi_user(payload | {"account_type": "Driver"}, supabase_user_id=(driver_row or {}).get("user_id"))
                if driver_row and vehicle_id:
                    update_row("vehicles", "id", vehicle_id, {"driver_id": driver_row["id"], "updated_at": datetime.now().isoformat()})
                    _save_document_links("driver_documents", "driver_id", driver_row["id"], "driver_profile", _split_urls(request.form.get("document_urls")))
                ok = True
                message = f"Driver created successfully. Driver ID: {driver_id}"
            else:
                ok = False
                message = f"Failed to create driver auth account: {auth_result}"
        else:
            driver_code = (payload.get("driver_code") or f"DRV-{datetime.now().strftime('%H%M%S')}").strip()
            driver_payload = {
                "driver_code": driver_code,
                "license_number": payload.get("license_number"),
                "phone": payload.get("phone"),
                "status": payload.get("status"),
                "rating": float(payload["rating"]) if payload.get("rating") not in (None, "") else None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            created = insert_row("drivers", driver_payload)
            if created:
                driver_id = driver_code
                _sync_tarasi_user(payload | {"account_type": "Driver"})
                if vehicle_id:
                    update_row("vehicles", "id", vehicle_id, {"driver_id": created["id"], "updated_at": datetime.now().isoformat()})
                _save_document_links("driver_documents", "driver_id", created["id"], "driver_profile", _split_urls(request.form.get("document_urls")))
                ok = True
                message = f"Driver created successfully. Driver ID: {driver_code}"
            else:
                ok = False
                message = "Failed to create driver."

    if ok:
        log_admin_action(f"{action}_driver", "drivers", driver_id, new_value=payload)
        flash(message)
    else:
        flash(message)
    return redirect(url_for("admin.drivers"))


@admin_bp.route("/drivers/<driver_id>/documents", methods=["POST"])
@require_admin
def drivers_upload_document(driver_id: str):
    # This would involve file upload logic, for now we simulate saving the URL
    document_type = request.form.get("document_type")
    document_url = request.form.get("document_url") # In real app, this would be from storage_service
    payload = {
        "driver_id": driver_id,
        "document_type": document_type,
        "document_url": document_url,
        "status": "pending",
        "expiry_date": request.form.get("expiry_date")
    }
    ok = insert_row("driver_documents", payload)
    if ok:
        log_admin_action("uploaded_driver_document", "driver_documents", ok.get("id"), new_value=payload)
        flash("Document uploaded successfully.")
    else:
        flash("Failed to upload document.")
    return redirect(url_for("admin.drivers"))


@admin_bp.route("/customers", methods=["GET", "POST"])
@require_admin
def customers():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        action = request.form.get("action", "").strip()
        if email and action in {"block", "unblock"}:
            blocked = action == "block"
            ok = update_customer_block(email, blocked)
            flash(f"Customer {'blocked' if blocked else 'unblocked'}." if ok else "Customer status could not be updated.")
            return redirect(url_for("admin.customers"))
    return _render_admin("admin/customers.html", "customers", **get_customers_context())


@admin_bp.route("/customers/message", methods=["POST"])
@require_admin
def customers_send_message():
    email = request.form.get("email")
    message = request.form.get("message")
    # In real app, this would use messaging_service or notification_service
    from services.notification_service import trigger_generic_notification
    ok = trigger_generic_notification(email, "Message from Tarasi Admin", message)
    if ok:
        log_admin_action("sent_customer_message", "profiles", email, new_value={"message": message})
        flash("Message sent to customer.")
    else:
        flash("Failed to send message.")
    return redirect(url_for("admin.customers"))


@admin_bp.route("/fleet")
@require_admin
def fleet():
    return _render_admin("admin/fleet.html", "fleet", **get_fleet_context())


@admin_bp.route("/fleet/save", methods=["POST"])
@require_admin
def fleet_save():
    vehicle_id = request.form.get("vehicle_id")
    payload = {
        "name": request.form.get("name"),
        "vehicle_type": request.form.get("vehicle_type"),
        "plate_number": request.form.get("plate_number"),
        "seats": int(request.form.get("seats") or 0),
        "luggage_capacity": request.form.get("luggage_capacity"),
        "aircon": _truthy(request.form.get("aircon")),
        "image_url": request.form.get("image_url"),
        "status": request.form.get("status", "available"),
        "driver_id": request.form.get("driver_id") or None,
        "updated_at": datetime.now().isoformat(),
    }
    fleet_group_name = request.form.get("fleet_group_name", "").strip()
    fleet_group_id = request.form.get("fleet_group_id") or None
    if fleet_group_name and resolve_table_name("fleet_groups"):
        existing_group = fetch_rows("fleet_groups", filters={"name": fleet_group_name}, limit=1)
        if existing_group:
            fleet_group_id = existing_group[0].get("id")
        else:
            created_group = insert_row("fleet_groups", {"name": fleet_group_name, "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()})
            fleet_group_id = (created_group or {}).get("id")
    if vehicle_id:
        ok = update_row("vehicles", "id", vehicle_id, payload)
        action = "updated"
    else:
        payload["created_at"] = payload["updated_at"]
        ok = insert_row("vehicles", payload)
        action = "created"

    if ok:
        vehicle_row_id = vehicle_id or ok.get("id")
        _save_document_links("vehicle_documents", "vehicle_id", vehicle_row_id, "vehicle_profile", _split_urls(request.form.get("document_urls")))
        log_admin_action(f"{action}_vehicle", "vehicles", vehicle_row_id, new_value=payload)
        flash(f"Vehicle {action} successfully.")
    else:
        flash("Failed to save vehicle.")
    return redirect(url_for("admin.fleet"))


@admin_bp.route("/fleet/<vehicle_id>/documents", methods=["POST"])
@require_admin
def fleet_upload_document(vehicle_id: str):
    document_type = request.form.get("document_type")
    document_url = request.form.get("document_url")
    payload = {
        "vehicle_id": vehicle_id,
        "document_type": document_type,
        "document_url": document_url,
        "status": "pending",
        "expiry_date": request.form.get("expiry_date")
    }
    ok = insert_row("vehicle_documents", payload)
    if ok:
        log_admin_action("uploaded_vehicle_document", "vehicle_documents", ok.get("id"), new_value=payload)
        flash("Vehicle document uploaded.")
    else:
        flash("Failed to upload vehicle document.")
    return redirect(url_for("admin.fleet"))


@admin_bp.route("/routes")
@require_admin
def routes_catalog():
    return _render_admin("admin/routes.html", "routes", **get_routes_context())


@admin_bp.route("/tours")
@require_admin
def tours():
    return _render_admin("admin/tours.html", "tours", **get_tours_context())


@admin_bp.route("/support", methods=["GET", "POST"])
@require_admin
def support():
    if request.method == "POST":
        reference = request.form.get("reference", "").strip()
        payload = {
            "status": request.form.get("status", "").strip(),
        }
        payload = {key: value for key, value in payload.items() if value}
        ok = update_support_ticket(reference, payload)
        flash("Ticket updated." if ok else "Support ticket update could not be completed.")
        return redirect(url_for("admin.support"))
    return _render_admin("admin/support.html", "support", **get_support_context())


@admin_bp.route("/support/close", methods=["POST"])
@require_admin
def support_close():
    reference = request.form.get("reference", "").strip()
    ok = update_support_ticket(reference, {"status": "Closed", "updated_at": datetime.now().isoformat()})
    flash("Support ticket closed." if ok else "Support ticket could not be closed.")
    return redirect(url_for("admin.support"))


@admin_bp.route("/payments")
@require_admin
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


@admin_bp.route("/pricing")
@require_admin
def pricing_dashboard():
    return _render_admin("admin/pricing_dashboard.html", "pricing", **get_pricing_context())


@admin_bp.route("/pricing/simulate", methods=["POST"])
@require_admin
def pricing_simulate():
    payload = {
        "pickup_text": request.form.get("pickup_text"),
        "dropoff_text": request.form.get("dropoff_text"),
        "vehicle_type": request.form.get("vehicle_type"),
        "service_type": request.form.get("service_type"),
        "passengers": request.form.get("passengers"),
        "luggage_count": request.form.get("luggage_count"),
        "pickup_time": request.form.get("pickup_time"),
    }
    quote = calculate_quote(payload)
    context = get_pricing_context()
    context["simulator_result"] = quote
    context["simulator_payload"] = payload
    return _render_admin("admin/pricing_dashboard.html", "pricing", **context)


@admin_bp.route("/pricing/zones/save", methods=["POST"])
@require_admin
def pricing_zones_save():
    zone_id = request.form.get("zone_id")
    payload = {
        "zone_name": request.form.get("zone_name"),
        "suburb_area": request.form.get("suburb_area"),
        "description": request.form.get("description"),
        "base_fare": float(request.form.get("base_fare") or 0),
        "price_per_km": float(request.form.get("price_per_km") or 0),
        "airport_fee": float(request.form.get("airport_fee") or 0),
        "minimum_fare": float(request.form.get("minimum_fare") or 0),
        "night_fee": float(request.form.get("night_fee") or 0),
        "luggage_fee": float(request.form.get("luggage_fee") or 0),
        "waiting_fee": float(request.form.get("waiting_fee") or 0),
        "latitude": float(request.form.get("latitude") or 0),
        "longitude": float(request.form.get("longitude") or 0),
        "map_radius_km": float(request.form.get("map_radius_km") or 0),
        "is_active": request.form.get("is_active") == "on",
        "updated_at": datetime.now().isoformat(),
    }
    if zone_id:
        ok = update_row("pricing_zones", "id", zone_id, payload)
        action = "updated"
    else:
        payload["created_at"] = payload["updated_at"]
        ok = insert_row("pricing_zones", payload)
        action = "created"
    
    if ok:
        log_admin_action(f"{action}_pricing_zone", "pricing_zones", zone_id or ok.get("id"), new_value=payload)
        flash(f"Zone {action} successfully.")
    else:
        flash("Failed to save zone.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/rules/save", methods=["POST"])
@require_admin
def pricing_rules_save():
    rule_id = request.form.get("rule_id")
    payload = {
        "rule_name": request.form.get("rule_name"),
        "rule_type": request.form.get("rule_type"),
        "vehicle_type": request.form.get("vehicle_type"),
        "value": float(request.form.get("value") or 0),
        "description": request.form.get("description"),
        "is_active": request.form.get("is_active") == "on",
        "updated_at": datetime.now().isoformat(),
    }
    if rule_id:
        ok = update_row("pricing_rules", "id", rule_id, payload)
        action = "updated"
    else:
        payload["created_at"] = payload["updated_at"]
        ok = insert_row("pricing_rules", payload)
        action = "created"
    
    if ok:
        log_admin_action(f"{action}_pricing_rule", "pricing_rules", rule_id or ok.get("id"), new_value=payload)
        flash(f"Pricing rule {action} successfully.")
    else:
        flash("Failed to save pricing rule.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/rules/<rule_id>/deactivate", methods=["POST"])
@require_admin
def pricing_rule_deactivate(rule_id: str):
    ok = update_row("pricing_rules", "id", rule_id, {"is_active": False, "updated_at": datetime.now().isoformat()})
    if ok:
        log_admin_action("deactivated_pricing_rule", "pricing_rules", rule_id)
        flash("Pricing rule deactivated.")
    else:
        flash("Failed to deactivate pricing rule.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/zones/<zone_id>/delete", methods=["POST"])
@require_admin
def pricing_zone_delete(zone_id: str):
    # For safety, we just deactivate instead of hard delete if it has dependencies
    ok = update_row("pricing_zones", "id", zone_id, {"is_active": False})
    if ok:
        log_admin_action("deactivated_pricing_zone", "pricing_zones", zone_id)
        flash("Zone deactivated.")
    else:
        flash("Failed to deactivate zone.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/reports")
@require_admin
def reports():
    return _render_admin("admin/reports.html", "reports", **get_reports_context())


@admin_bp.route("/system-health")
@require_admin
def system_health():
    return _render_admin("admin/system_health.html", "system_health", **get_system_health_context())


@admin_bp.route("/content")
@require_admin
def content():
    return _render_admin("admin/content.html", "content", **get_content_context())


@admin_bp.route("/content/homepage/save", methods=["POST"])
@require_admin
def content_homepage_save():
    section_name = request.form.get("section_name", "").strip()
    if not section_name:
        flash("Section name is required.")
        return redirect(url_for("admin.content"))

    content_payload = {
        key: value.strip()
        for key, value in request.form.items()
        if key not in {"section_name", "content"} and value is not None
    }
    if not content_payload and request.form.get("content"):
        try:
            content_payload = json.loads(request.form.get("content", ""))
        except json.JSONDecodeError:
            content_payload = {}

    payload = {
        "section_name": section_name,
        "content": content_payload,
        "updated_at": datetime.now().isoformat(),
    }
    existing = fetch_rows("homepage_content", filters={"section_name": section_name}, limit=1)
    ok = (
        update_row("homepage_content", "section_name", section_name, payload)
        if existing else
        insert_row("homepage_content", payload)
    )
    if ok:
        log_admin_action("updated_homepage_content", "homepage_content", section_name, new_value=payload)
        flash("Homepage content updated.")
    else:
        flash("Failed to update content.")
    return redirect(url_for("admin.content"))


@admin_bp.route("/marketing/coupons/save", methods=["POST"])
@require_admin
def marketing_coupons_save():
    payload = {
        "code": request.form.get("code"),
        "discount_type": request.form.get("discount_type"),
        "discount_value": float(request.form.get("discount_value") or 0),
        "expiry_date": request.form.get("expiry_date"),
        "is_active": True
    }
    ok = insert_row("coupons", payload)
    if ok:
        log_admin_action("created_coupon", "coupons", ok.get("id"), new_value=payload)
        flash("Coupon created successfully.")
    else:
        flash("Failed to create coupon.")
    return redirect(url_for("admin.payments")) # Or dedicated marketing page


@admin_bp.route("/audit-logs")
@require_admin
def audit_logs():
    return _render_admin("admin/audit_logs.html", "audit_logs", **get_audit_context())


@admin_bp.route("/users/admin/save", methods=["POST"])
@require_admin
def admin_users_save():
    admin_id = request.form.get("admin_id")
    payload = {
        "email": request.form.get("email"),
        "full_name": request.form.get("full_name"),
        "role_id": request.form.get("role_id"),
        "status": request.form.get("status", "active"),
        "updated_at": datetime.now().isoformat()
    }
    if admin_id:
        ok = update_row("admin_users", "id", admin_id, payload)
        action = "updated"
    else:
        ok = insert_row("admin_users", payload)
        action = "created"
        
    if ok:
        log_admin_action(f"{action}_admin_user", "admin_users", admin_id or ok.get("id"), new_value=payload)
        flash(f"Admin user {action} successfully.")
    else:
        flash("Failed to save admin user.")
    return redirect(url_for("admin.audit_logs"))

@admin_bp.route("/payments/verify/<reference>", methods=["POST"])
@require_admin
def verify_payment(reference: str):
    from services.booking_service import update_booking_payment
    booking = update_booking_payment(reference, {"payment_status": "Paid"})
    flash(f"Payment for {reference} verified successfully." if booking else "Booking not found.")
    return redirect(url_for("admin.payments"))

@admin_bp.route("/payments/reject/<reference>", methods=["POST"])
@require_admin
def reject_payment(reference: str):
    from services.booking_service import update_booking_payment
    booking = update_booking_payment(reference, {"payment_status": "Failed"})
    flash(f"Payment for {reference} rejected." if booking else "Booking not found.")
    return redirect(url_for("admin.payments"))

@admin_bp.route("/finance/refunds/process", methods=["POST"])
@require_admin
def finance_process_refund():
    payment_id = request.form.get("payment_id")
    amount = float(request.form.get("amount") or 0)
    reason = request.form.get("reason")
    
    payload = {
        "payment_id": payment_id,
        "amount": amount,
        "reason": reason,
        "status": "completed",
        "processed_by": session.get("user", {}).get("user_id")
    }
    ok = insert_row("refunds", payload)
    if ok:
        log_admin_action("processed_refund", "refunds", ok.get("id"), new_value=payload)
        flash("Refund processed successfully.")
    else:
        flash("Failed to process refund.")
    return redirect(url_for("admin.payments"))

@admin_bp.route("/alerts")
@require_admin
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


def _safe_float(value, default=0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)

def _tarasi_invoice_code(document_type="Invoice"):
    prefix = "INV" if document_type == "Invoice" else "QUO"
    stamp = datetime.now().strftime("%y%m%d")
    rand = "".join(random.choices(string.digits, k=3))
    return f"{prefix}-{stamp}-{rand}"

def _save_invoice_record(invoice):
    """
    Best-effort Supabase save.
    Create table tarasi_documents first if you want permanent history.
    This will never break invoice generation if Supabase/table is missing.
    """
    try:
        from services.supabase_service import get_supabase_client
        supabase = get_supabase_client()
        if not supabase:
            return False

        supabase.table("tarasi_documents").insert({
            "document_code": invoice["invoice_code"],
            "document_type": invoice["document_type"],
            "client_name": invoice["client_name"],
            "contact_number": invoice["contact_number"],
            "email": invoice["email"],
            "service_type": invoice["service_type"],
            "amount": invoice["amount"],
            "discount": invoice["discount"],
            "vat": invoice["vat"],
            "final_total": invoice["final_total"],
            "payment_status": invoice["payment_status"],
            "payload": invoice,
        }).execute()
        return True
    except Exception:
        return False


from datetime import datetime
import random
import string
from flask import request, render_template

def _tarasi_invoice_code(document_type="INVOICE"):
    stamp = datetime.now().strftime("%y%m%d")
    rand = "".join(random.choices(string.digits, k=3))
    prefix = "QUO" if document_type == "QUOTATION" else "INV"
    return f"{prefix}-{stamp}-{rand}"


from datetime import datetime
import random
import string
import os
from pathlib import Path
from flask import request, render_template, url_for

def _tarasi_doc_code(document_type="INVOICE"):
    now = datetime.now()
    prefix = "QUO" if document_type == "QUOTATION" else "INV"
    return f"{prefix}-{now.strftime('%y%m%d')}-{random.randint(100,999)}"

def _make_invoice_qr(invoice_code):
    try:
        import qrcode
        base_url = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5000").rstrip("/")
        invoice_url = f"{base_url}/admin/invoices/create?ref={invoice_code}"

        qr_dir = Path("static/generated/qr")
        qr_dir.mkdir(parents=True, exist_ok=True)

        qr_path = qr_dir / f"{invoice_code}.png"
        img = qrcode.make(invoice_url)
        img.save(qr_path)

        return {
            "url": invoice_url,
            "image": f"generated/qr/{invoice_code}.png"
        }
    except Exception:
        return {
            "url": "",
            "image": ""
        }


from datetime import datetime
import random
import os
import base64
from io import BytesIO
from urllib.parse import quote_plus
from flask import request, render_template

def _tarasi_doc_code(document_type="INVOICE"):
    prefix = "QUO" if document_type == "QUOTATION" else "INV"
    return f"{prefix}-{datetime.now().strftime('%y%m%d')}-{random.randint(100,999)}"


def _qr_data_uri(invoice_url: str) -> str:
    try:
        import qrcode
        img = qrcode.make(invoice_url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote_plus(invoice_url)}"

@admin_bp.route("/invoices/create", methods=["GET", "POST"])
@require_admin
def create_invoice():
    if request.method == "POST":
        document_type = request.form.get("document_type", "INVOICE").strip().upper()
        code = _tarasi_doc_code(document_type)

        amount = _safe_float(request.form.get("amount"), 0)
        discount = _safe_float(request.form.get("discount"), 0)
        vat_percent = _safe_float(request.form.get("vat"), 15)

        taxable = max(amount - discount, 0)
        vat_amount = taxable * (vat_percent / 100)
        final_total = taxable + vat_amount

        base_url = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5000").rstrip("/")
        invoice_url = f"{base_url}/admin/invoices/create?ref={code}"

        now = datetime.now()

        invoice = {
            "document_type": document_type,
            "invoice_code": code,
            "date_issued": now.strftime("%d %b %Y"),
            "issue_time": now.strftime("%H:%M"),
            "client_name": request.form.get("client_name", "").strip(),
            "contact_number": request.form.get("contact_number", "").strip(),
            "email": request.form.get("email", "").strip(),
            "service_type": request.form.get("service_type", "").strip(),
            "vehicle_type": request.form.get("vehicle_type", "").strip(),
            "passengers": request.form.get("passengers", "1").strip(),
            "detail_mode": request.form.get("detail_mode", "Full Trip Details").strip(),
            "pickup": request.form.get("pickup", "").strip(),
            "dropoff": request.form.get("dropoff", "").strip(),
            "service_date": request.form.get("service_date", "").strip(),
            "service_time": request.form.get("service_time", "").strip(),
            "payment_status": request.form.get("payment_status", "UNPAID").strip().upper(),
            "prepared_by": request.form.get("prepared_by", "").strip() or session.get("user", {}).get("full_name") or "Tarasi Operations",
            "notes": request.form.get("notes", "").strip(),
            "amount": amount,
            "subtotal": amount,
            "discount": discount,
            "vat_percent": vat_percent,
            "vat_amount": vat_amount,
            "final_total": final_total,
            "qr_url": invoice_url,
            "qr_data": _qr_data_uri(invoice_url),
            "pdf_url": "",
        }

        target_table = "quotes" if document_type == "QUOTATION" else "invoices"
        if target_table == "quotes":
            stored_payload = {
                "quote_number": code,
                "customer_name": invoice["client_name"],
                "email": invoice["email"],
                "phone": invoice["contact_number"],
                "pickup_text": invoice["pickup"],
                "dropoff_text": invoice["dropoff"],
                "vehicle_type": invoice["vehicle_type"],
                "service_type": invoice["service_type"],
                "passengers": int(invoice["passengers"] or 1),
                "amount": final_total,
                "final_price": final_total,
                "currency": "NAD",
                "status": "quoted",
                "pdf_url": invoice.get("pdf_url") or "",
                "metadata": invoice,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        else:
            stored_payload = {
                "invoice_number": code,
                "customer_name": invoice["client_name"],
                "amount": final_total,
                "currency": "NAD",
                "status": invoice["payment_status"],
                "pdf_url": invoice.get("pdf_url") or "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        stored = insert_row(target_table, stored_payload) if resolve_table_name(target_table) else None
        if stored:
            log_admin_action(f"created_{target_table[:-1]}", target_table, code, new_value=stored)
        else:
            flash(f"{document_type.title()} preview generated, but the Neon {target_table} table could not be updated.")

        return render_template("admin/invoice_view.html", invoice=invoice)

    return render_template(
        "admin/invoice_create.html",
        admin_shell=get_admin_shell("invoices")
    )

@admin_bp.route("/quotes/<quote_number>/convert", methods=["POST"])
@require_admin
def quotes_convert_to_invoice(quote_number: str):
    quote_rows = fetch_rows("quotes", filters={"quote_number": quote_number}, limit=1)
    quote = quote_rows[0] if quote_rows else None
    if quote and resolve_table_name("invoices"):
        invoice_number = _tarasi_doc_code("INVOICE")
        invoice = insert_row(
            "invoices",
            {
                "invoice_number": invoice_number,
                "customer_name": quote.get("customer_name") or "Tarasi customer",
                "amount": quote.get("amount") or quote.get("final_price") or 0,
                "currency": "NAD",
                "status": "UNPAID",
                "pdf_url": "",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        )
    else:
        invoice = create_invoice_for_booking(quote_number, base_url=request.host_url.rstrip("/"))
    if invoice:
        log_admin_action("converted_quote_to_invoice", "invoices", invoice.get("invoice_number"), old_value={"quote_number": quote_number})
        flash(f"Quote {quote_number} converted to Invoice {invoice.get('invoice_number')}.")
    else:
        flash("Failed to convert quote to invoice.")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/invoices/<invoice_number>/send", methods=["POST"])
@require_admin
def invoices_send_to_customer(invoice_number: str):
    email = request.form.get("email")
    # Logic to send PDF link via email/whatsapp
    from services.notification_service import trigger_generic_notification
    message = f"Your invoice {invoice_number} is ready. View it here: {request.host_url}admin/invoices/view?ref={invoice_number}"
    ok = trigger_generic_notification(email, f"Invoice {invoice_number} from Tarasi", message)
    if ok:
        log_admin_action("sent_invoice_to_customer", "invoices", invoice_number, new_value={"email": email})
        flash(f"Invoice {invoice_number} sent to {email}.")
    else:
        flash("Failed to send invoice.")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/support/live")
@require_admin
def live_support_dashboard():
    chats = get_open_support_chats()
    return _render_admin("admin/live_support.html", "support", chats=chats)


@admin_bp.route("/support/live/<chat_number>")
@require_admin
def live_support_room(chat_number: str):
    chat = get_support_chat(chat_number)
    if not chat:
        flash("Support chat not found.")
        return redirect(url_for("admin.live_support_dashboard"))
        
    messages = get_chat_messages(chat["id"])
    return _render_admin("admin/live_support_room.html", "support", chat=chat, messages=messages)


@admin_bp.route("/support/chat/<chat_number>/join", methods=["POST"])
@require_admin
def admin_join_support_chat(chat_number: str):
    admin_name = request.form.get("admin_name") or session.get("user_name") or session.get("user", {}).get("full_name") or "Tarasi Admin"
    if admin_join_chat(chat_number, admin_name):
        flash(f"Joined chat {chat_number}")
    else:
        flash("Could not join chat.")
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/support/chat/<chat_number>/message", methods=["POST"])
@require_admin
def admin_post_support_message(chat_number: str):
    chat = get_support_chat(chat_number)
    if not chat:
        return jsonify({"ok": False, "error": "Chat not found"}), 404

    json_payload = request.get_json(silent=True) or {}
    message = request.form.get("message") or json_payload.get("message")
    admin_name = session.get("user_name") or session.get("user", {}).get("full_name") or "Tarasi Admin"
    
    if not message:
        return jsonify({"ok": False, "error": "Message required"}), 400
        
    msg = save_support_message(chat["id"], "admin", admin_name, message)
    
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "message": msg})
        
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/support/chat/<chat_number>/close", methods=["POST"])
@require_admin
def admin_close_support_chat(chat_number: str):
    if close_chat(chat_number):
        flash(f"Chat {chat_number} closed.")
    else:
        flash("Could not close chat.")
    return redirect(url_for("admin.live_support_dashboard"))


@admin_bp.route("/support/chat/<chat_number>/release-bot", methods=["POST"])
@require_admin
def admin_release_support_to_bot(chat_number: str):
    if release_to_bot(chat_number):
        flash(f"Released chat {chat_number} back to bot.")
    else:
        flash("Could not release chat.")
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/api/notifications")
@require_admin
def admin_get_notifications():
    return jsonify({"notifications": get_unread_notifications()})


@admin_bp.route("/api/notifications/<notification_id>/read", methods=["POST"])
@require_admin
def admin_mark_notification_read(notification_id: str):
    mark_notification_read(notification_id)
    return jsonify({"ok": True})


@admin_bp.route("/bot/conversations")
@require_admin
def bot_conversations():
    convos = _extra_table_rows("bot_conversations")
    return _render_admin("admin/bot_dashboard.html", "bot", convos=convos)


@admin_bp.route("/bot/knowledge")
@require_admin
def bot_knowledge():
    return _render_admin("admin/bot_knowledge.html", "bot", items=_bot_knowledge_items())


@admin_bp.route("/bot/conversations/<convo_id>/messages")
@require_admin
def bot_conversation_messages(convo_id: str):
    messages = _safe_rows("bot_messages", filters={"conversation_id": convo_id})
    return jsonify({"messages": messages})


@admin_bp.route("/bot/messages/<message_id>/feedback", methods=["POST"])
@require_admin
def bot_message_feedback(message_id: str):
    is_useful = request.form.get("useful") == "true"
    ok = update_row("bot_messages", "id", message_id, {"is_useful": is_useful})
    if ok:
        log_admin_action("provided_bot_feedback", "bot_messages", message_id, new_value={"is_useful": is_useful})
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 500


@admin_bp.route("/bot/knowledge/create", methods=["POST"])
@require_admin
def bot_knowledge_create():
    payload = {
        "title": request.form.get("title"),
        "category": request.form.get("category") or "general",
        "keywords": [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()],
        "content": request.form.get("content"),
        "priority": int(request.form.get("priority") or 5),
        "created_by": session.get("user_name") or session.get("user", {}).get("full_name") or "Admin",
        "is_active": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    created = insert_row("bot_training_data", payload) if resolve_table_name("bot_training_data") else None
    category = str(payload["category"]).lower()
    if created and category in {"faq", "support", "tourism", "airport", "pricing"} and resolve_table_name("bot_faq"):
        insert_row(
            "bot_faq",
            {
                "question": payload["title"],
                "answer": payload["content"],
                "category": payload["category"],
                "priority": payload["priority"],
                "is_active": True,
                "created_at": payload["created_at"],
                "updated_at": payload["updated_at"],
            },
        )
    if created and category == "routes" and resolve_table_name("bot_route_knowledge"):
        insert_row(
            "bot_route_knowledge",
            {
                "route_name": payload["title"],
                "guidance_text": payload["content"],
                "vehicle_type": request.form.get("vehicle_type") or "",
                "is_active": True,
                "created_at": payload["created_at"],
                "updated_at": payload["updated_at"],
            },
        )
    if created:
        log_admin_action("created_bot_knowledge", "bot_training_data", created.get("id"), new_value=payload)
        flash("Knowledge item created.")
    else:
        flash("Failed to create knowledge item.")
    return redirect(url_for("admin.bot_knowledge"))


@admin_bp.route("/bot/knowledge/<item_id>/update", methods=["POST"])
@require_admin
def bot_knowledge_update(item_id: str):
    payload = {
        "title": request.form.get("title"),
        "category": request.form.get("category"),
        "keywords": [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()],
        "content": request.form.get("content"),
        "priority": int(request.form.get("priority") or 5),
        "updated_at": datetime.now().isoformat(),
    }
    updated = update_row("bot_training_data", "id", item_id, payload)
    if updated:
        log_admin_action("updated_bot_knowledge", "bot_training_data", item_id, new_value=payload)
        flash("Knowledge item updated.")
    else:
        flash("Failed to update knowledge item.")
    return redirect(url_for("admin.bot_knowledge"))


@admin_bp.route("/bot/knowledge/<item_id>/deactivate", methods=["POST"])
@require_admin
def bot_knowledge_deactivate(item_id: str):
    updated = update_row("bot_training_data", "id", item_id, {"is_active": False, "updated_at": datetime.now().isoformat()})
    if updated:
        log_admin_action("deactivated_bot_knowledge", "bot_training_data", item_id)
        flash("Knowledge item deactivated.")
    else:
        flash("Failed to deactivate knowledge item.")
    return redirect(url_for("admin.bot_knowledge"))
