from __future__ import annotations

from typing import Any
from datetime import datetime

from services.db_service import fetch_rows, count_rows, insert_row, update_row
from services.driver_service import normalize_driver, list_driver_trips, get_driver_trip
from services.booking_service import get_booking

def get_driver_dashboard_context(driver_user_id: str) -> dict[str, Any]:
    # 1. Get Driver Profile from Neon
    rows = fetch_rows("drivers", filters={"user_id": driver_user_id})
    if not rows:
        return {"available": False, "error": "Driver profile not found."}
    
    driver = normalize_driver(rows[0])
    
    # 2. Get Today's Trips
    all_trips = list_driver_trips(driver)
    
    # Filter for active/recent
    active_statuses = {"Driver assigned", "On the way", "Arrived", "Picked up"}
    active_trips = [t for t in all_trips if t.get("status") in active_statuses]
    
    # Completed today
    today_str = datetime.now().strftime("%Y-%m-%d")
    completed_today = [
        t for t in all_trips 
        if t.get("status") == "Completed" and str(t.get("updated_at", "")).startswith(today_str)
    ]
    
    # Calculate earnings (simplified: sum of estimated_price for completed today)
    def _parse_price(val):
        try: return float(str(val).replace("N$", "").replace(",", "").strip())
        except: return 0.0
        
    earnings_today = sum(_parse_price(t.get("estimated_price")) for t in completed_today)

    # 3. New Requests (Trips assigned but not yet accepted by anyone or specifically assigned to this driver)
    # For now, we assume if it's in list_driver_trips with status 'Driver assigned', it's a request to accept
    new_requests = [t for t in all_trips if t.get("status") == "Driver assigned"]

    return {
        "available": True,
        "driver": driver,
        "active_trips": active_trips,
        "new_requests": new_requests,
        "earnings_today": f"N${earnings_today:.2f}",
        "completed_count": len(completed_today),
        "total_trips": driver.get("total_trips", 0),
        "status": driver.get("status", "Offline"),
        "verification_status": driver.get("verification_status", "Pending"),
    }

def record_driver_event(driver_id: str, booking_id: str, event_type: str, lat: float = None, lng: float = None, notes: str = None):
    payload = {
        "driver_id": driver_id,
        "booking_id": booking_id,
        "event_type": event_type,
        "lat": lat,
        "lng": lng,
        "notes": notes,
        "created_at": datetime.now().isoformat()
    }
    insert_row("driver_trip_events", payload)

def update_live_location(driver_id: str, lat: float, lng: float, speed: float = None, heading: float = None, accuracy: float = None, booking_id: str = None):
    payload = {
        "driver_id": driver_id,
        "booking_id": booking_id,
        "lat": lat,
        "lng": lng,
        "speed": speed,
        "heading": heading,
        "accuracy": accuracy,
        "created_at": datetime.now().isoformat()
    }
    insert_row("live_driver_locations", payload)
    
    # Also update the main driver record for "last seen"
    update_row("drivers", "driver_id", driver_id, {
        "current_lat": lat,
        "current_lng": lng,
        "last_location_at": datetime.now().isoformat()
    })
