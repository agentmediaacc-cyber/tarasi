from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from services.profile_service import get_profile_dashboard, update_user_profile
from services.booking_service import get_booking_for_email, list_bookings

profile_bp = Blueprint("profile", __name__)

def login_required():
    if not session.get("user_email") and not session.get("user_id"):
        return False
    return True


def _render_profile(template_name, active_tab, **context):
    dashboard = context.get("dashboard") or get_profile_dashboard(session)
    context["dashboard"] = dashboard
    context["active_tab"] = active_tab
    return render_template(template_name, **context)

@profile_bp.route("/profile")
def profile():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))

    return _render_profile("profile/premium_dashboard.html", "dashboard")

@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@profile_bp.route("/profile/settings", methods=["GET", "POST"])
def edit_profile():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))

    dashboard = get_profile_dashboard(session)

    if request.method == "POST":
        payload = {
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "town": request.form.get("town", "").strip(),
            "region": request.form.get("region", "").strip(),
            "language": request.form.get("language", "").strip(),
            "emergency_contact": request.form.get("emergency_contact", "").strip(),
            "preferred_vehicle": request.form.get("preferred_vehicle", "").strip(),
            "quiet_ride": request.form.get("quiet_ride", "").strip(),
            "accessibility_needs": request.form.get("accessibility_needs", "").strip(),
        }
        update_user_profile(session, payload)
        flash("Profile updated successfully.")
        return redirect(url_for("profile.profile"))

    return _render_profile("profile/edit_premium.html", "settings", dashboard=dashboard)

@profile_bp.route("/account/bookings")
def account_bookings():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))

    user_email = session.get("user_email", "")
    bookings = [
        b for b in list_bookings()
        if not user_email or b.get("email") == user_email or b.get("user_email") == user_email
    ]

    status_filter = request.args.get("status", "all")
    active_statuses = {"booking_received", "confirmed", "driver_assigned", "on_the_way", "arrived", "picked_up"}
    if status_filter == "active":
        bookings = [b for b in bookings if str(b.get("status", "")).lower().replace(" ", "_") in active_statuses]
    elif status_filter != "all":
        bookings = [b for b in bookings if str(b.get("status", "")).lower().replace(" ", "_") == status_filter]

    dashboard = get_profile_dashboard(session)
    return _render_profile(
        "profile/bookings.html",
        "trips",
        bookings=bookings,
        status_filter=status_filter,
        profile=dashboard.get("profile"),
        dashboard=dashboard,
    )


@profile_bp.route("/account/bookings/<reference>")
def account_booking_detail(reference: str):
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    user_email = session.get("user_email", "")
    booking = get_booking_for_email(reference, user_email) if user_email else None
    dashboard = get_profile_dashboard(session)
    return _render_profile(
        "profile/booking_detail.html",
        "trips",
        booking=booking,
        not_found=booking is None,
        dashboard=dashboard,
    ), (404 if booking is None else 200)

@profile_bp.route("/profile/saved-places")
def saved_places():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/saved_places.html", "saved_places")

@profile_bp.route("/profile/wallet")
def wallet():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/wallet.html", "wallet")

@profile_bp.route("/profile/loyalty")
def loyalty():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/loyalty.html", "loyalty")

@profile_bp.route("/profile/documents")
def documents():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/documents.html", "documents")

@profile_bp.route("/profile/notifications")
def notifications():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    
    from services.notification_service import list_user_notifications
    user_email = session.get("user_email") or ""
    user_notifications = list_user_notifications(user_email)
    
    return _render_profile("profile/notifications.html", "notifications", user_notifications=user_notifications)

@profile_bp.route("/profile/notifications/<id>/read")
def mark_read(id: str):
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    
    from services.notification_service import mark_notification_read
    mark_notification_read(id)
    return redirect(url_for("profile.notifications"))

@profile_bp.route("/profile/notifications/read-all")
def mark_all_as_read():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    
    from services.notification_service import mark_all_read
    user_email = session.get("user_email") or ""
    mark_all_read(user_email)
    return redirect(url_for("profile.notifications"))

@profile_bp.route("/profile/safety")
def safety():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/safety.html", "safety")

@profile_bp.route("/profile/referrals")
def referrals():
    if not login_required():
        return redirect(url_for("auth.login", next=request.path))
    return _render_profile("profile/referrals.html", "referrals")
