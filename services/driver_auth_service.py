from __future__ import annotations

import secrets
from typing import Any
from datetime import datetime

from services.db_service import insert_row, update_row, fetch_rows
from services.supabase_service import sign_up, get_supabase_config_status
from services.driver_service import normalize_driver

def create_driver_account(payload: dict[str, Any]) -> tuple[bool, str]:
    """
    Creates a driver account:
    1. Supabase Auth user
    2. Neon drivers table record
    """
    email = payload.get("email", "").strip().lower()
    password = payload.get("password")
    full_name = payload.get("full_name")
    phone = payload.get("phone")
    
    if not email or not password or not full_name:
        return False, "Email, password, and full name are required."

    if not get_supabase_config_status()["configured"]:
        return False, "Supabase setup is required before driver registration."

    # 1. Create Supabase Auth User
    try:
        # account_type metadata is used by auth_service to identify the role
        auth_payload = sign_up(
            email, 
            password, 
            {
                "full_name": full_name,
                "phone": phone,
                "account_type": "Driver"
            }
        )
        
        supabase_user_id = None
        if auth_payload.get("user"):
            supabase_user_id = auth_payload["user"].get("id")
        elif auth_payload.get("id"):
             supabase_user_id = auth_payload["id"]
             
        if not supabase_user_id:
             return False, "Could not create auth user."

    except Exception as exc:
        return False, f"Auth creation failed: {str(exc)}"

    # 2. Create Neon Driver Record
    driver_id = payload.get("driver_code") or f"DRV-{secrets.token_hex(3).upper()}"
    driver_record = {
        "user_id": supabase_user_id,
        "driver_code": driver_id,
        "phone": phone,
        "status": payload.get("status") or "Offline",
        "license_number": payload.get("license_number"),
        "rating": float(payload.get("rating") or 0) if payload.get("rating") not in (None, "") else None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    try:
        ok = insert_row("drivers", driver_record)
        if not ok:
            return False, "Failed to save driver record to Neon."
            
        # Also ensure user exists in tarasi_users for common lookups
        user_record = {
            "supabase_user_id": supabase_user_id,
            "email": email,
            "full_name": full_name,
            "phone": phone,
            "account_type": "Driver",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        insert_row("tarasi_users", user_record)
        
        return True, driver_id
    except Exception as exc:
        return False, f"Database record creation failed: {str(exc)}"

def get_driver_by_user_id(user_id: str) -> dict[str, Any] | None:
    rows = fetch_rows("drivers", filters={"user_id": user_id})
    if rows:
        return normalize_driver(rows[0])
    return None
