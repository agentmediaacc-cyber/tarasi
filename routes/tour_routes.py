from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for

from services.homepage_service import EMPTY_STATE_MESSAGE, get_featured_tours


tour_bp = Blueprint("tour", __name__)


@tour_bp.route("/tours")
def tours_page():
    return render_template("tours/index.html", tours=get_featured_tours(limit=20), empty_state_message=EMPTY_STATE_MESSAGE)


@tour_bp.route("/tour/<slug>")
def tour_detail(slug: str):
    tours = get_featured_tours(limit=50)
    tour = next((item for item in tours if item.get("slug") == slug), None)
    if not tour:
        flash("Tour not found.")
        return redirect(url_for("tour.tours_page"))
    return render_template("tours/detail.html", tour=tour)
