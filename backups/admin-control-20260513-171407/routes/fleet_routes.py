from __future__ import annotations

from flask import Blueprint, render_template

from services.homepage_service import EMPTY_STATE_MESSAGE, get_featured_fleet


fleet_bp = Blueprint("fleet", __name__)


@fleet_bp.route("/fleet")
def fleet_page():
    return render_template("fleet/index.html", cars=get_featured_fleet(limit=20), empty_state_message=EMPTY_STATE_MESSAGE)
