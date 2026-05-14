from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")

def _read_json(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _list(name):
    return _read_json(DATA_DIR / name, [])

def _money(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0

def get_admin_control_context():
    bookings = _list("bookings.json")
    drivers = _list("drivers.json") or _list("partners.json")
    vehicles = _list("cars.json") or _list("fleet.json")
    tickets = _list("support_tickets.json")
    payments = _list("payments.json")
    invoices = _list("invoices.json")
    refunds = _list("refunds.json")
    routes = _list("routes.json")
    tours = _list("tours.json") or _list("packages.json")
    audits = _list("audit_log.json")

    pending = [b for b in bookings if str(b.get("status","")).lower() in ["booking received","pending","requested"]]
    confirmed = [b for b in bookings if "confirm" in str(b.get("status","")).lower()]
    active = [b for b in bookings if str(b.get("status","")).lower() in ["driver assigned","active","on the way","picked up"]]
    completed = [b for b in bookings if "complete" in str(b.get("status","")).lower()]
    open_tickets = [t for t in tickets if str(t.get("status","open")).lower() == "open"]

    revenue = sum(_money(b.get("amount") or b.get("price") or b.get("final_price") or b.get("total")) for b in bookings)
    if not revenue:
        revenue = sum(_money(p.get("amount")) for p in payments)

    def service_count(word):
        return len([b for b in bookings if word in str(b.get("service_type","") + " " + b.get("type","")).lower()])

    return {
        "system_mode": "real backend connected",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "metrics": {
            "total_bookings": len(bookings),
            "pending_bookings": len(pending),
            "confirmed_bookings": len(confirmed),
            "active_rides": len(active),
            "completed_rides": len(completed),
            "total_drivers": len(drivers),
            "available_vehicles": len(vehicles),
            "support_tickets": len(open_tickets),
            "payments": len(payments),
            "invoices": len(invoices),
            "refunds": len(refunds),
            "routes": len(routes),
            "tours": len(tours),
            "estimated_revenue": revenue,
            "airport_bookings": service_count("airport"),
            "school_bookings": service_count("school"),
            "tourist_bookings": service_count("tour"),
            "vip_bookings": service_count("vip"),
            "business_bookings": service_count("business"),
        },
        "recent_bookings": list(reversed(bookings))[:10],
        "live_trips": active[:8],
        "support_queue": open_tickets[:8],
        "drivers": drivers[:10],
        "vehicles": vehicles[:10],
        "routes": routes[:10],
        "invoices": list(reversed(invoices))[:10],
        "audit_logs": list(reversed(audits))[:10],
    }
