from __future__ import annotations

import os
from typing import Any

from services.storage_service import load_json


MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "").strip()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "").strip()

ZONES_FILE = "tarasi_zones.json"
KNOWN_DISTANCES: dict[tuple[str, str], float] = {
    ("cbd / town", "hosea kutako airport"): 45,
    ("wanaheda", "hosea kutako airport"): 47,
    ("klein windhoek", "hosea kutako airport"): 43,
    ("cbd / town", "eros airport"): 7,
    ("windhoek", "swakopmund"): 360,
    ("windhoek", "walvis bay"): 395,
    ("windhoek", "sossusvlei"): 360,
    ("windhoek", "etosha"): 415,
    ("windhoek", "okahandja"): 70,
    ("windhoek", "otjiwarongo"): 250,
}


def normalise(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def load_zones() -> list[dict[str, Any]]:
    zones = load_json(ZONES_FILE, [])
    return zones if isinstance(zones, list) else []


def search_zones(query: str, limit: int = 8) -> list[dict[str, Any]]:
    probe = normalise(query)
    if not probe:
        return load_zones()[:limit]
    results = []
    for zone in load_zones():
        haystack = [zone.get("name", "")] + list(zone.get("aliases", []))
        if any(probe in normalise(item) for item in haystack if item):
            results.append(zone)
    return results[:limit]


def resolve_zone(text: str | None) -> dict[str, Any] | None:
    probe = normalise(text)
    if not probe:
        return None
    for zone in load_zones():
        names = [zone.get("name", "")] + list(zone.get("aliases", []))
        if any(normalise(item) in probe for item in names if item):
            return zone
    return None


def _known_distance_key(pickup: str, dropoff: str) -> tuple[str, str]:
    return normalise(pickup), normalise(dropoff)


def _known_distance(pickup: str, dropoff: str) -> float | None:
    key = _known_distance_key(pickup, dropoff)
    if key in KNOWN_DISTANCES:
        return KNOWN_DISTANCES[key]
    reversed_key = (key[1], key[0])
    return KNOWN_DISTANCES.get(reversed_key)


def _is_windhoek_zone(zone: dict[str, Any] | None, text: str) -> bool:
    if zone:
        return zone.get("name") != "Hosea Kutako Airport" and zone.get("name") != "Eros Airport"
    probe = normalise(text)
    return any(term in probe for term in ["windhoek", "klein windhoek", "wanaheda", "katutura", "cbd", "town", "eros"])


def _fallback_distance(pickup: str, dropoff: str, pickup_zone: dict[str, Any] | None, dropoff_zone: dict[str, Any] | None) -> tuple[float, str, list[str]]:
    notes: list[str] = []
    airport_distance = None
    if pickup_zone and dropoff_zone:
        if pickup_zone.get("zone_type") == "airport":
            airport_distance = dropoff_zone.get("airport_distance_hint")
        elif dropoff_zone.get("zone_type") == "airport":
            airport_distance = pickup_zone.get("airport_distance_hint")
    if airport_distance:
        notes.append("Estimated from zone airport distance hint. Exact street can refine the price.")
        return float(airport_distance), "medium", notes
    if _is_windhoek_zone(pickup_zone, pickup) and _is_windhoek_zone(dropoff_zone, dropoff):
        notes.append("Exact route is not in the known table yet. Tarasi estimated this as an in-town Windhoek trip.")
        return 12.0 if normalise(pickup) == normalise(dropoff) else 16.0, "low", notes
    notes.append("Exact route is not in the known table yet. Please send the exact street for a tighter estimate.")
    return 18.0, "low", notes


def _estimate_duration(distance_km: float, pickup_zone: dict[str, Any] | None, dropoff_zone: dict[str, Any] | None) -> int:
    if distance_km <= 20:
        average_speed = 32
    elif pickup_zone and dropoff_zone and (
        pickup_zone.get("zone_type") == "airport" or dropoff_zone.get("zone_type") == "airport"
    ):
        average_speed = 75
    elif distance_km >= 80:
        average_speed = 90
    else:
        average_speed = 65
    return max(15, int(round((distance_km / average_speed) * 60)))


def estimate_distance(pickup: str, dropoff: str) -> dict[str, Any]:
    pickup_zone = resolve_zone(pickup)
    dropoff_zone = resolve_zone(dropoff)
    distance = _known_distance(pickup, dropoff)
    notes: list[str] = []
    confidence = "high"
    if distance is None and pickup_zone and dropoff_zone:
        distance = _known_distance(pickup_zone.get("name", ""), dropoff_zone.get("name", ""))
    if distance is None:
        distance, confidence, notes = _fallback_distance(pickup, dropoff, pickup_zone, dropoff_zone)
    duration = _estimate_duration(float(distance), pickup_zone, dropoff_zone)
    return {
        "pickup_zone": pickup_zone.get("name") if pickup_zone else "",
        "dropoff_zone": dropoff_zone.get("name") if dropoff_zone else "",
        "pickup_zone_data": pickup_zone or {},
        "dropoff_zone_data": dropoff_zone or {},
        "distance_km": round(float(distance), 2),
        "duration_minutes": duration,
        "confidence": confidence,
        "notes": notes,
        "mode": "known_distance_table",
        "future_map_api_ready": bool(MAPBOX_TOKEN or GOOGLE_MAPS_API_KEY or OSRM_BASE_URL),
    }
