from __future__ import annotations

from services.booking_service import get_booking, list_bookings


def booking_snapshot(reference: str | None = None):
    if reference:
        return get_booking(reference)
    return list_bookings()
