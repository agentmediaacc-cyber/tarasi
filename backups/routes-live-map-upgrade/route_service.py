import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or ""
)

ROUTE_TABLE = os.getenv("TARASI_ROUTES_TABLE", "tarasi_routes")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _clean_money(value):
    try:
        if value in ("", None):
            return 0
        return float(value)
    except Exception:
        return 0


def _route_price(row):
    for key in [
        "starting_price",
        "base_price",
        "price",
        "fare",
        "amount",
        "route_price",
        "price_nad",
    ]:
        if key in row:
            return _clean_money(row.get(key))
    return 0


def _normalise_route(row):
    pickup = (
        row.get("pickup")
        or row.get("origin")
        or row.get("from_location")
        or row.get("start_location")
        or "Pickup not set"
    )

    dropoff = (
        row.get("dropoff")
        or row.get("destination")
        or row.get("to_location")
        or row.get("end_location")
        or "Drop-off not set"
    )

    route_name = (
        row.get("name")
        or row.get("route_name")
        or f"{pickup} to {dropoff}"
    )

    return {
        "id": row.get("id") or row.get("route_id") or "",
        "name": route_name,
        "pickup": pickup,
        "dropoff": dropoff,
        "category": row.get("category") or row.get("route_type") or row.get("service_type") or "Route",
        "region": row.get("region") or row.get("destination_region") or row.get("area") or "Namibia",
        "road_type": row.get("road_type") or row.get("road") or "Road type not set",
        "distance_km": row.get("distance_km") or row.get("distance") or 0,
        "duration": row.get("duration") or row.get("duration_text") or row.get("estimated_duration") or "Not set",
        "vehicle": row.get("vehicle") or row.get("recommended_vehicle") or row.get("vehicle_type") or "Admin to assign",
        "price": _route_price(row),
        "comfort": row.get("comfort") or row.get("comfort_level") or "Premium",
        "best_for": row.get("best_for") or row.get("suitability") or "Namibia travel",
        "status": row.get("status") or "active",
        "origin_lat": row.get("origin_lat") or row.get("pickup_lat") or row.get("start_lat"),
        "origin_lng": row.get("origin_lng") or row.get("pickup_lng") or row.get("start_lng"),
        "destination_lat": row.get("destination_lat") or row.get("dropoff_lat") or row.get("end_lat"),
        "destination_lng": row.get("destination_lng") or row.get("dropoff_lng") or row.get("end_lng"),
    }


def get_live_routes():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {
            "routes": [],
            "count": 0,
            "source": "not_configured",
            "message": "Supabase is not configured yet.",
        }

    url = f"{SUPABASE_URL}/rest/v1/{ROUTE_TABLE}"

    params = {
        "select": "*",
        "order": "created_at.desc",
    }

    try:
        response = requests.get(url, headers=_headers(), params=params, timeout=12)

        if response.status_code >= 400:
            return {
                "routes": [],
                "count": 0,
                "source": "supabase_error",
                "message": response.text[:300],
            }

        rows = response.json()
        routes = [
            _normalise_route(row)
            for row in rows
            if str(row.get("status", "active")).lower() in ["active", "published", "available", "true"]
        ]

        return {
            "routes": routes,
            "count": len(routes),
            "source": "supabase",
            "message": "",
        }

    except Exception as e:
        return {
            "routes": [],
            "count": 0,
            "source": "exception",
            "message": str(e),
        }
