from __future__ import annotations

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from services.auth_service import current_user, establish_oauth_session, get_login_redirect, get_oauth_redirect, login_user, logout_user, register_user, require_auth
from services.booking_service import list_bookings
from services.db_service import get_db_status
from services.profile_service import get_profile
from services.supabase_service import get_supabase_config_status, get_supabase_health


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            ok, message = register_user(request.form.to_dict())
            flash(message)
            return redirect(url_for("auth.dashboard" if ok and current_user() else "auth.login"))
        except Exception as exc:  # pragma: no cover - integration safety
            flash(f"Registration failed: {exc}")
    return render_template("auth/register.html", supabase_status=get_supabase_config_status(), supabase_health=get_supabase_health())


@auth_bp.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        print("[LOGIN DEBUG] form=", dict(request.form))

        email = str(
            request.form.get("email")
            or request.form.get("login")
            or request.form.get("username")
            or ""
        ).lower().strip()

        password = str(
            request.form.get("password")
            or request.form.get("user_password")
            or request.form.get("pass")
            or ""
        )

        print("[LOGIN DEBUG] email=", email)
        print("[LOGIN DEBUG] password length=", len(password))

        ok, message = login_user(email, password)
        user = current_user()

        print("[LOGIN DEBUG] ok=", ok)
        print("[LOGIN DEBUG] message=", message)
        print("[LOGIN DEBUG] user=", user)

        if ok and user:
            if user.get("is_admin") is True or user.get("account_type") == "Admin":
                print("[LOGIN DEBUG] redirect=/admin")
                return redirect("/admin")
            if user.get("account_type") == "Driver":
                print("[LOGIN DEBUG] redirect=/driver/dashboard")
                return redirect("/driver/dashboard")
            print("[LOGIN DEBUG] redirect=/dashboard")
            return redirect("/dashboard")

        flash(message or "Login failed.")
        return redirect(url_for("auth.login"))

    return render_template(
        "auth/login.html",
        supabase_status=get_supabase_config_status(),
        supabase_health=get_supabase_health()
    )


@auth_bp.route("/auth/logout")
def logout():
    _ok, message = logout_user()
    flash(message)
    return redirect(url_for("public.home"))


@auth_bp.route("/auth/google")
def oauth_google():
    try:
        return redirect(get_oauth_redirect("google", url_for("auth.auth_callback", _external=True)))
    except Exception as exc:
        flash(f"Google login is unavailable: {exc}")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/facebook")
def oauth_facebook():
    try:
        return redirect(get_oauth_redirect("facebook", url_for("auth.auth_callback", _external=True)))
    except Exception as exc:
        flash(f"Facebook login is unavailable: {exc}")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            ok, message = establish_oauth_session(
                payload.get("access_token", ""),
                payload.get("refresh_token"),
                payload.get("provider", "oauth"),
            )
            if not ok:
                return jsonify({"ok": False, "message": message}), 400
            return jsonify({"ok": True, "message": message, "redirect": get_login_redirect()})
        except Exception as exc:
            current_app.logger.exception("OAuth callback failed")
            return jsonify({"ok": False, "message": str(exc)}), 400
    error_message = request.args.get("error_description") or request.args.get("error")
    return render_template("auth/callback.html", error_message=error_message)


@auth_bp.route("/dashboard")
@require_auth
def dashboard():
    user = get_profile() or current_user()
    user_bookings = [item for item in list_bookings() if item.get("account_email") == user.get("email") or item.get("email") == user.get("email")]
    return render_template("dashboard.html", user=user, bookings=user_bookings[:6], db_status=get_db_status())
