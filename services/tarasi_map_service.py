from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search").strip()
OSRM_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org/route/v1/driving").strip()
USER_AGENT = os.getenv("TARASI_MAP_USER_AGENT", "Tarasi/1.0 (tarasishuttle@gmail.com)")
SSL_CONTEXT = ssl._create_unverified_context()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_from_importance(importance: Any) -> str:
    score = _safe_float(importance) or 0.0
    if score >= 0.6:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def _extract_area(address: dict[str, Any]) -> str:
    for key in ("suburb", "neighbourhood", "city_district", "quarter", "residential", "town", "city", "county"):
        value = str(address.get(key) or "").strip()
        if value:
            return value
    return ""


def _valid_namibia_lat(lat: float | None) -> bool:
    return lat is not None and -23.0 <= lat <= -17.0


def _valid_namibia_lng(lng: float | None) -> bool:
    return lng is not None and 11.0 <= lng <= 26.0


def _normalize_coords(coords: tuple[float, float] | None) -> tuple[float, float] | None:
    if not coords:
        return None
    first = _safe_float(coords[0])
    second = _safe_float(coords[1])
    if first is None or second is None:
        return None
    if _valid_namibia_lat(first) and _valid_namibia_lng(second):
        return first, second
    if _valid_namibia_lat(second) and _valid_namibia_lng(first):
        print("OSRM coordinate order looked swapped. Tarasi corrected it safely.")
        return second, first
    return None


def search_address(query: str, limit: int = 5) -> list[dict[str, Any]]:
    probe = str(query or "").strip()
    if not probe:
        return []
    params = {
        "q": f"{probe}, Namibia",
        "format": "jsonv2",
        "limit": str(max(1, min(limit, 8))),
        "addressdetails": "1",
        "countrycodes": "na",
    }
    request = Request(
        f"{NOMINATIM_URL}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=6, context=SSL_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Nominatim search failed: {exc}")
        return []

    results: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        address = item.get("address") or {}
        lat = _safe_float(item.get("lat"))
        lng = _safe_float(item.get("lon"))
        if lat is None or lng is None:
            continue
        results.append(
            {
                "display_name": item.get("display_name") or probe,
                "lat": lat,
                "lng": lng,
                "lon": lng,
                "suburb_area": _extract_area(address),
                "confidence": _confidence_from_importance(item.get("importance")),
                "importance": _safe_float(item.get("importance")) or 0.0,
                "address": address,
                "type": item.get("type") or "",
            }
        )
    return results


def geocode_address(query: str) -> dict[str, Any] | None:
    results = search_address(query, limit=1)
    return results[0] if results else None


def get_route(start_coords: tuple[float, float], end_coords: tuple[float, float]) -> dict[str, Any] | None:
    start = _normalize_coords(start_coords)
    end = _normalize_coords(end_coords)
    if not start or not end:
        return {
            "distance_km": 0.0,
            "duration_minutes": 0.0,
            "confidence": "low",
            "notes": ["Invalid Namibia coordinates were supplied for route lookup."],
        }
    start_lat, start_lng = start
    end_lat, end_lng = end
    coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
    params = {"overview": "false", "steps": "false", "alternatives": "false"}
    request = Request(
        f"{OSRM_URL}/{coords}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=8, context=SSL_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        routes = payload.get("routes") or []
        if payload.get("code") != "Ok" or not routes:
            return None
        route = routes[0]
        return {
            "distance_km": round(float(route.get("distance") or 0) / 1000, 2),
            "duration_minutes": round(float(route.get("duration") or 0) / 60, 1),
            "confidence": "high",
            "notes": [],
        }
    except Exception as exc:
        print(f"OSRM route failed: {exc}")
        return None


def reverse_geocode(lat: float, lng: float) -> dict[str, Any] | None:
    params = {
        "lat": str(lat),
        "lon": str(lng),
        "format": "jsonv2",
        "addressdetails": "1",
    }
    request = Request(
        f"https://nominatim.openstreetmap.org/reverse?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=6, context=SSL_CONTEXT) as response:
            item = json.loads(response.read().decode("utf-8"))
        if not item or "error" in item:
            return None
        address = item.get("address") or {}
        return {
            "display_name": item.get("display_name") or "Unknown location",
            "lat": _safe_float(item.get("lat")),
            "lng": _safe_float(item.get("lon")),
            "lon": _safe_float(item.get("lon")),
            "suburb_area": _extract_area(address),
            "address": address,
            "type": item.get("type") or "",
        }
    except Exception as exc:
        print(f"Nominatim reverse failed: {exc}")
        return None
