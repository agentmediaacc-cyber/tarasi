from __future__ import annotations
from services.route_service import get_live_routes
import logging
import time

from flask import Blueprint, render_template

from services.homepage_service import (
    EMPTY_STATE_MESSAGE,
    get_category_services,
    get_homepage_payload,
)
from services.pricing_service import DEFAULT_MAP_CENTER, list_routes


public_bp = Blueprint("public", __name__)
logger = logging.getLogger(__name__)

CATEGORY_CONFIG = {
    "transport": {"title": "Ride", "description": "Once-off shuttle and everyday point-to-point rides.", "cta": "/book/once-off"},
    "airport": {"title": "Airport Transfer", "description": "Airport arrivals and departures across Namibia.", "cta": "/book/airport"},
    "school": {"title": "School Transport", "description": "Safe recurring school pickup and drop-off.", "cta": "/book/school"},
    "monthly": {"title": "Monthly Transport", "description": "Recurring family and staff transport plans.", "cta": "/book/monthly"},
    "vip": {"title": "VIP / Private Hire", "description": "Executive and private full-day transport.", "cta": "/book/vip"},
    "business": {"title": "Business Transport", "description": "Staff movement and corporate bookings.", "cta": "/book/business"},
    "tours": {"title": "Tours", "description": "Tourist routes and travel transfer packages.", "cta": "/tours"},
}


@public_bp.route("/routes")
def routes_page():
    route_data = get_live_routes()
    return render_template(
        "routes_premium_real.html",
        routes=route_data.get("routes", []),
        route_count=route_data.get("count", 0),
        route_source=route_data.get("source", ""),
        route_message=route_data.get("message", ""),
    )


@public_bp.route("/")
def home():
    return render_template("index.html")
