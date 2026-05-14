from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import quote

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

def search_address(query: str) -> list[dict[str, Any]]:
    """Search for address using Nominatim (OpenStreetMap)."""
    # Filter for Namibia results
    q = f"{query}, Namibia"
    url = f"{NOMINATIM_URL}?q={quote(q)}&format=json&limit=5&addressdetails=1"
    
    headers = {
        "User-Agent": "TarasiBot/1.0 (tarasishuttle@gmail.com)"
    }
    
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = []
            for item in data:
                results.append({
                    "display_name": item.get("display_name"),
                    "lat": float(item.get("lat")),
                    "lon": float(item.get("lon")),
                    "address": item.get("address", {}),
                    "type": item.get("type"),
                    "importance": item.get("importance")
                })
            return results
    except Exception as e:
        print(f"Geocoding error: {e}")
        return []

def get_route(start_coords: tuple[float, float], end_coords: tuple[float, float]) -> dict[str, Any] | None:
    """Get distance and duration from OSRM."""
    # OSRM uses {lon},{lat}
    coords = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    url = f"{OSRM_URL}/{coords}?overview=false"
    
    try:
        request = Request(url)
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                return {
                    "distance_km": round(route["distance"] / 1000, 2),
                    "duration_minutes": round(route["duration"] / 60, 1)
                }
    except Exception as e:
        print(f"Routing error: {e}")
    return None
