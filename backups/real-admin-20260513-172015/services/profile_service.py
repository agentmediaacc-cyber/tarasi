from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from services.booking_service import list_bookings
from services.storage_service import load_json, save_json

PROFILE_FILE = "profiles.json"


def _email_from_session(session):
    return session.get("user_email") or session.get("email") or ""


def _default_profile(session):
    email = _email_from_session(session)
    name = session.get("user_name") or session.get("full_name") or email.split("@")[0].replace(".", " ").title()
    return {
        "full_name": name or "Tarasi Member",
        "email": email,
        "phone": session.get("phone", ""),
        "town": session.get("town", "Windhoek"),
        "region": session.get("region", "Khomas"),
        "language": "English",
        "member_since": datetime.now().strftime("%Y"),
        "verified": bool(email),
        "level": "Silver",
        "wallet_balance": "N$0.00",
        "loyalty_points": 0,
        "emergency_contact": "",
        "preferred_vehicle": "Toyota Quantum",
        "quiet_ride": "No preference",
        "accessibility_needs": "",
    }


def get_saved_profile(session):
    email = _email_from_session(session)
    profiles = load_json(PROFILE_FILE, [])
    if isinstance(profiles, list):
        for profile in profiles:
            if profile.get("email") == email and email:
                merged = _default_profile(session)
                merged.update(profile)
                return merged
    return _default_profile(session)


def update_user_profile(session, payload):
    email = _email_from_session(session)
    profiles = load_json(PROFILE_FILE, [])
    if not isinstance(profiles, list):
        profiles = []

    found = False
    for profile in profiles:
        if profile.get("email") == email and email:
            profile.update(payload)
            profile["email"] = email
            profile["updated_at"] = datetime.now().isoformat()
            found = True
            break

    if not found:
        profile = _default_profile(session)
        profile.update(payload)
        profile["email"] = email
        profile["created_at"] = datetime.now().isoformat()
        profiles.append(profile)

    save_json(PROFILE_FILE, profiles)
    return True


def _status_key(booking: dict[str, Any]) -> str:
    return str(booking.get("status", "")).lower().replace(" ", "_")


def _status_is(booking: dict[str, Any], values: list[str]) -> bool:
    return _status_key(booking) in values


def _parse_amount(value: Any) -> float:
    if value is None:
        return 0.0
    raw = str(value).strip()
    if not raw:
        return 0.0
    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch in {".", ","}).replace(",", "")
    try:
        return float(cleaned or 0)
    except ValueError:
        return 0.0


def _currency(amount: float) -> str:
    return f"N${amount:,.2f}"


def _safe_date(booking: dict[str, Any]) -> datetime:
    raw_date = str(booking.get("date", "")).strip()
    raw_time = str(booking.get("time", "")).strip() or "00:00"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{raw_date} {raw_time}", fmt)
        except ValueError:
            continue
    return datetime.max


def _profile_completion(profile: dict[str, Any]) -> dict[str, Any]:
    checks = [
        ("Full name", bool(profile.get("full_name"))),
        ("Phone", bool(profile.get("phone"))),
        ("Town", bool(profile.get("town"))),
        ("Region", bool(profile.get("region"))),
        ("Language", bool(profile.get("language"))),
        ("Emergency contact", bool(profile.get("emergency_contact"))),
        ("Preferred vehicle", bool(profile.get("preferred_vehicle"))),
        ("Accessibility notes", bool(profile.get("accessibility_needs"))),
    ]
    completed = sum(1 for _label, ok in checks if ok)
    percent = round((completed / len(checks)) * 100)
    missing = [label for label, ok in checks if not ok]
    return {
        "completed": completed,
        "total": len(checks),
        "percent": percent,
        "missing": missing,
    }


def _build_saved_places(profile: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": "Home", "address": profile.get("town", "Windhoek"), "icon": "Home", "symbol": "⌂"},
        {"label": "Airport", "address": "Hosea Kutako International Airport", "icon": "Airport", "symbol": "✈"},
        {"label": "Work", "address": "Add work address", "icon": "Work", "symbol": "◫"},
        {"label": "School", "address": "Add school address", "icon": "School", "symbol": "△"},
    ]


def _build_notifications(profile: dict[str, Any], active: list[dict[str, Any]], upcoming: list[dict[str, Any]]) -> list[dict[str, str]]:
    notes = [
        {
            "title": "Welcome to Tarasi Premium",
            "text": "Your premium mobility dashboard is active and ready for live trips, wallet tracking and VIP support.",
            "type": "Account",
            "time": "Just now",
        },
        {
            "title": "Profile completion boosts support speed",
            "text": "Add emergency contact, accessibility notes and favorite routes for faster dispatch decisions.",
            "type": "Tip",
            "time": "Today",
        },
    ]
    if active:
        ride = active[0]
        notes.insert(
            0,
            {
                "title": f"Ride {ride.get('reference', '')} is active",
                "text": f"{ride.get('pickup') or 'Pickup'} to {ride.get('dropoff') or 'Drop-off'} is currently in motion.",
                "type": "Trip",
                "time": "Live",
            },
        )
    elif upcoming:
        trip = upcoming[0]
        notes.insert(
            0,
            {
                "title": "Next trip is ready",
                "text": f"{trip.get('pickup') or 'Pickup'} to {trip.get('dropoff') or 'Drop-off'} is next in your travel queue.",
                "type": "Upcoming",
                "time": "Scheduled",
            },
        )
    if profile.get("emergency_contact"):
        notes.append(
            {
                "title": "Trusted contact synced",
                "text": "Your emergency contact is stored and available from the safety center.",
                "type": "Safety",
                "time": "Today",
            }
        )
    return notes


def _build_resources() -> list[dict[str, str]]:
    return [
        {"title": "My Bookings", "text": "View trips, requests and confirmations.", "endpoint": "profile.account_bookings", "icon": "▣"},
        {"title": "Saved Places", "text": "Home, work, school, hotel and airport.", "endpoint": "profile.saved_places", "icon": "⌂"},
        {"title": "Wallet", "text": "Payments, refunds and ride credits.", "endpoint": "profile.wallet", "icon": "◈"},
        {"title": "Loyalty", "text": "Points, VIP level and benefits.", "endpoint": "profile.loyalty", "icon": "◎"},
        {"title": "Documents", "text": "Travel, school and corporate documents.", "endpoint": "profile.documents", "icon": "▤"},
        {"title": "Notifications", "text": "Booking updates and support replies.", "endpoint": "profile.notifications", "icon": "◌"},
        {"title": "Safety", "text": "Emergency contact, SOS and trusted contacts.", "endpoint": "profile.safety", "icon": "▲"},
        {"title": "Referrals", "text": "Invite friends and earn rewards.", "endpoint": "profile.referrals", "icon": "◇"},
    ]


def _build_active_ride(active: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not active:
        return None
    booking = active[0]
    status = _status_key(booking)
    eta_map = {
        "booking_received": "Driver confirming soon",
        "confirmed": "18 min",
        "driver_assigned": "12 min",
        "on_the_way": "8 min",
        "arrived": "Driver has arrived",
        "picked_up": "En route to drop-off",
    }
    return {
        "reference": booking.get("reference"),
        "route": f"{booking.get('pickup') or 'Pickup'} to {booking.get('dropoff') or 'Drop-off'}",
        "status": booking.get("status", "Booking received"),
        "eta": eta_map.get(status, "Tracking available"),
        "driver": booking.get("driver_name") or "Tarasi chauffeur",
        "vehicle": booking.get("preferred_vehicle") or booking.get("car") or "Premium fleet vehicle",
        "date": booking.get("date") or "TBD",
        "time": booking.get("time") or "TBD",
        "passengers": booking.get("passengers") or "1",
    }


def _build_upcoming_trips(bookings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        booking for booking in bookings
        if not _status_is(booking, ["completed", "cancelled", "cancellation_requested"])
    ]
    return sorted(candidates, key=_safe_date)[:6]


def _build_quick_rebook(bookings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    rebook = []
    for booking in bookings:
        route = (booking.get("pickup"), booking.get("dropoff"))
        if route in seen or not all(route):
            continue
        seen.add(route)
        rebook.append(
            {
                "label": f"{booking.get('pickup')} to {booking.get('dropoff')}",
                "pickup": booking.get("pickup"),
                "dropoff": booking.get("dropoff"),
                "booking_type": booking.get("booking_type", "once-off").replace("-", " ").title(),
            }
        )
        if len(rebook) == 4:
            break
    return rebook


def _build_loyalty(profile: dict[str, Any], completed_count: int) -> dict[str, Any]:
    points = int(profile.get("loyalty_points") or 0)
    tier_thresholds = {"Silver": 250, "Gold": 600, "Platinum": 1200}
    current_tier = profile.get("level", "Silver")
    target = tier_thresholds.get(current_tier, 250)
    percent = min(100, round((points / target) * 100)) if target else 100
    return {
        "level": current_tier,
        "points": points,
        "target": target,
        "percent": percent,
        "next_level_hint": "Complete premium trips to unlock faster support and exclusive ride perks.",
        "completed_trips": completed_count,
    }


def _build_wallet(profile: dict[str, Any], completed: list[dict[str, Any]], bookings: list[dict[str, Any]]) -> dict[str, Any]:
    spend = sum(_parse_amount(booking.get("amount")) for booking in bookings)
    credits = completed[-3:] if completed else []
    email = profile.get("email")
    transactions = get_wallet_transactions(email) if email else []
    
    return {
        "balance": profile.get("wallet_balance", "N$0.00"),
        "ride_credits": _currency(len(completed) * 25.0),
        "coupon_count": max(1, min(4, len(bookings) // 2 or 1)),
        "rewards_value": _currency((profile.get("loyalty_points") or 0) * 0.15),
        "monthly_spend": _currency(spend),
        "recent_credit_routes": [item.get("route_summary") for item in credits if item.get("route_summary")],
        "transactions": transactions,
        "pending_refunds": _currency(sum(250 for b in bookings if b.get("refund_status") == "Requested"))
    }


def _build_trusted_contacts(profile: dict[str, Any]) -> list[dict[str, str]]:
    contacts = []
    if profile.get("emergency_contact"):
        contacts.append({"name": "Primary contact", "value": profile.get("emergency_contact"), "status": "Synced"})
    contacts.append({"name": "Tarasi safety desk", "value": "24/7 in-app support", "status": "Always on"})
    contacts.append({"name": "Share live trip", "value": "Available on active rides", "status": "Ready"})
    return contacts


def _build_saved_drivers(active: list[dict[str, Any]], completed: list[dict[str, Any]]) -> list[dict[str, str]]:
    drivers = []
    source = active + completed
    for booking in source:
        name = booking.get("driver_name") or "Tarasi chauffeur"
        if any(item["name"] == name for item in drivers):
            continue
        drivers.append(
            {
                "name": name,
                "vehicle": booking.get("preferred_vehicle") or booking.get("car") or "Premium vehicle",
                "rating": "4.9",
            }
        )
        if len(drivers) == 3:
            break
    if not drivers:
        drivers.append({"name": "Tarasi chauffeur", "vehicle": "Executive fleet", "rating": "4.9"})
    return drivers


def _build_favorite_routes(bookings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter()
    for booking in bookings:
        pickup = booking.get("pickup")
        dropoff = booking.get("dropoff")
        if pickup and dropoff:
            counts[f"{pickup} to {dropoff}"] += 1
    favorites = []
    for route, total in counts.most_common(3):
        favorites.append({"label": route, "count": total})
    if not favorites:
        favorites.append({"label": "Windhoek to Hosea Kutako International Airport", "count": 0})
    return favorites


def _build_spending_summary(bookings: list[dict[str, Any]], completed: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(_parse_amount(item.get("amount")) for item in bookings)
    completed_total = sum(_parse_amount(item.get("amount")) for item in completed)
    return {
        "total": _currency(total),
        "completed": _currency(completed_total),
        "average": _currency(completed_total / len(completed)) if completed else _currency(0),
        "premium_share": f"{min(100, len(completed) * 12)}%",
    }


def _build_support_summary(email: str) -> dict[str, Any]:
    tickets = load_json("support_tickets.json", [])
    if not isinstance(tickets, list):
        tickets = []
    user_tickets = [
        ticket for ticket in tickets
        if not email or ticket.get("email") == email or ticket.get("user_email") == email
    ]
    open_count = sum(1 for ticket in user_tickets if str(ticket.get("status", "")).lower() == "open")
    return {
        "total": len(user_tickets),
        "open": open_count,
        "resolved": max(0, len(user_tickets) - open_count),
        "latest": user_tickets[:3],
    }


def _build_referral(profile: dict[str, Any], completed_count: int) -> dict[str, Any]:
    name = str(profile.get("full_name", "Tarasi Member")).strip()
    initials = "".join(part[:1] for part in name.split()[:2]).upper() or "TM"
    code = f"TARASI-{initials}{datetime.now().year}"
    return {
        "code": code,
        "earned": _currency(completed_count * 20.0),
        "rides_needed": max(0, 5 - completed_count),
    }


def _build_ride_history(bookings: list[dict[str, Any]], completed: list[dict[str, Any]]) -> dict[str, Any]:
    booking_types = Counter(item.get("booking_type", "once-off") for item in bookings)
    favorite_mode = booking_types.most_common(1)[0][0].replace("-", " ").title() if booking_types else "Once-Off"
    completion_rate = round((len(completed) / len(bookings)) * 100) if bookings else 0
    return {
        "favorite_mode": favorite_mode,
        "completion_rate": completion_rate,
        "total_routes": len({item.get("route_summary") for item in bookings if item.get("route_summary")}),
        "night_rides": max(0, len(bookings) // 3),
    }


def _build_app_navigation() -> dict[str, list[dict[str, str]]]:
    primary = [
        {"id": "dashboard", "label": "Dashboard", "endpoint": "profile.profile", "icon": "◉"},
        {"id": "trips", "label": "Trips", "endpoint": "profile.account_bookings", "icon": "▣"},
        {"id": "track", "label": "Track Ride", "endpoint": "track.track_index", "icon": "⌖"},
        {"id": "saved_places", "label": "Saved Places", "endpoint": "profile.saved_places", "icon": "⌂"},
        {"id": "wallet", "label": "Wallet", "endpoint": "profile.wallet", "icon": "◈"},
        {"id": "loyalty", "label": "Loyalty", "endpoint": "profile.loyalty", "icon": "◎"},
    ]
    secondary = [
        {"id": "notifications", "label": "Notifications", "endpoint": "profile.notifications", "icon": "◌"},
        {"id": "safety", "label": "Safety", "endpoint": "profile.safety", "icon": "▲"},
        {"id": "documents", "label": "Documents", "endpoint": "profile.documents", "icon": "▤"},
        {"id": "referrals", "label": "Referrals", "endpoint": "profile.referrals", "icon": "◇"},
        {"id": "support", "label": "Support", "endpoint": "support.support_page", "icon": "✦"},
        {"id": "settings", "label": "Settings", "endpoint": "profile.edit_profile", "icon": "☰"},
        {"id": "logout", "label": "Logout", "endpoint": "auth.logout", "icon": "↗"},
    ]
    mobile = [
        {"id": "dashboard", "label": "Dashboard", "endpoint": "profile.profile", "icon": "◉"},
        {"id": "trips", "label": "Trips", "endpoint": "profile.account_bookings", "icon": "▣"},
        {"id": "book", "label": "Book", "endpoint": "booking.book_index", "icon": "+"},
        {"id": "track", "label": "Track", "endpoint": "track.track_index", "icon": "⌖"},
        {"id": "wallet", "label": "Wallet", "endpoint": "profile.wallet", "icon": "◈"},
    ]
    quick_actions = [
        {"label": "Book Again", "endpoint": "booking.book_index", "icon": "↻"},
        {"label": "Track Current Ride", "endpoint": "track.track_index", "icon": "⌖"},
        {"label": "Emergency Support", "endpoint": "profile.safety", "icon": "!"},
    ]
    return {
        "primary": primary,
        "secondary": secondary,
        "mobile": mobile,
        "quick_actions": quick_actions,
    }


def get_profile_dashboard(session):
    profile = get_saved_profile(session)
    email = profile.get("email", "")

    bookings = [
        b for b in list_bookings()
        if not email or b.get("email") == email or b.get("user_email") == email
    ]

    active = [
        booking for booking in bookings
        if _status_is(booking, ["booking_received", "confirmed", "driver_assigned", "on_the_way", "arrived", "picked_up"])
    ]
    completed = [booking for booking in bookings if _status_is(booking, ["completed"])]
    cancelled = [booking for booking in bookings if _status_is(booking, ["cancelled"])]
    cancellation_requested = [booking for booking in bookings if _status_is(booking, ["cancellation_requested"])]
    upcoming = _build_upcoming_trips(bookings)
    saved_places = _build_saved_places(profile)
    notifications = _build_notifications(profile, active, upcoming)
    profile_completion = _profile_completion(profile)
    wallet = _build_wallet(profile, completed, bookings)
    loyalty = _build_loyalty(profile, len(completed))
    support_summary = _build_support_summary(email)
    app_navigation = _build_app_navigation()

    return {
        "profile": profile,
        "bookings": bookings,
        "active_bookings": active,
        "completed_bookings": completed,
        "cancelled_bookings": cancelled,
        "cancellation_requested": cancellation_requested,
        "latest_bookings": bookings[:5],
        "upcoming_trips": upcoming,
        "saved_places": saved_places,
        "notifications": notifications,
        "resources": _build_resources(),
        "active_ride": _build_active_ride(active),
        "quick_rebook": _build_quick_rebook(bookings),
        "loyalty": loyalty,
        "wallet": wallet,
        "profile_completion": profile_completion,
        "trusted_contacts": _build_trusted_contacts(profile),
        "saved_drivers": _build_saved_drivers(active, completed),
        "favorite_routes": _build_favorite_routes(bookings),
        "spending_summary": _build_spending_summary(bookings, completed),
        "support_summary": support_summary,
        "referral": _build_referral(profile, len(completed)),
        "ride_history": _build_ride_history(bookings, completed),
        "app_navigation": app_navigation,
        "stats": {
            "total": len(bookings),
            "active": len(active),
            "completed": len(completed),
            "cancelled": len(cancelled),
            "cancellation_requested": len(cancellation_requested),
            "saved_places": len(saved_places),
            "support_open": support_summary["open"],
        },
    }


def get_profile(session_or_email=None):
    if isinstance(session_or_email, dict):
        return get_saved_profile(session_or_email)

    fake_session = {"user_email": session_or_email or ""}
    return get_saved_profile(fake_session)


def list_account_bookings(session_or_email=None):
    if isinstance(session_or_email, dict):
        email = _email_from_session(session_or_email)
    else:
        email = session_or_email or ""

    bookings = list_bookings()
    if not email:
        return bookings

    return [
        b for b in bookings
        if b.get("email") == email or b.get("user_email") == email
    ]


def list_saved_routes(session_or_email=None):
    if isinstance(session_or_email, dict):
        dashboard = get_profile_dashboard(session_or_email)
    else:
        dashboard = get_profile_dashboard({"user_email": session_or_email or ""})
    return dashboard.get("saved_places", [])


def list_support_tickets(session_or_email=None):
    email = ""
    if isinstance(session_or_email, dict):
        email = _email_from_session(session_or_email)
    elif session_or_email:
        email = session_or_email

    tickets = load_json("support_tickets.json", [])
    if not isinstance(tickets, list):
        return []

    if not email:
        return tickets

    return [
        t for t in tickets
        if t.get("email") == email or t.get("user_email") == email
    ]

def get_wallet_transactions(email: str) -> list[dict[str, Any]]:
    transactions = load_json("wallet_transactions.json", [])
    if not isinstance(transactions, list):
        return []
    return [t for t in transactions if t.get("email") == email]

def add_wallet_transaction(email: str, amount: float, description: str, transaction_type: str = "credit") -> bool:
    transactions = load_json("wallet_transactions.json", [])
    if not isinstance(transactions, list):
        transactions = []
    
    transactions.append({
        "id": f"TXN-{int(time.time())}",
        "email": email,
        "amount": amount,
        "description": description,
        "type": transaction_type,
        "created_at": datetime.now().isoformat()
    })
    save_json("wallet_transactions.json", transactions)
    
    # Update balance in profile
    profiles = load_json(PROFILE_FILE, [])
    for p in profiles:
        if p.get("email") == email:
            current = _parse_amount(p.get("wallet_balance", "N/bin/bash.00"))
            new_balance = current + (amount if transaction_type == "credit" else -amount)
            p["wallet_balance"] = _currency(new_balance)
            break
    save_json(PROFILE_FILE, profiles)
    return True
