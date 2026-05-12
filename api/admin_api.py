from __future__ import annotations

from services.booking_service import list_bookings
from services.db_service import fetch_rows, get_db_status


def admin_snapshot():
    return {
        "db_status": get_db_status(),
        "bookings": list_bookings(),
        "routes": fetch_rows("routes", limit=20),
        "fleet": fetch_rows("fleet", limit=20),
        "tours": fetch_rows("tours", limit=20),
        "support": fetch_rows("support_tickets", limit=20),
    }
