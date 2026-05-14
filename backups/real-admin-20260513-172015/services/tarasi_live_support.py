from __future__ import annotations

import json
import os
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from services.storage_service import load_json, save_json
from services.tarasi_bot_storage import (
    _db_mode,
    _new_id,
    _now,
    _pg_execute,
    _supabase_request,
    SUPABASE_KEY_NAMES,
)

BOT_DATA_DIR = Path("tarasi_bot")
SUPPORT_JSON_FILES = {
    "chats": BOT_DATA_DIR / "support_chats.json",
    "messages": BOT_DATA_DIR / "support_messages.json",
    "notifications": BOT_DATA_DIR / "admin_notifications.json",
}

def _json_rows(key: str) -> list[dict[str, Any]]:
    rows = load_json(SUPPORT_JSON_FILES[key], [])
    return rows if isinstance(rows, list) else []

def _save_json_rows(key: str, rows: list[dict[str, Any]]) -> None:
    save_json(SUPPORT_JSON_FILES[key], rows)

def _next_chat_number() -> str:
    today = datetime.now().strftime("%Y%m%d")
    counter = 1
    # Simple count from JSON if needed, or DB
    mode = _db_mode()
    if mode == "postgres":
        try:
            row = _pg_execute("select count(*) as count from tarasi_support_chats where created_at >= current_date", fetch="one")
            counter = (row["count"] or 0) + 1
        except: pass
    elif mode == "supabase":
        try:
            data = _supabase_request("GET", f"/rest/v1/tarasi_support_chats?select=id&created_at=gte.{datetime.now().date().isoformat()}")
            counter = len(data) + 1
        except: pass
    else:
        rows = _json_rows("chats")
        counter = len([r for r in rows if r.get("created_at", "").startswith(today)]) + 1
    
    return f"CHAT-{today}-{counter:04d}"

def create_support_chat(session_id: str, conversation_id: str | None, user_info: dict[str, Any], reason: str) -> dict[str, Any]:
    chat_number = _next_chat_number()
    row = {
        "id": _new_id(),
        "chat_number": chat_number,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "user_id": user_info.get("user_id"),
        "user_name": user_info.get("user_name"),
        "user_phone": user_info.get("user_phone"),
        "status": "waiting",
        "handoff_reason": reason,
        "bot_paused": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_support_chats 
                (id, chat_number, conversation_id, session_id, user_id, user_name, user_phone, status, handoff_reason, bot_paused, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one"
            )
            if result: row = dict(result)
        except: pass
    elif mode == "supabase":
        try:
            result = _supabase_request("POST", "/rest/v1/tarasi_support_chats", row, extra_headers={"Prefer": "return=representation"})
            if isinstance(result, list) and result: row = result[0]
        except: pass
    else:
        rows = _json_rows("chats")
        rows.append(row)
        _save_json_rows("chats", rows)
    
    # Create notification
    create_admin_notification(
        "New live support request",
        f"Client {row['user_name'] or 'Guest'} wants real support. Reason: {reason}",
        f"/admin/support/live/{chat_number}"
    )
    
    return row

def save_support_message(chat_id: str, sender_type: str, sender_name: str, message: str) -> dict[str, Any]:
    row = {
        "id": _new_id(),
        "chat_id": chat_id,
        "sender_type": sender_type,
        "sender_name": sender_name,
        "message": message,
        "created_at": _now(),
    }
    
    mode = _db_mode()
    if mode == "postgres":
        try:
            _pg_execute(
                "insert into tarasi_support_messages (id, chat_id, sender_type, sender_name, message, created_at) values (%s, %s, %s, %s, %s, %s)",
                tuple(row.values())
            )
            _pg_execute("update tarasi_support_chats set last_message = %s, updated_at = %s where id = %s", (message, _now(), chat_id))
        except: pass
    elif mode == "supabase":
        try:
            _supabase_request("POST", "/rest/v1/tarasi_support_messages", row)
            _supabase_request("PATCH", f"/rest/v1/tarasi_support_chats?id=eq.{chat_id}", {"last_message": message, "updated_at": _now()})
        except: pass
    else:
        messages = _json_rows("messages")
        messages.append(row)
        _save_json_rows("messages", messages)
        
        chats = _json_rows("chats")
        for c in chats:
            if c["id"] == chat_id:
                c["last_message"] = message
                c["updated_at"] = _now()
                break
        _save_json_rows("chats", chats)
        
    return row

def get_open_support_chats() -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        rows = _pg_execute("select * from tarasi_support_chats where status != 'closed' order by created_at desc")
        return [dict(r) for r in rows]
    elif mode == "supabase":
        data = _supabase_request("GET", "/rest/v1/tarasi_support_chats?status=neq.closed&order=created_at.desc")
        return data if isinstance(data, list) else []
    else:
        return [r for r in _json_rows("chats") if r.get("status") != "closed"]

def get_support_chat(chat_number: str) -> dict[str, Any] | None:
    mode = _db_mode()
    if mode == "postgres":
        row = _pg_execute("select * from tarasi_support_chats where chat_number = %s", (chat_number,), fetch="one")
        return dict(row) if row else None
    elif mode == "supabase":
        data = _supabase_request("GET", f"/rest/v1/tarasi_support_chats?chat_number=eq.{chat_number}")
        return data[0] if isinstance(data, list) and data else None
    else:
        for r in _json_rows("chats"):
            if r.get("chat_number") == chat_number: return r
        return None

def get_chat_messages(chat_id: str) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        rows = _pg_execute("select * from tarasi_support_messages where chat_id = %s order by created_at asc", (chat_id,))
        return [dict(r) for r in rows]
    elif mode == "supabase":
        data = _supabase_request("GET", f"/rest/v1/tarasi_support_messages?chat_id=eq.{chat_id}&order=created_at.asc")
        return data if isinstance(data, list) else []
    else:
        return [r for r in _json_rows("messages") if r.get("chat_id") == chat_id]

def admin_join_chat(chat_number: str, admin_name: str) -> bool:
    chat = get_support_chat(chat_number)
    if not chat: return False
    
    payload = {"status": "active", "assigned_admin": admin_name, "updated_at": _now()}
    mode = _db_mode()
    if mode == "postgres":
        _pg_execute("update tarasi_support_chats set status = %s, assigned_admin = %s, updated_at = %s where id = %s", ("active", admin_name, _now(), chat["id"]))
    elif mode == "supabase":
        _supabase_request("PATCH", f"/rest/v1/tarasi_support_chats?id=eq.{chat['id']}", payload)
    else:
        chats = _json_rows("chats")
        for c in chats:
            if c["id"] == chat["id"]:
                c.update(payload)
                break
        _save_json_rows("chats", chats)
        
    save_support_message(chat["id"], "system", "System", f"{admin_name} from Tarasi support joined the chat.")
    return True

def close_chat(chat_number: str) -> bool:
    chat = get_support_chat(chat_number)
    if not chat: return False
    
    payload = {"status": "closed", "bot_paused": False, "updated_at": _now()}
    mode = _db_mode()
    if mode == "postgres":
        _pg_execute("update tarasi_support_chats set status = %s, bot_paused = %s, updated_at = %s where id = %s", ("closed", False, _now(), chat["id"]))
    elif mode == "supabase":
        _supabase_request("PATCH", f"/rest/v1/tarasi_support_chats?id=eq.{chat['id']}", payload)
    else:
        chats = _json_rows("chats")
        for c in chats:
            if c["id"] == chat["id"]:
                c.update(payload)
                break
        _save_json_rows("chats", chats)
    
    save_support_message(chat["id"], "system", "System", "This support chat has been closed.")
    return True

def release_to_bot(chat_number: str) -> bool:
    chat = get_support_chat(chat_number)
    if not chat: return False
    
    payload = {"bot_paused": False, "updated_at": _now()}
    mode = _db_mode()
    if mode == "postgres":
        _pg_execute("update tarasi_support_chats set bot_paused = %s, updated_at = %s where id = %s", (False, _now(), chat["id"]))
    elif mode == "supabase":
        _supabase_request("PATCH", f"/rest/v1/tarasi_support_chats?id=eq.{chat['id']}", payload)
    else:
        chats = _json_rows("chats")
        for c in chats:
            if c["id"] == chat["id"]:
                c.update(payload)
                break
        _save_json_rows("chats", chats)
    
    save_support_message(chat["id"], "system", "System", "Support has released the chat back to the AI assistant.")
    return True

def create_admin_notification(title: str, message: str, link_url: str) -> dict[str, Any]:
    row = {
        "id": _new_id(),
        "notification_type": "support_handoff",
        "title": title,
        "message": message,
        "link_url": link_url,
        "is_read": False,
        "created_at": _now(),
    }
    
    mode = _db_mode()
    if mode == "postgres":
        try:
            _pg_execute("insert into tarasi_admin_notifications (id, notification_type, title, message, link_url, is_read, created_at) values (%s, %s, %s, %s, %s, %s, %s)", tuple(row.values()))
        except: pass
    elif mode == "supabase":
        try: _supabase_request("POST", "/rest/v1/tarasi_admin_notifications", row)
        except: pass
    else:
        notifications = _json_rows("notifications")
        notifications.append(row)
        _save_json_rows("notifications", notifications)
        
    return row

def get_unread_notifications() -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        rows = _pg_execute("select * from tarasi_admin_notifications where is_read = false order by created_at desc")
        return [dict(r) for r in rows]
    elif mode == "supabase":
        data = _supabase_request("GET", "/rest/v1/tarasi_admin_notifications?is_read=eq.false&order=created_at.desc")
        return data if isinstance(data, list) else []
    else:
        return [r for r in _json_rows("notifications") if not r.get("is_read")]

def mark_notification_read(notification_id: str) -> bool:
    mode = _db_mode()
    if mode == "postgres":
        _pg_execute("update tarasi_admin_notifications set is_read = true where id = %s", (notification_id,))
    elif mode == "supabase":
        _supabase_request("PATCH", f"/rest/v1/tarasi_admin_notifications?id=eq.{notification_id}", {"is_read": True})
    else:
        notifications = _json_rows("notifications")
        for n in notifications:
            if n["id"] == notification_id:
                n["is_read"] = True
                break
        _save_json_rows("notifications", notifications)
    return True

def get_active_chat_for_session(session_id: str) -> dict[str, Any] | None:
    mode = _db_mode()
    if mode == "postgres":
        row = _pg_execute("select * from tarasi_support_chats where session_id = %s and status != 'closed' order by created_at desc limit 1", (session_id,), fetch="one")
        return dict(row) if row else None
    elif mode == "supabase":
        data = _supabase_request("GET", f"/rest/v1/tarasi_support_chats?session_id=eq.{session_id}&status=neq.closed&order=created_at.desc&limit=1")
        return data[0] if isinstance(data, list) and data else None
    else:
        chats = [r for r in _json_rows("chats") if r.get("session_id") == session_id and r.get("status") != "closed"]
        if not chats: return None
        chats.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return chats[0]
