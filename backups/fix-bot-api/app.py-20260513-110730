from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, send_from_directory, url_for

from routes import register_blueprints
from services.auth_service import current_user
from services.booking_service import BOOKING_STATUSES


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "tarasi-premium-secret-key")

    register_blueprints(app)

    @app.context_processor
    def inject_shell_context():
        return {
            "nav_links": [
                {"label": "Home", "href": url_for("public.home")},
                {"label": "Book", "href": url_for("booking.book_index")},
                {"label": "Routes", "href": url_for("public.routes_page")},
                {"label": "Fleet", "href": url_for("fleet.fleet_page")},
                {"label": "Tours", "href": url_for("tour.tours_page")},
                {"label": "Track", "href": url_for("track.track_index")},
                {"label": "Support", "href": url_for("support.support_page")},
            ],
            "current_user": current_user(),
            "is_authenticated": bool(current_user()),
            "booking_statuses": BOOKING_STATUSES,
        }

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", title="Page not found", message="The page you requested does not exist."), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", title="Something went wrong", message="Tarasi hit an unexpected issue. Please try again or contact support."), 500

    @app.route("/booking")
    def legacy_booking():
        return redirect(url_for("booking.book_index"))

    @app.route("/login")
    def legacy_login():
        return redirect(url_for("auth.login"))

    @app.route("/register")
    def legacy_register():
        return redirect(url_for("auth.register"))

    @app.route("/logout")
    def legacy_logout():
        return redirect(url_for("auth.logout"))

    @app.route("/contact")
    def legacy_contact():
        return redirect(url_for("support.support_page"))

    @app.route("/account")
    def legacy_account():
        return redirect(url_for("profile.account_bookings"))

    @app.route("/shuttles")
    def legacy_shuttles():
        return redirect(url_for("public.routes_page"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory("uploads", filename)

    return app


app = create_app()



if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
