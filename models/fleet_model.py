from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FleetModel:
    name: str
    vehicle_type: str
    seats: int = 0
    status: str = "available"
