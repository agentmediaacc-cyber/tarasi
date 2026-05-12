from __future__ import annotations

from services.profile_service import get_profile, list_account_bookings, list_saved_routes, list_support_tickets


def profile_snapshot():
    return {
        "profile": get_profile(),
        "bookings": list_account_bookings(),
        "saved_routes": list_saved_routes(),
        "support_tickets": list_support_tickets(),
    }
