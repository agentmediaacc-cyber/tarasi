from __future__ import annotations
from flask import Blueprint, render_template, jsonify
from services.admin_control_service import get_admin_control_context
from services.admin_service import get_admin_shell

from services.auth_service import require_admin

admin_control_bp = Blueprint("admin_control", __name__)

@admin_control_bp.route("/admin/control")
@admin_control_bp.route("/admin/executive")
@require_admin
def executive_control():
    context = get_admin_control_context()
    context["admin_shell"] = get_admin_shell("dashboard")
    return render_template("admin/executive_control.html", **context)

@admin_control_bp.route("/api/admin/control/summary")
@require_admin
def executive_control_summary():
    return jsonify({"ok": True, **get_admin_control_context()})
