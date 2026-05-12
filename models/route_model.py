from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RouteModel:
    pickup: str
    dropoff: str
    base_price: str = ""
    route_type: str = ""
