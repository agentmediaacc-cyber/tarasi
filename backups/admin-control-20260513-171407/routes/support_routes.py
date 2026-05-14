from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.db_service import fetch_rows, insert_row, resolve_table_name
from services.storage_service import load_json, save_json


support_bp = Blueprint("support", __name__)


def _json_tickets() -> list[dict]:
    rows = load_json("support_tickets.json", [])
    return rows if isinstance(rows, list) else []


@support_bp.route("/support", methods=["GET", "POST"])
def support_page():
    if request.method == "POST":
        payload = {
            "name": request.form.get("full_name") or request.form.get("name", ""),
            "phone": request.form.get("phone", ""),
            "email": request.form.get("email", ""),
            "category": request.form.get("issue_type") or request.form.get("category", "Support"),
            "message": request.form.get("message", ""),
            "status": "open",
            "created_at": datetime.now().isoformat(),
        }
        if resolve_table_name("support_tickets"):
            created = insert_row("support_tickets", payload)
            if created:
                flash("Support request sent.")
                return redirect(url_for("support.support_page"))
        tickets = _json_tickets()
        tickets.append(payload)
        save_json("support_tickets.json", tickets)
        flash("Support request sent.")
        return redirect(url_for("support.support_page"))

    tickets = fetch_rows("support_tickets", limit=12)
    if not tickets:
        tickets = _json_tickets()[:12]
    return render_template("support/index.html", tickets=tickets)
