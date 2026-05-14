from __future__ import annotations

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


@public_bp.route("/")
def home():
    start = time.perf_counter()
    payload = get_homepage_payload()
    response = render_template("public/home.html", **payload)
    logger.debug("public.home render_time_ms=%.2f", (time.perf_counter() - start) * 1000)
    return response


@public_bp.route("/routes")
@public_bp.route("/routes/pricing")
def routes_page():
    routes = list_routes()
    return render_template(
        "public/routes.html",
        routes=routes,
        map_center=DEFAULT_MAP_CENTER,
        empty_state_message=EMPTY_STATE_MESSAGE,
    )


@public_bp.route("/service/<service_type>")
@public_bp.route("/services/<service_type>")
def service_category(service_type: str):
    category = CATEGORY_CONFIG.get(service_type)
    items = get_category_services(service_type)
    return render_template(
        "services/category.html" if category and items else "services/empty.html",
        category_key=service_type,
        category=category,
        items=items,
        title=category["title"] if category else "Service not found",
        message=EMPTY_STATE_MESSAGE,
        empty_state_message=EMPTY_STATE_MESSAGE,
    ), (200 if category else 404)


@public_bp.route("/school-transport")
def school_transport():
    return render_template("public/service_landing.html", title="School transport", description="Safe school transport plans for families and guardians.", cta_href="/book/school", cta_label="Book school transport")


@public_bp.route("/monthly-plans")
def monthly_plans():
    return render_template("public/service_landing.html", title="Monthly transport", description="Recurring monthly shuttle plans for staff, families and private clients.", cta_href="/book/monthly", cta_label="Start monthly booking")
