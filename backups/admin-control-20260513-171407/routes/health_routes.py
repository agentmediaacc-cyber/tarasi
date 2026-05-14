from __future__ import annotations

from flask import Blueprint, jsonify

from services.db_service import get_db_status
from services.supabase_service import get_supabase_health


health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.route("/db")
def db_health():
    return jsonify(get_db_status())


@health_bp.route("/supabase")
def supabase_health():
    return jsonify(get_supabase_health())
