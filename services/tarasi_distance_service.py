from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt
from typing import Any

from services.db_service import fetch_rows, get_database_mode, resolve_table_name
from services.storage_service import load_json
from services.tarasi_map_service import get_route


ZONES_FILE = "tarasi_zones.json"
KNOWN_DISTANCES: dict[tuple[str, str], float] = {
    ("wanaheda", "grove mall"): 8.5,
    ("katutura", "maerua mall"): 9.2,
    ("cbd", "eros airport"): 6.8,
    ("wanaheda", "hosea kutako airport"): 46.5,
    ("klein windhoek", "grove mall"): 5.7,
    ("cbd / town", "hosea kutako airport"): 45.0,
    ("windhoek cbd", "hosea kutako airport"): 45.0,
    ("katutura", "eros airport"): 10.5,
}


def normalise(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * earth_radius * asin(sqrt(a))


def load_zones() -> list[dict[str, Any]]:
    if get_database_mode() in {"neon", "supabase"} and resolve_table_name("pricing_zones"):
        rows = fetch_rows("pricing_zones", filters={"is_active": True}, limit=200, order_by="zone_name asc")
        if rows:
            normalized: list[dict[str, Any]] = []
            for row in rows:
                zone_name = str(row.get("zone_name") or row.get("name") or "").strip()
                suburb_area = str(row.get("suburb_area") or "").strip()
                row_aliases = row.get("aliases")
                if isinstance(row_aliases, str):
                    try:
                        row_aliases = json.loads(row_aliases)
                    except Exception:
                        row_aliases = []
                aliases = [zone_name, suburb_area] + (row_aliases if isinstance(row_aliases, list) else [])
                normalized.append(
                    {
                        "id": row.get("id"),
                        "name": zone_name,
                        "aliases": [item for item in aliases if item],
                        "zone_type": "airport" if "airport" in normalise(f"{zone_name} {suburb_area}") else "city",
                        "latitude": _safe_float(row.get("latitude")),
                        "longitude": _safe_float(row.get("longitude")),
                        "map_radius_km": _safe_float(row.get("map_radius_km")) or 0.0,
                        "base_fare": _safe_float(row.get("base_fare")) or 0.0,
                        "price_per_km": _safe_float(row.get("price_per_km")) or 0.0,
                        "airport_fee": _safe_float(row.get("airport_fee")) or 0.0,
                        "minimum_fare": _safe_float(row.get("minimum_fare")) or 0.0,
                        "night_fee": _safe_float(row.get("night_fee")) or 0.0,
                        "luggage_fee": _safe_float(row.get("luggage_fee")) or 0.0,
                        "waiting_fee": _safe_float(row.get("waiting_fee")) or 0.0,
                        "raw": row,
                    }
                )
            return normalized
    rows = load_json(ZONES_FILE, [])
    return rows if isinstance(rows, list) else []


def search_zones(query: str, limit: int = 8) -> list[dict[str, Any]]:
    probe = normalise(query)
    rows = []
    for zone in load_zones():
        haystack = " ".join([zone.get("name", "")] + list(zone.get("aliases", [])))
        if not probe or probe in normalise(haystack):
            rows.append(zone)
        if len(rows) >= limit:
            break
    return rows


def match_zone(text: str | None = None, lat: float | None = None, lng: float | None = None) -> dict[str, Any] | None:
    probe = normalise(text)
    best: tuple[int, float, dict[str, Any]] | None = None
    nearest: tuple[float, dict[str, Any]] | None = None
    for zone in load_zones():
        zone_lat = _safe_float(zone.get("latitude"))
        zone_lng = _safe_float(zone.get("longitude"))
        radius = _safe_float(zone.get("map_radius_km")) or 0.0
        if probe:
            zone_name = normalise(zone.get("name", ""))
            suburb = normalise(zone.get("raw", {}).get("suburb_area") if isinstance(zone.get("raw"), dict) else zone.get("suburb_area", ""))
            alias_names = [normalise(item) for item in zone.get("aliases", []) if normalise(item)]
            if zone_name and probe == zone_name:
                candidate = (6, float(len(zone_name)), {**zone, "matched_by": "zone_name", "match_confidence": "high"})
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
            elif suburb and probe == suburb:
                candidate = (5, float(len(suburb)), {**zone, "matched_by": "suburb_area", "match_confidence": "high"})
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
            else:
                for hay in alias_names:
                    if probe == hay:
                        candidate = (4, float(len(hay)), {**zone, "matched_by": "alias_exact", "match_confidence": "high"})
                        if best is None or candidate[:2] > best[:2]:
                            best = candidate
                    elif hay and (hay in probe or probe in hay):
                        candidate = (3, float(len(hay)), {**zone, "matched_by": "alias_partial", "match_confidence": "medium"})
                        if best is None or candidate[:2] > best[:2]:
                            best = candidate
                if zone_name and (zone_name in probe or probe in zone_name):
                    candidate = (3, float(len(zone_name)), {**zone, "matched_by": "zone_partial", "match_confidence": "medium"})
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
                elif suburb and (suburb in probe or probe in suburb):
                    candidate = (3, float(len(suburb)), {**zone, "matched_by": "suburb_partial", "match_confidence": "medium"})
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
        if lat is not None and lng is not None and zone_lat is not None and zone_lng is not None and radius > 0:
            distance = _haversine_km(lat, lng, zone_lat, zone_lng)
            if distance <= radius:
                candidate = (2, radius - distance, {**zone, "matched_by": "radius", "match_confidence": "medium", "distance_to_center_km": round(distance, 2)})
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
            if nearest is None or distance < nearest[0]:
                nearest = (distance, zone)
    if best:
        return best[2]
    if nearest:
        return {**nearest[1], "matched_by": "nearest_zone", "match_confidence": "low", "distance_to_center_km": round(nearest[0], 2)}
    return None


def resolve_zone(text: str | None, coords: tuple[float, float] | None = None) -> dict[str, Any] | None:
    lat = coords[0] if coords else None
    lng = coords[1] if coords else None
    return match_zone(text=text, lat=lat, lng=lng)


def _known_distance(pickup: str, dropoff: str) -> float | None:
    key = (normalise(pickup), normalise(dropoff))
    if key in KNOWN_DISTANCES:
        return KNOWN_DISTANCES[key]
    reverse_key = (key[1], key[0])
    return KNOWN_DISTANCES.get(reverse_key)


def _zone_center_distance(pickup_zone: dict[str, Any] | None, dropoff_zone: dict[str, Any] | None) -> float | None:
    if not pickup_zone or not dropoff_zone:
        return None
    lat1 = _safe_float(pickup_zone.get("latitude"))
    lng1 = _safe_float(pickup_zone.get("longitude"))
    lat2 = _safe_float(dropoff_zone.get("latitude"))
    lng2 = _safe_float(dropoff_zone.get("longitude"))
    if None in {lat1, lng1, lat2, lng2}:
        return None
    # Light road factor to move from straight-line to city-road estimate.
    return round(_haversine_km(lat1, lng1, lat2, lng2) * 1.18, 2)


def _estimate_duration(distance_km: float) -> int:
    if distance_km <= 12:
        speed = 28.0
    elif distance_km <= 60:
        speed = 55.0
    else:
        speed = 78.0
    return max(8, int(round((distance_km / speed) * 60)))


def estimate_distance(
    pickup: str,
    dropoff: str,
    pickup_coords: tuple[float, float] | None = None,
    dropoff_coords: tuple[float, float] | None = None,
) -> dict[str, Any]:
    pickup_zone = resolve_zone(pickup, pickup_coords)
    dropoff_zone = resolve_zone(dropoff, dropoff_coords)
    notes: list[str] = []

    if pickup_coords and dropoff_coords:
        route = get_route(pickup_coords, dropoff_coords)
        if route and float(route.get("distance_km") or 0) > 0:
            return {
                "pickup_zone": pickup_zone.get("name") if pickup_zone else "",
                "dropoff_zone": dropoff_zone.get("name") if dropoff_zone else "",
                "pickup_zone_data": pickup_zone or {},
                "dropoff_zone_data": dropoff_zone or {},
                "distance_km": round(float(route["distance_km"]), 2),
                "duration_minutes": int(round(float(route["duration_minutes"]))),
                "confidence": "high" if pickup_zone and dropoff_zone else "medium",
                "notes": route.get("notes", []),
                "mode": "osrm_route",
            }
        notes.extend((route or {}).get("notes", []))
        notes.append("OSRM route lookup failed. Tarasi used zone-based distance fallback.")

    zone_distance = _zone_center_distance(pickup_zone, dropoff_zone)
    if zone_distance is not None and zone_distance > 0:
        confidence = "medium"
        low_confidence_matches = {"radius", "nearest_zone"}
        if (pickup_zone or {}).get("matched_by") in low_confidence_matches or (dropoff_zone or {}).get("matched_by") in low_confidence_matches:
            confidence = "low"
            notes.append("Closest mapped zone was used because the exact street could not be confirmed.")
        return {
            "pickup_zone": pickup_zone.get("name") if pickup_zone else "",
            "dropoff_zone": dropoff_zone.get("name") if dropoff_zone else "",
            "pickup_zone_data": pickup_zone or {},
            "dropoff_zone_data": dropoff_zone or {},
            "distance_km": round(zone_distance, 2),
            "duration_minutes": _estimate_duration(zone_distance),
            "confidence": confidence,
            "notes": notes,
            "mode": "zone_distance",
        }

    known_distance = _known_distance(pickup, dropoff)
    if known_distance is not None:
        return {
            "pickup_zone": pickup_zone.get("name") if pickup_zone else "",
            "dropoff_zone": dropoff_zone.get("name") if dropoff_zone else "",
            "pickup_zone_data": pickup_zone or {},
            "dropoff_zone_data": dropoff_zone or {},
            "distance_km": round(known_distance, 2),
            "duration_minutes": _estimate_duration(known_distance),
            "confidence": "low",
            "notes": notes + ["Known route distance fallback was used because live map routing was unavailable."],
            "mode": "known_distance",
        }

    return {
        "pickup_zone": pickup_zone.get("name") if pickup_zone else "",
        "dropoff_zone": dropoff_zone.get("name") if dropoff_zone else "",
        "pickup_zone_data": pickup_zone or {},
        "dropoff_zone_data": dropoff_zone or {},
        "distance_km": 0.0,
        "duration_minutes": 0,
        "confidence": "low",
        "notes": notes + ["No route distance could be confirmed from map or zone data."],
        "mode": "unresolved",
    }
