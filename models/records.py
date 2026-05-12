from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserProfileRecord:
    id: str | None = None
    full_name: str = ""
    email: str = ""
    phone: str = ""
    account_type: str = "Customer"
    provider: str = "email"


@dataclass
class BookingRecord:
    reference: str
    booking_type: str
    full_name: str
    phone: str
    pickup: str
    dropoff: str
    date: str
    time: str
    status: str = "Booking received"
    amount: str = "Quote required"
    metadata: dict = field(default_factory=dict)
