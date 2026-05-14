from __future__ import annotations

from services.admin_service import (
    get_dashboard_context,
    get_payments_context,
    get_reports_context,
    get_support_context,
)


def get_admin_control_context() -> dict:
    dashboard = get_dashboard_context()
    reports = get_reports_context()
    payments = get_payments_context()
    support = get_support_context()
    metrics = {item["label"]: item["value"] for item in dashboard.get("metrics", [])}

    return {
        "available": dashboard.get("available", False),
        "notice": dashboard.get("notice"),
        "metrics": metrics,
        "bookings": dashboard.get("bookings", []),
        "live_trips": dashboard.get("live_trips", []),
        "support_rows": support.get("tickets", []),
        "payments": payments.get("payments", []),
        "reports": reports,
        "drivers_online": dashboard.get("drivers_online", 0),
    }
