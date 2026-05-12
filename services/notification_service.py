from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

from .db_service import get_neon_connection, resolve_table_name
from .storage_service import load_json, save_json

logger = logging.getLogger(__name__)
NOTIFICATIONS_FILE = "notifications.json"

def create_notification(
    user_email: str | None,
    title: str,
    message: str,
    notification_type: str,
    booking_reference: str | None = None,
    action_url: str | None = None,
    channel: str = "in_app"
) -> dict[str, Any] | None:
    """
    Creates a real notification record in the DB or JSON fallback.
    """
    notif = {
        "id": f"NOT-{int(time.time() * 1000)}",
        "user_email": user_email,
        "booking_reference": booking_reference,
        "title": title,
        "message": message,
        "type": notification_type,
        "channel": channel,
        "status": "unread",
        "action_url": action_url,
        "created_at": datetime.now().isoformat(),
        "read_at": None
    }

    # Try DB first
    table_name = resolve_table_name("notifications")
    if table_name:
        try:
            with get_neon_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {table_name} (
                            user_email, booking_reference, title, message, type, 
                            channel, status, action_url, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            user_email, booking_reference, title, message, notification_type,
                            channel, "unread", action_url, notif["created_at"]
                        )
                    )
                    row = cursor.fetchone()
                    if row:
                        notif["id"] = row[0]
                conn.commit()
            return notif
        except Exception as e:
            logger.error(f"Failed to create notification in DB: {e}")

    # Fallback to JSON
    notifs = load_json(NOTIFICATIONS_FILE, [])
    notifs.append(notif)
    save_json(NOTIFICATIONS_FILE, notifs)
    return notif

def list_user_notifications(user_email: str) -> list[dict[str, Any]]:
    """
    Lists notifications for a specific user.
    """
    table_name = resolve_table_name("notifications")
    if table_name:
        try:
            from psycopg2.extras import RealDictCursor
            with get_neon_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"SELECT * FROM {table_name} WHERE user_email = %s ORDER BY created_at DESC LIMIT 100",
                        (user_email,)
                    )
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list notifications from DB: {e}")

    # Fallback
    notifs = load_json(NOTIFICATIONS_FILE, [])
    return [n for n in notifs if n.get("user_email") == user_email]

def mark_notification_read(notification_id: str | int) -> bool:
    """
    Marks a single notification as read.
    """
    table_name = resolve_table_name("notifications")
    read_at = datetime.now().isoformat()
    if table_name:
        try:
            with get_neon_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {table_name} SET status = 'read', read_at = %s WHERE id = %s",
                        (read_at, notification_id)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark notification read in DB: {e}")

    # Fallback
    notifs = load_json(NOTIFICATIONS_FILE, [])
    for n in notifs:
        if str(n.get("id")) == str(notification_id):
            n["status"] = "read"
            n["read_at"] = read_at
            save_json(NOTIFICATIONS_FILE, notifs)
            return True
    return False

def mark_all_read(user_email: str) -> bool:
    """
    Marks all notifications for a user as read.
    """
    table_name = resolve_table_name("notifications")
    read_at = datetime.now().isoformat()
    if table_name:
        try:
            with get_neon_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {table_name} SET status = 'read', read_at = %s WHERE user_email = %s AND status = 'unread'",
                        (read_at, user_email)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark all read in DB: {e}")

    # Fallback
    notifs = load_json(NOTIFICATIONS_FILE, [])
    for n in notifs:
        if n.get("user_email") == user_email:
            n["status"] = "read"
            n["read_at"] = read_at
    save_json(NOTIFICATIONS_FILE, notifs)
    return True

def list_admin_alerts() -> list[dict[str, Any]]:
    """
    Lists recent alerts/notifications that might need admin attention.
    """
    # For now, just return most recent globally, could be filtered by type (e.g. payment_pending)
    notifs = load_json(NOTIFICATIONS_FILE, [])
    return sorted(notifs, key=lambda x: x.get("created_at", ""), reverse=True)[:50]

def trigger_booking_event(event_type: str, booking: dict[str, Any]):
    """
    Orchestrates notifications and messaging for a booking event.
    """
    from services.messaging_service import send_email_message
    
    reference = booking.get("reference")
    email = booking.get("email") or booking.get("account_email")
    name = booking.get("full_name") or "Tarasi Customer"
    
    context = {
        "reference": reference,
        "name": name,
        "pickup": booking.get("pickup"),
        "dropoff": booking.get("dropoff"),
        "date": booking.get("date"),
        "time": booking.get("time"),
        "driver_name": booking.get("driver_name"),
        "vehicle": booking.get("vehicle_name")
    }

    titles = {
        "booking_created": "Booking Received",
        "booking_confirmed": "Booking Confirmed",
        "driver_assigned": "Driver Assigned",
        "payment_verified": "Payment Verified",
        "cancellation_approved": "Trip Cancelled"
    }
    
    messages = {
        "booking_created": f"Your trip {reference} has been received.",
        "booking_confirmed": f"Your trip {reference} is now confirmed.",
        "driver_assigned": f"Driver {booking.get('driver_name')} assigned to {reference}.",
        "payment_verified": f"Payment for {reference} verified.",
        "cancellation_approved": f"Your trip {reference} has been cancelled."
    }

    title = titles.get(event_type, "Trip Update")
    msg = messages.get(event_type, f"Update for your trip {reference}")
    
    # 1. Create In-App Notification
    if email:
        create_notification(
            user_email=email,
            title=title,
            message=msg,
            notification_type=event_type,
            booking_reference=reference,
            action_url=f"/track/{reference}" if event_type != "cancellation_approved" else None
        )
    
    # 2. Trigger External Messaging
    if email:
        send_email_message(email, event_type, context)
    
    # 3. Create Admin Alert for specific types
    if event_type in ["booking_created", "cancellation_requested"]:
        create_notification(
            user_email=None, # System/Admin alert
            title=f"ADMIN: {title}",
            message=f"Action required for {reference}. {msg}",
            notification_type=f"admin_{event_type}",
            booking_reference=reference,
            action_url=f"/admin/bookings/{reference}"
        )

