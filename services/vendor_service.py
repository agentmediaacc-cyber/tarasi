from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime
from typing import Any

from .db_service import get_neon_connection, resolve_table_name, fetch_rows
from .storage_service import load_json, save_json

logger = logging.getLogger(__name__)
VENDORS_FILE = "vendors.json"

VENDOR_TYPES = [
    "Shuttle", "Airport Transfer", "Tours", "School Transport", 
    "VIP Transport", "Business Transport", "Car Rental", "Guide", "Activity Provider"
]

def create_vendor(payload: dict[str, Any]) -> dict[str, Any]:
    vendor = {
        "vendor_id": f"VEN-{secrets.token_hex(3).upper()}",
        "business_name": payload.get("business_name"),
        "vendor_type": payload.get("vendor_type", "Shuttle"),
        "contact_person": payload.get("contact_person"),
        "phone": payload.get("phone"),
        "email": payload.get("email"),
        "town": payload.get("town", "Windhoek"),
        "region": payload.get("region", "Khomas"),
        "verification_status": "Pending",
        "payout_status": "Active",
        "logo_url": payload.get("logo_url", "/static/img/vendor-default-logo.svg"),
        "cover_image": payload.get("cover_image", "/static/img/vendor-default-cover.jpg"),
        "rating": 5.0,
        "total_bookings": 0,
        "joined_at": datetime.now().isoformat(),
        "slug": payload.get("business_name", "").lower().replace(" ", "-")
    }
    
    vendors = list_vendors()
    vendors.append(vendor)
    save_json(VENDORS_FILE, vendors)
    return vendor

def list_vendors() -> list[dict[str, Any]]:
    # Try DB first
    table_name = resolve_table_name("vendors")
    if table_name:
        try:
            return fetch_rows("vendors")
        except Exception:
            pass
            
    # Fallback to JSON
    data = load_json(VENDORS_FILE, [])
    if not data:
        # Initial seeding if empty
        data = [
            {
                "vendor_id": "VEN-ETOSHA",
                "business_name": "Etosha Dream Safaris",
                "vendor_type": "Tours",
                "town": "Outjo",
                "verification_status": "Verified",
                "rating": 4.9,
                "slug": "etosha-dream-safaris"
            },
            {
                "vendor_id": "VEN-COASTAL",
                "business_name": "Coastal Quick Shuttle",
                "vendor_type": "Shuttle",
                "town": "Swakopmund",
                "verification_status": "Verified",
                "rating": 4.8,
                "slug": "coastal-quick-shuttle"
            }
        ]
        save_json(VENDORS_FILE, data)
    return data

def get_vendor(vendor_id: str) -> dict[str, Any] | None:
    return next((v for v in list_vendors() if v.get("vendor_id") == vendor_id), None)

def get_vendor_by_slug(slug: str) -> dict[str, Any] | None:
    return next((v for v in list_vendors() if v.get("slug") == slug), None)

def get_vendor_by_email(email: str) -> dict[str, Any] | None:
    return next((v for v in list_vendors() if v.get("email") == email), None)

def get_vendor_metrics(vendor_id: str) -> dict[str, Any]:
    from .booking_service import list_bookings
    bookings = [b for b in list_bookings() if b.get("vendor_id") == vendor_id]
    
    return {
        "booking_count": len(bookings),
        "earnings": sum(float(str(b.get("amount", 0)).replace("N$", "").replace(",", "") or 0) for b in bookings if b.get("payment_status") == "Paid"),
        "active_trips": len([b for b in bookings if b.get("status") in ["On the way", "Picked up"]]),
        "fleet_count": 0, # To be linked
        "route_count": 0, # To be linked
        "customer_rating": 4.8,
        "support_alerts": 0
    }
