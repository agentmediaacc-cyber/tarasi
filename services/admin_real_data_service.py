from __future__ import annotations
from datetime import datetime
from services.db_service import count_rows, fetch_rows, get_db_status, get_database_mode
from services.admin_service import _money, _amount_number

def get_real_admin_context():
    db_status = get_db_status()
    available = db_status.get("connected", False)
    
    # Use count_rows for metrics instead of full fetch
    metrics = {
        "total_bookings": count_rows("bookings"),
        "pending_bookings": count_rows("bookings", filters={"status": "pending"}),
        "confirmed_bookings": count_rows("bookings", filters={"status": "confirmed"}),
        "active_rides": count_rows("bookings", filters={"status": "driver_assigned"}),
        "completed_rides": count_rows("bookings", filters={"status": "completed"}),
        "total_drivers": count_rows("drivers"),
        "available_vehicles": count_rows("fleet", filters={"status": "available"}),
        "support_tickets": count_rows("support_tickets", filters={"status": "open"}),
        "payments": count_rows("payments"),
        "invoices": count_rows("invoices"),
    }

    # Fetch data with limits for the dashboard view
    bookings = fetch_rows("bookings", limit=10)
    drivers = fetch_rows("drivers", limit=10)
    vehicles = fetch_rows("fleet", limit=10)
    tickets = fetch_rows("support_tickets", filters={"status": "open"}, limit=10)
    payments = fetch_rows("payments", limit=10)
    invoices = fetch_rows("invoices", limit=10)

    # Estimate revenue from last 50 payments (faster than full scan)
    recent_payments = fetch_rows("payments", limit=50)
    revenue = sum(_amount_number(p.get("amount")) or 0.0 for p in recent_payments)
    metrics["estimated_revenue"] = _money(revenue)
    
    return {
        "system_mode": f"{get_database_mode().upper()} REAL DATA",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "metrics": metrics,
        "recent_bookings": bookings,
        "drivers": drivers,
        "vehicles": vehicles,
        "support_queue": tickets,
        "payments": payments,
        "invoices": invoices,
        "available": available
    }
