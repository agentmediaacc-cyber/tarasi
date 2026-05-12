from __future__ import annotations

import logging
import time
from typing import Any

from .db_service import fetch_rows, get_db_status


logger = logging.getLogger(__name__)
EMPTY_STATE_MESSAGE = "Tarasi transport services are being configured. You can still contact support or make an enquiry."
HOMEPAGE_CACHE_TTL = 30
_CACHE: dict[str, dict[str, Any]] = {}


def _cache_get(key: str):
    cached = _CACHE.get(key)
    if not cached:
        return None
    if time.monotonic() - cached["stored_at"] > HOMEPAGE_CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return cached["value"]


def _cache_set(key: str, value: Any):
    _CACHE[key] = {"stored_at": time.monotonic(), "value": value}
    return value


def _timed_fetch_rows(table: str, limit: int | None = None) -> list[dict[str, Any]]:
    start = time.perf_counter()
    rows = fetch_rows(table, limit=limit)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.debug("homepage_service.fetch_rows table=%s limit=%s duration_ms=%.2f rows=%s", table, limit, duration_ms, len(rows) if isinstance(rows, list) else 0)
    return rows if isinstance(rows, list) else []


def _route_title(row: dict[str, Any]) -> str:
    pickup = row.get("pickup") or row.get("from") or "Route"
    dropoff = row.get("dropoff") or row.get("to") or "Destination"
    return f"{pickup} to {dropoff}"


def _route_meta(row: dict[str, Any]) -> str:
    parts = []
    if row.get("route_type"):
        parts.append(str(row["route_type"]))
    if row.get("distance_km") not in (None, ""):
        parts.append(f"{row['distance_km']} km")
    if row.get("base_price") not in (None, ""):
        parts.append(f"N${row['base_price']}" if isinstance(row["base_price"], (int, float)) else str(row["base_price"]))
    return " • ".join(parts)


def _tour_meta(row: dict[str, Any]) -> str:
    parts = []
    if row.get("destination"):
        parts.append(str(row["destination"]))
    if row.get("duration"):
        parts.append(str(row["duration"]))
    if row.get("price_from") not in (None, ""):
        parts.append(f"N${row['price_from']}" if isinstance(row["price_from"], (int, float)) else str(row["price_from"]))
    return " • ".join(parts)


def _fleet_meta(row: dict[str, Any]) -> str:
    parts = []
    if row.get("vehicle_type"):
        parts.append(str(row["vehicle_type"]))
    if row.get("seats") not in (None, ""):
        parts.append(f"{row['seats']} seats")
    if row.get("status"):
        parts.append(str(row["status"]).title())
    return " • ".join(parts)


def _fleet_theme(title: str, best_for: str) -> str:
    text = f"{title} {best_for}".lower()
    if "school" in text:
        return "school"
    if "airport" in text:
        return "airport"
    if "vip" in text or "luxury" in text or "executive" in text:
        return "vip"
    if "tour" in text or "safari" in text:
        return "tour"
    return "city"


def _fleet_specs(row: dict[str, Any]) -> dict[str, str]:
    return {
        "Seats": str(row.get("seats") or "Unavailable"),
        "Luggage": str(row.get("luggage_capacity") or row.get("luggage") or "Unavailable"),
        "A/C": "Yes" if str(row.get("aircon", "")).lower() in {"true", "yes", "1"} else (str(row.get("aircon")) if row.get("aircon") not in (None, "") else "Unavailable"),
        "USB": str(row.get("usb_charging") or "Unavailable"),
        "WiFi": str(row.get("wifi_available") or "Unavailable"),
        "Child seat": str(row.get("child_seat_available") or "Unavailable"),
        "Wheelchair": str(row.get("wheelchair_support") or "Unavailable"),
        "Comfort": str(row.get("comfort_level") or "Premium"),
    }


def _normalize_route_preview(row: dict[str, Any]) -> dict[str, Any]:
    pickup = row.get("pickup")
    dropoff = row.get("dropoff")
    return {
        "title": _route_title(row),
        "subtitle": row.get("vehicle_type") or "Scheduled transport",
        "meta": _route_meta(row),
        "pickup": pickup,
        "dropoff": dropoff,
        "base_price": row.get("base_price"),
        "route_type": row.get("route_type") or "",
    }


def _normalize_tour_preview(row: dict[str, Any]) -> dict[str, Any]:
    title = row.get("title") or "Tour"
    return {
        "slug": row.get("slug"),
        "title": title,
        "subtitle": row.get("description") or row.get("destination") or "Namibia tour",
        "meta": _tour_meta(row),
        "description": row.get("description", ""),
        "theme": "desert" if "sossus" in title.lower() else ("safari" if "etosha" in title.lower() else "coast"),
    }


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _destination_slides() -> list[dict[str, str]]:
    return [
        {"name": "Sossusvlei", "text": "Sunrise dune transfers, lodge movement and premium desert touring.", "theme": "sossusvlei", "wallpaper": "desert-premium.svg"},
        {"name": "Swakopmund Ocean / Coast", "text": "Coastal arrivals, hotel transfers and premium Atlantic road travel.", "theme": "ocean-coast", "wallpaper": "ocean-coast.svg"},
        {"name": "Walvis Bay", "text": "Airport, harbour and coast-to-city shuttle movement with premium timing.", "theme": "ocean-coast", "wallpaper": "ocean-coast.svg"},
        {"name": "Etosha", "text": "Safari transfer coordination for camps, lodges and overland premium routes.", "theme": "etosha", "wallpaper": "etosha.svg"},
        {"name": "Popa Falls", "text": "Northern river journeys and scenic transport through Namibia’s greener corridor.", "theme": "popa-falls", "wallpaper": "popa-falls.svg"},
        {"name": "Windhoek", "text": "City glow transfers, airport pickups and premium urban movement.", "theme": "windhoek-night", "wallpaper": "windhoek-night.svg"},
        {"name": "Dune 7", "text": "Adventure transfer support for dune experiences near the coast.", "theme": "desert-premium", "wallpaper": "desert-premium.svg"},
        {"name": "Fish River Canyon", "text": "Long-distance comfort routes into Namibia’s dramatic southern landscapes.", "theme": "fish-river", "wallpaper": "fish-river.svg"},
        {"name": "Lüderitz", "text": "Coastal frontier travel with premium long-distance and lodge transfer support.", "theme": "ocean-coast", "wallpaper": "ocean-coast.svg"},
        {"name": "Skeleton Coast", "text": "Remote premium touring routes with striking coastal atmosphere.", "theme": "skeleton-coast", "wallpaper": "skeleton-coast.svg"},
        {"name": "Rundu", "text": "Northern business and family movement with long-distance comfort planning.", "theme": "popa-falls", "wallpaper": "popa-falls.svg"},
        {"name": "Caprivi / Zambezi", "text": "Premium regional transfers into Namibia’s river and safari gateway.", "theme": "popa-falls", "wallpaper": "popa-falls.svg"},
    ]


def _resolve_slide_cta(slide_name: str, routes: list[dict[str, Any]], tours: list[dict[str, Any]]) -> tuple[str, str]:
    name = slide_name.lower()
    route_match = next((route for route in routes if name in route.get("title", "").lower()), None)
    tour_match = next((tour for tour in tours if name in tour.get("title", "").lower() or name in tour.get("subtitle", "").lower()), None)
    if tour_match and tour_match.get("slug"):
        return "Book tour", f"/tour/{tour_match['slug']}"
    if route_match:
        return "View routes", "/routes"
    return "Book shuttle", "/book/tourist"


def _normalize_fleet_preview(row: dict[str, Any]) -> dict[str, Any]:
    title = row.get("name") or row.get("vehicle_type") or "Vehicle"
    best_for = row.get("best_for") or row.get("route_suitability") or "Premium travel"
    theme = _fleet_theme(title, best_for)
    suitability = best_for.lower()
    badge = "Best for airport" if "airport" in suitability else "Best for tours" if "tour" in suitability else "Best for school" if "school" in suitability else "Best for VIP" if any(word in suitability for word in ["vip", "executive", "luxury"]) else "Best for city rides"
    return {
        "title": title,
        "subtitle": row.get("vehicle_category") or row.get("vehicle_type") or "Fleet availability",
        "meta": _fleet_meta(row),
        "status": row.get("status") or "",
        "best_for": best_for,
        "badge": badge,
        "theme": theme,
        "specs": _fleet_specs(row),
    }


def get_featured_transport_routes(limit: int = 6, route_type_filter: str | None = None) -> list[dict[str, Any]]:
    cache_key = f"routes:{limit}:{route_type_filter or 'all'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    rows = _timed_fetch_rows("routes", limit=max(limit * 2, limit))
    items = []
    for row in rows:
        route_type = str(row.get("route_type", "")).lower()
        if route_type_filter and route_type_filter.lower() not in route_type:
            continue
        items.append(_normalize_route_preview(row))
        if len(items) >= limit:
            break
    return _cache_set(cache_key, items)


def get_featured_tours(limit: int = 4) -> list[dict[str, Any]]:
    cache_key = f"tours:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    rows = _timed_fetch_rows("tours", limit=limit)
    return _cache_set(cache_key, [_normalize_tour_preview(row) for row in rows])


def get_featured_fleet(limit: int = 4) -> list[dict[str, Any]]:
    cache_key = f"fleet:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    rows = _timed_fetch_rows("fleet", limit=limit)
    return _cache_set(cache_key, [_normalize_fleet_preview(row) for row in rows])


def get_service_cards() -> list[dict[str, str]]:
    return [
        {"title": "Ride", "description": "Point-to-point bookings for everyday movement across Namibia.", "href": "/book/once-off", "icon": "↔", "badge": "Core"},
        {"title": "Airport Transfer", "description": "Arrival and departure transport with premium pickup coordination.", "href": "/book/airport", "icon": "✈", "badge": "Priority"},
        {"title": "School Transport", "description": "Guardian-friendly recurring school movement with safe scheduling.", "href": "/book/school", "icon": "△", "badge": "Trusted"},
        {"title": "Monthly Plans", "description": "Reliable recurring transport for staff, families and private clients.", "href": "/book/monthly", "icon": "▤", "badge": "Recurring"},
        {"title": "Tours", "description": "Desert, coast and safari movement connected to real listed tour routes.", "href": "/tours", "icon": "◇", "badge": "Explore"},
        {"title": "VIP", "description": "Executive private hire with premium fleet matching and route comfort.", "href": "/book/vip", "icon": "★", "badge": "Executive"},
        {"title": "Business", "description": "Corporate staff movement, airport pickups and flexible transport support.", "href": "/book/business", "icon": "□", "badge": "Corporate"},
        {"title": "Support", "description": "Urgent booking help, complaints and service assistance when needed.", "href": "/support", "icon": "✦", "badge": "24/7"},
    ]


def get_homepage_metrics() -> dict[str, Any]:
    cache_key = "homepage_metrics"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    db_status = get_db_status()
    routes = get_featured_transport_routes(limit=12)
    tours = get_featured_tours(limit=12)
    fleet = get_featured_fleet(limit=12)
    active_bookings = _timed_fetch_rows("bookings", limit=200)
    active_count = sum(1 for row in active_bookings if str(row.get("status", "")).lower().replace(" ", "_") in {"driver_assigned", "on_the_way", "arrived", "picked_up"})
    metrics = {
        "database_connected": db_status.get("connected", False),
        "database_mode": db_status.get("database"),
        "has_routes": bool(routes),
        "has_tours": bool(tours),
        "has_fleet": bool(fleet),
        "active_bookings": active_count if active_count else None,
        "route_count": len(routes) if routes else None,
        "fleet_count": len(fleet) if fleet else None,
        "tour_count": len(tours) if tours else None,
    }
    return _cache_set(cache_key, metrics)


def get_live_route_board() -> list[dict[str, Any]]:
    desired = [
        ("windhoek", "hosea kutako"),
        ("windhoek", "swakopmund"),
        ("windhoek", "etosha"),
        ("windhoek", "sossusvlei"),
    ]
    routes = get_featured_transport_routes(limit=24)
    board = []
    for pickup, dropoff in desired:
        match = next(
            (
                route for route in routes
                if pickup in str(route.get("pickup", "")).lower()
                and dropoff in str(route.get("dropoff", "")).lower()
            ),
            None,
        )
        if match:
            board.append(match)
    return board


def get_homepage_payload() -> dict[str, Any]:
    cache_key = "homepage_payload"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    route_highlights = get_featured_transport_routes(limit=4)
    tours = get_featured_tours(limit=3)
    fleet = get_featured_fleet(limit=4)
    slideshow_tours = get_featured_tours(limit=20)
    slideshow_routes = get_featured_transport_routes(limit=30)
    metrics = get_homepage_metrics()
    destination_slides = []
    for slide in _destination_slides():
        cta_label, cta_href = _resolve_slide_cta(slide["name"], slideshow_routes, slideshow_tours)
        destination_slides.append(
            {
                **slide,
                "cta_label": cta_label,
                "cta_href": cta_href,
                "wallpaper_url": f"/static/img/namibia/{slide['wallpaper']}",
                "id": _slugify(slide["name"]),
            }
        )
    payload = {
        "service_cards": get_service_cards(),
        "route_highlights": route_highlights,
        "tours": tours,
        "fleet": fleet,
        "route_board": get_live_route_board(),
        "destination_slides": destination_slides,
        "empty_state_message": EMPTY_STATE_MESSAGE,
        "homepage_has_live_data": bool(route_highlights or tours or fleet),
        "metrics": metrics,
        "hero_words": ["Airport", "Tours", "School", "VIP", "Business", "Long-distance"],
    }
    return _cache_set(cache_key, payload)


def get_category_services(category: str, limit: int = 12) -> list[dict[str, Any]]:
    if category == "transport":
        return get_featured_transport_routes(limit=limit)
    if category == "airport":
        return get_featured_transport_routes(limit=limit, route_type_filter="airport")
    if category == "school":
        return get_featured_transport_routes(limit=limit, route_type_filter="school")
    if category == "monthly":
        return get_featured_transport_routes(limit=limit, route_type_filter="monthly")
    if category == "vip":
        return get_featured_fleet(limit=limit)
    if category == "business":
        return get_featured_transport_routes(limit=limit, route_type_filter="business")
    if category == "tours":
        return get_featured_tours(limit=limit)
    return []


def homepage_has_live_data() -> bool:
    metrics = get_homepage_metrics()
    return any([metrics.get("has_routes"), metrics.get("has_tours"), metrics.get("has_fleet")])
