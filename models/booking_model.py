from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BookingModel:
    reference: str
    booking_type: str
    customer_name: str
    phone: str
    email: str = ""
    pickup_location: str = ""
    dropoff_location: str = ""
    status: str = "Booking received"
    metadata: dict[str, Any] = field(default_factory=dict)
