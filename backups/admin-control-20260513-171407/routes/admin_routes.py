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
    get_pricing_context,
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
from services.tarasi_pricing_engine import assign_best_driver, create_invoice_for_booking, update_payment_status


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


@admin_bp.route("/pricing")
def pricing_dashboard():
    return _render_admin("admin/pricing_dashboard.html", "pricing", **get_pricing_context())


@admin_bp.route("/pricing/<booking_number>/invoice", methods=["POST"])
def pricing_create_invoice(booking_number: str):
    invoice = create_invoice_for_booking(booking_number, base_url=request.host_url.rstrip("/"))
    flash(f"Invoice {invoice['invoice_number']} created." if invoice else "Invoice could not be created.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/<booking_number>/assign-driver", methods=["POST"])
def pricing_assign_driver(booking_number: str):
    booking = assign_best_driver(booking_number)
    flash(f"Driver assigned to {booking_number}." if booking else "No suitable driver found.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/<booking_number>/payment/approve", methods=["POST"])
def pricing_approve_payment(booking_number: str):
    payment = update_payment_status(booking_number, "approved", "Approved from admin pricing dashboard.")
    flash(f"Payment approved for {booking_number}." if payment else "Payment record not found.")
    return redirect(url_for("admin.pricing_dashboard"))


@admin_bp.route("/pricing/<booking_number>/payment/reject", methods=["POST"])
def pricing_reject_payment(booking_number: str):
    payment = update_payment_status(booking_number, "rejected", "Rejected from admin pricing dashboard.")
    flash(f"Payment rejected for {booking_number}." if payment else "Payment record not found.")
    return redirect(url_for("admin.pricing_dashboard"))


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

def _qr_data_uri(invoice_url):
    try:
        import qrcode
        img = qrcode.make(invoice_url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        safe_url = quote_plus(invoice_url)
        return f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={safe_url}"

@admin_bp.route("/invoices/create", methods=["GET", "POST"])
def create_invoice():
    if request.method == "POST":
        document_type = request.form.get("document_type", "INVOICE").strip().upper()
        code = _tarasi_doc_code(document_type)

        amount = float(request.form.get("amount") or 0)
        discount = float(request.form.get("discount") or 0)
        vat_percent = float(request.form.get("vat") or 15)

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
            "prepared_by": request.form.get("prepared_by", "Tarasi Operations").strip() or "Tarasi Operations",
            "notes": request.form.get("notes", "").strip(),
            "amount": amount,
            "subtotal": amount,
            "discount": discount,
            "vat_percent": vat_percent,
            "vat_amount": vat_amount,
            "final_total": final_total,
            "qr_url": invoice_url,
            "qr_data": _qr_data_uri(invoice_url),
        }

        return render_template("admin/invoice_view.html", invoice=invoice)

    return render_template(
        "admin/invoice_create.html",
        admin_shell=get_admin_shell("invoices")
    )


@admin_bp.route("/support/live")
def live_support_dashboard():
    chats = get_open_support_chats()
    return _render_admin("admin/live_support.html", "support", chats=chats)


@admin_bp.route("/support/live/<chat_number>")
def live_support_room(chat_number: str):
    chat = get_support_chat(chat_number)
    if not chat:
        flash("Support chat not found.")
        return redirect(url_for("admin.live_support_dashboard"))
        
    messages = get_chat_messages(chat["id"])
    return _render_admin("admin/live_support_room.html", "support", chat=chat, messages=messages)


@admin_bp.route("/support/chat/<chat_number>/join", methods=["POST"])
def admin_join_support_chat(chat_number: str):
    admin_name = request.form.get("admin_name") or session.get("user_name") or "Tarasi Admin"
    if admin_join_chat(chat_number, admin_name):
        flash(f"Joined chat {chat_number}")
    else:
        flash("Could not join chat.")
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/support/chat/<chat_number>/message", methods=["POST"])
def admin_post_support_message(chat_number: str):
    chat = get_support_chat(chat_number)
    if not chat:
        return jsonify({"ok": False, "error": "Chat not found"}), 404
        
    message = request.form.get("message") or request.get_json(silent=True).get("message")
    admin_name = session.get("user_name") or "Tarasi Admin"
    
    if not message:
        return jsonify({"ok": False, "error": "Message required"}), 400
        
    msg = save_support_message(chat["id"], "admin", admin_name, message)
    
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "message": msg})
        
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/support/chat/<chat_number>/close", methods=["POST"])
def admin_close_support_chat(chat_number: str):
    if close_chat(chat_number):
        flash(f"Chat {chat_number} closed.")
    else:
        flash("Could not close chat.")
    return redirect(url_for("admin.live_support_dashboard"))


@admin_bp.route("/support/chat/<chat_number>/release-bot", methods=["POST"])
def admin_release_support_to_bot(chat_number: str):
    if release_to_bot(chat_number):
        flash(f"Released chat {chat_number} back to bot.")
    else:
        flash("Could not release chat.")
    return redirect(url_for("admin.live_support_room", chat_number=chat_number))


@admin_bp.route("/api/notifications")
def admin_get_notifications():
    return jsonify({"notifications": get_unread_notifications()})


@admin_bp.route("/api/notifications/<notification_id>/read", methods=["POST"])
def admin_mark_notification_read(notification_id: str):
    mark_notification_read(notification_id)
    return jsonify({"ok": True})


@admin_bp.route("/bot/knowledge")
def bot_knowledge():
    items = get_active_knowledge()
    return _render_admin("admin/bot_knowledge.html", "bot_os", items=items)


@admin_bp.route("/bot/knowledge/create", methods=["POST"])
def bot_knowledge_create():
    payload = {
        "title": request.form.get("title"),
        "category": request.form.get("category"),
        "keywords": [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()],
        "content": request.form.get("content"),
        "priority": request.form.get("priority", 5),
        "created_by": session.get("user_name") or "Admin",
    }
    create_knowledge_item(payload)
    flash("Knowledge item created.")
    return redirect(url_for("admin.bot_knowledge"))


@admin_bp.route("/bot/knowledge/<item_id>/update", methods=["POST"])
def bot_knowledge_update(item_id: str):
    payload = {
        "title": request.form.get("title"),
        "category": request.form.get("category"),
        "keywords": [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()],
        "content": request.form.get("content"),
        "priority": request.form.get("priority", 5),
    }
    update_knowledge_item(item_id, payload)
    flash("Knowledge item updated.")
    return redirect(url_for("admin.bot_knowledge"))


@admin_bp.route("/bot/knowledge/<item_id>/deactivate", methods=["POST"])
def bot_knowledge_deactivate(item_id: str):
    deactivate_knowledge_item(item_id)
    flash("Knowledge item deactivated.")
    return redirect(url_for("admin.bot_knowledge"))
