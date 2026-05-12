from __future__ import annotations

from services.booking_service import list_bookings


def driver_snapshot():
    bookings = list_bookings()
    return [item for item in bookings if item.get("status") in ["Driver assigned", "On the way", "Picked up", "Completed"]]
