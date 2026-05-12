from __future__ import annotations

from typing import Any

from .db_service import fetch_rows, get_database_mode, get_db_status
from .storage_service import load_json

DEFAULT_MAP_CENTER = {"lat": -22.5609, "lng": 17.0658, "label": "Windhoek"}
NAMIBIA_TOWNS = {
    "windhoek": {"label": "Windhoek", "lat": -22.5609, "lng": 17.0658, "region": "Khomas"},
    "hosea kutako airport": {"label": "Hosea Kutako Airport", "lat": -22.4799, "lng": 17.4709, "region": "Khomas"},
    "hosea kutako international airport": {"label": "Hosea Kutako Airport", "lat": -22.4799, "lng": 17.4709, "region": "Khomas"},
    "swakopmund": {"label": "Swakopmund", "lat": -22.6784, "lng": 14.5266, "region": "Erongo"},
    "walvis bay": {"label": "Walvis Bay", "lat": -22.9576, "lng": 14.5053, "region": "Erongo"},
    "etosha": {"label": "Etosha", "lat": -19.2157, "lng": 15.9120, "region": "Oshikoto"},
    "sossusvlei": {"label": "Sossusvlei", "lat": -24.7282, "lng": 15.2993, "region": "Hardap"},
    "rundu": {"label": "Rundu", "lat": -17.9172, "lng": 19.7662, "region": "Kavango East"},
    "popa falls": {"label": "Popa Falls", "lat": -18.1195, "lng": 21.5815, "region": "Kavango East"},
    "luderitz": {"label": "Luderitz", "lat": -26.6481, "lng": 15.1594, "region": "Karas"},
    "lüderitz": {"label": "Luderitz", "lat": -26.6481, "lng": 15.1594, "region": "Karas"},
    "fish river canyon": {"label": "Fish River Canyon", "lat": -27.6122, "lng": 17.6079, "region": "Karas"},
}
ROUTE_THEME_MAP = {
    "airport": "airport-transfer.svg",
    "coast": "ocean-coast.svg",
    "coastal": "ocean-coast.svg",
    "swakopmund": "ocean-coast.svg",
    "walvis": "ocean-coast.svg",
    "safari": "etosha.svg",
    "etosha": "etosha.svg",
    "tour": "sossusvlei.svg",
    "sossusvlei": "sossusvlei.svg",
    "rundu": "safari-road.svg",
    "windhoek": "windhoek-night.svg",
    "fish": "fish-river.svg",
    "luderitz": "skeleton-coast.svg",
    "lüderitz": "skeleton-coast.svg",
}
BOOKING_TYPE_ROUTE_BADGES = {
    "airport": "Best for airport",
    "school": "Best for school",
    "tourist": "Best for tours",
    "business": "Best for business",
    "vip": "Best for VIP",
    "monthly": "Best for monthly plans",
    "long-distance": "Best for long-distance",
}
BOOKING_TYPE_FILTERS = {
    "airport": ("airport",),
    "school": ("school",),
    "tourist": ("tour", "safari", "coast"),
    "business": ("business", "airport"),
    "vip": ("vip", "executive", "airport"),
    "monthly": ("business", "school"),
    "long-distance": ("long-distance", "shuttle", "coast"),
}


def _location_key(value: str) -> str:
    return str(value or "").strip().lower().replace("international ", "").replace("intl ", "")


def _town_lookup(name: str) -> dict[str, Any] | None:
    key = _location_key(name)
    for alias, location in NAMIBIA_TOWNS.items():
        if alias in key or key in alias:
            return location
    return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _distance_label(value: Any) -> str:
    amount = _coerce_float(value)
    if amount is None:
        return ""
    return f"{int(amount) if amount.is_integer() else amount:g} km"


def _estimate_duration_label(distance_km: Any, explicit: Any = None) -> str:
    if explicit:
        return str(explicit)
    distance = _coerce_float(distance_km)
    if distance is None:
        return ""
    minutes = max(35, int((distance / 82) * 60))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def _route_theme(route_type: str, pickup: str, dropoff: str) -> str:
    probe = f"{route_type} {pickup} {dropoff}".lower()
    for key, asset in ROUTE_THEME_MAP.items():
        if key in probe:
            return asset
    return "desert-premium.svg"


def _route_badge(route_type: str, pickup: str, dropoff: str) -> str:
    probe = f"{route_type} {pickup} {dropoff}".lower()
    if "airport" in probe:
        return "Best for airport"
    if "school" in probe:
        return "Best for school"
    if "business" in probe:
        return "Best for business"
    if "vip" in probe or "executive" in probe:
        return "Best for VIP"
    if any(term in probe for term in ("tour", "safari", "coast", "sossusvlei", "etosha")):
        return "Best for tours"
    return "Best for Namibia travel"


def _build_route_preview(pickup: str, dropoff: str, pickup_lat: Any = None, pickup_lng: Any = None, dropoff_lat: Any = None, dropoff_lng: Any = None) -> dict[str, Any]:
    pickup_lookup = _town_lookup(pickup)
    dropoff_lookup = _town_lookup(dropoff)
    pickup_point = {
        "label": pickup_lookup["label"] if pickup_lookup else pickup or "Pickup",
        "lat": _coerce_float(pickup_lat) if pickup_lat not in (None, "") else (pickup_lookup or {}).get("lat"),
        "lng": _coerce_float(pickup_lng) if pickup_lng not in (None, "") else (pickup_lookup or {}).get("lng"),
    }
    dropoff_point = {
        "label": dropoff_lookup["label"] if dropoff_lookup else dropoff or "Drop-off",
        "lat": _coerce_float(dropoff_lat) if dropoff_lat not in (None, "") else (dropoff_lookup or {}).get("lat"),
        "lng": _coerce_float(dropoff_lng) if dropoff_lng not in (None, "") else (dropoff_lookup or {}).get("lng"),
    }
    points = []
    if pickup_point["lat"] is not None and pickup_point["lng"] is not None:
        points.append([pickup_point["lat"], pickup_point["lng"]])
    if dropoff_point["lat"] is not None and dropoff_point["lng"] is not None:
        points.append([dropoff_point["lat"], dropoff_point["lng"]])
    if len(points) == 2:
        center = {
            "lat": round((points[0][0] + points[1][0]) / 2, 4),
            "lng": round((points[0][1] + points[1][1]) / 2, 4),
            "label": f"{pickup_point['label']} to {dropoff_point['label']}",
        }
    elif points:
        center = {"lat": points[0][0], "lng": points[0][1], "label": pickup_point["label"]}
    else:
        center = dict(DEFAULT_MAP_CENTER)
    return {
        "center": center,
        "pickup_marker": pickup_point if pickup_point["lat"] is not None and pickup_point["lng"] is not None else None,
        "dropoff_marker": dropoff_point if dropoff_point["lat"] is not None and dropoff_point["lng"] is not None else None,
        "route_points": points,
        "has_coordinates": len(points) == 2,
    }


def _normalize_route(route: dict[str, Any]) -> dict[str, Any]:
    pickup = route.get("pickup") or route.get("from") or "Pickup"
    dropoff = route.get("dropoff") or route.get("to") or "Drop-off"
    preview = _build_route_preview(
        pickup,
        dropoff,
        route.get("pickup_lat"),
        route.get("pickup_lng"),
        route.get("dropoff_lat"),
        route.get("dropoff_lng"),
    )
    route_type = route.get("route_type", "")
    distance_label = _distance_label(route.get("distance_km"))
    duration_label = _estimate_duration_label(route.get("distance_km"), route.get("estimated_duration"))
    return {
        "pickup": pickup,
        "dropoff": dropoff,
        "distance_km": route.get("distance_km", ""),
        "distance_label": distance_label,
        "base_price": route.get("base_price", ""),
        "price_label": str(route.get("base_price", "") or "Quote required"),
        "price_per_extra_passenger": route.get("price_per_extra_passenger", ""),
        "vehicle_type": route.get("vehicle_type", ""),
        "route_type": route_type,
        "estimated_duration": route.get("estimated_duration", ""),
        "duration_label": duration_label,
        "road_type": route.get("road_type", "Tar road"),
        "region": route.get("region") or ((preview.get("dropoff_marker") or {}).get("label") and (_town_lookup(dropoff) or {}).get("region")) or "",
        "pickup_lat": (preview.get("pickup_marker") or {}).get("lat"),
        "pickup_lng": (preview.get("pickup_marker") or {}).get("lng"),
        "dropoff_lat": (preview.get("dropoff_marker") or {}).get("lat"),
        "dropoff_lng": (preview.get("dropoff_marker") or {}).get("lng"),
        "map_center": preview["center"],
        "map_preview": preview,
        "has_coordinates": preview["has_coordinates"],
        "route_badge": _route_badge(route_type, pickup, dropoff),
        "theme_asset": _route_theme(route_type, pickup, dropoff),
        "route": f"{pickup} -> {dropoff}",
    }


def _normalize_car(car: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": car.get("name") or car.get("vehicle_type") or "Vehicle",
        "vehicle_type": car.get("vehicle_type", ""),
        "seats": car.get("seats", ""),
        "luggage": car.get("luggage_capacity") or car.get("luggage", ""),
        "aircon": car.get("aircon", True),
        "best_for": car.get("best_for", ""),
        "price": car.get("price", ""),
        "status": car.get("status", ""),
    }


def _normalize_tour(tour: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": tour.get("slug"),
        "title": tour.get("title") or "Tour",
        "hero": tour.get("description") or tour.get("destination") or "",
        "price": tour.get("price_from") or "",
        "duration": tour.get("duration") or "",
        "pickup_locations": tour.get("pickup_locations", []),
        "itinerary": tour.get("itinerary", []),
        "included": tour.get("includes") or tour.get("included") or [],
        "summary": tour.get("description") or "",
    }


def _dev_rows(file_name: str) -> list[dict[str, Any]]:
    rows = load_json(file_name, [])
    return rows if isinstance(rows, list) else []


def list_routes() -> list[dict[str, Any]]:
    rows = fetch_rows("routes", limit=50)
    if rows:
        return [_normalize_route(item) for item in rows]
    if get_database_mode() == "json_dev_fallback":
        return [_normalize_route(item) for item in _dev_rows("routes.json")]
    return []


def get_namibia_towns() -> list[dict[str, Any]]:
    seen: set[str] = set()
    towns = []
    for item in NAMIBIA_TOWNS.values():
        if item["label"] in seen:
            continue
        seen.add(item["label"])
        towns.append(dict(item))
    return towns


def get_popular_routes(limit: int = 6) -> list[dict[str, Any]]:
    return list_routes()[:limit]


def match_route(pickup: str, dropoff: str, routes: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    routes = routes if routes is not None else list_routes()
    pickup_key = _location_key(pickup)
    dropoff_key = _location_key(dropoff)
    for route in routes:
        if _location_key(route.get("pickup", "")) == pickup_key and _location_key(route.get("dropoff", "")) == dropoff_key:
            return route
    return None


def build_route_preview(pickup: str, dropoff: str, routes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    routes = routes if routes is not None else list_routes()
    matched = match_route(pickup, dropoff, routes=routes)
    if matched:
        return {
            "route": matched,
            "preview": matched.get("map_preview"),
            "matched": True,
        }
    preview = _build_route_preview(pickup, dropoff)
    return {
        "route": {
            "pickup": pickup,
            "dropoff": dropoff,
            "route": f"{pickup or 'Pickup'} -> {dropoff or 'Drop-off'}",
            "distance_label": "",
            "duration_label": "",
            "price_label": "Quote required",
            "vehicle_type": "",
            "route_badge": "Preview only",
            "theme_asset": "desert-premium.svg",
            "has_coordinates": preview["has_coordinates"],
        },
        "preview": preview,
        "matched": False,
    }


def build_booking_route_suggestions(booking_type: str, routes: list[dict[str, Any]] | None = None, limit: int = 6) -> list[dict[str, Any]]:
    routes = routes if routes is not None else list_routes()
    filters = BOOKING_TYPE_FILTERS.get(booking_type, ())
    if filters:
        filtered = [
            route for route in routes
            if any(token in f"{route.get('route_type', '')} {route.get('pickup', '')} {route.get('dropoff', '')}".lower() for token in filters)
        ]
    else:
        filtered = routes
    suggestions = filtered[:limit] or routes[:limit]
    badge = BOOKING_TYPE_ROUTE_BADGES.get(booking_type)
    if badge:
        return [route | {"route_badge": badge} for route in suggestions]
    return suggestions


def list_cars() -> list[dict[str, Any]]:
    rows = fetch_rows("fleet", limit=50)
    if rows:
        return [_normalize_car(item) for item in rows]
    if get_database_mode() == "json_dev_fallback":
        return [_normalize_car(item) for item in _dev_rows("cars.json")]
    return []


def list_tours() -> list[dict[str, Any]]:
    rows = fetch_rows("tours", limit=50)
    if rows:
        return [_normalize_tour(item) for item in rows]
    if get_database_mode() == "json_dev_fallback":
        return [_normalize_tour(item) for item in _dev_rows("tours.json")]
    return []


def catalog_setup_required() -> bool:
    status = get_db_status()
    return bool(status.get("setup_required"))
