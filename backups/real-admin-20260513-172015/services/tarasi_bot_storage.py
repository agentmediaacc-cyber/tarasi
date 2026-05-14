from __future__ import annotations

import json
import os
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import RealDictCursor

from services.driver_service import list_drivers
from services.storage_service import load_json, save_json


BOT_DATA_DIR = Path("tarasi_bot")
BOT_JSON_FILES = {
    "conversations": BOT_DATA_DIR / "conversations.json",
    "messages": BOT_DATA_DIR / "messages.json",
    "tickets": BOT_DATA_DIR / "tickets.json",
    "reviews": BOT_DATA_DIR / "reviews.json",
    "memory": BOT_DATA_DIR / "user_memory.json",
    "drivers": BOT_DATA_DIR / "drivers.json",
    "knowledge": BOT_DATA_DIR / "knowledge_items.json",
}


def get_active_knowledge() -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute("select * from tarasi_bot_knowledge_items where is_active = true order by priority desc, created_at desc")
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request("GET", "/rest/v1/tarasi_bot_knowledge_items?is_active=eq.true&order=priority.desc,created_at.desc")
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = [r for r in _json_rows("knowledge") if r.get("is_active", True)]
    rows.sort(key=lambda x: (x.get("priority", 5), x.get("created_at", "")), reverse=True)
    return rows


def search_knowledge(query: str) -> list[dict[str, Any]]:
    probe = query.lower().strip()
    if not probe:
        return get_active_knowledge()
    
    # In-memory search for now, or DB if available
    all_items = get_active_knowledge()
    results = []
    for item in all_items:
        haystack = " ".join([
            item.get("title", ""),
            item.get("category", ""),
            " ".join(item.get("keywords", []) or []),
            item.get("content", "")
        ]).lower()
        if probe in haystack:
            results.append(item)
    return results


def create_knowledge_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        "id": _new_id(),
        "title": payload.get("title", "Untitled"),
        "category": payload.get("category", "general"),
        "keywords": payload.get("keywords", []),
        "content": payload.get("content", ""),
        "priority": int(payload.get("priority") or 5),
        "is_active": True,
        "created_by": payload.get("created_by", "admin"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bot_knowledge_items
                (id, title, category, keywords, content, priority, is_active, created_by, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (row["id"], row["title"], row["category"], row["keywords"], row["content"], row["priority"], row["is_active"], row["created_by"], row["created_at"], row["updated_at"]),
                fetch="one"
            )
            if result: return dict(result)
        except Exception: pass
    if mode == "supabase":
        try:
            result = _supabase_request("POST", "/rest/v1/tarasi_bot_knowledge_items", row, extra_headers={"Prefer": "return=representation"})
            if isinstance(result, list) and result: return result[0]
        except Exception: pass
    
    rows = _json_rows("knowledge")
    rows.append(row)
    _save_json_rows("knowledge", rows)
    return row


def update_knowledge_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    payload["updated_at"] = _now()
    mode = _db_mode()
    if mode == "postgres":
        try:
            keys = [k for k in payload.keys() if k != "id"]
            set_sql = ", ".join(f"{k} = %s" for k in keys)
            values = tuple(payload[k] for k in keys) + (item_id,)
            result = _pg_execute(f"update tarasi_bot_knowledge_items set {set_sql} where id = %s returning *", values, fetch="one")
            if result: return dict(result)
        except Exception: pass
    if mode == "supabase":
        try:
            result = _supabase_request("PATCH", f"/rest/v1/tarasi_bot_knowledge_items?id=eq.{item_id}", payload, extra_headers={"Prefer": "return=representation"})
            if isinstance(result, list) and result: return result[0]
        except Exception: pass
    
    rows = _json_rows("knowledge")
    for i, r in enumerate(rows):
        if r.get("id") == item_id:
            rows[i].update(payload)
            _save_json_rows("knowledge", rows)
            return rows[i]
    return None


def deactivate_knowledge_item(item_id: str) -> bool:
    return update_knowledge_item(item_id, {"is_active": False}) is not None
SUPABASE_KEY_NAMES = ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return str(uuid.uuid4())


def _db_mode() -> str:
    if os.getenv("DATABASE_URL", "").strip():
        return "postgres"
    if os.getenv("SUPABASE_URL", "").strip() and any(os.getenv(name, "").strip() for name in SUPABASE_KEY_NAMES):
        return "supabase"
    return "json"


def _supabase_key() -> str | None:
    for name in SUPABASE_KEY_NAMES:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _supabase_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = _supabase_key()
    if not base_url or not key:
        raise RuntimeError("Supabase is not configured.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8") or str(exc)) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Supabase: {exc.reason}") from exc


def _pg_execute(query: str, values: tuple[Any, ...] = (), fetch: str = "all") -> Any:
    with closing(psycopg2.connect(os.getenv("DATABASE_URL", "").strip(), connect_timeout=5)) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, values)
            result = None
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            conn.commit()
            return result


def _json_rows(key: str) -> list[dict[str, Any]]:
    rows = load_json(BOT_JSON_FILES[key], [])
    return rows if isinstance(rows, list) else []


def _save_json_rows(key: str, rows: list[dict[str, Any]]) -> None:
    save_json(BOT_JSON_FILES[key], rows)


def _normalize_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or _new_id(),
        "conversation_id": row.get("conversation_id"),
        "sender": row.get("sender", "bot"),
        "message": row.get("message", ""),
        "detected_intent": row.get("detected_intent"),
        "detected_mood": row.get("detected_mood"),
        "bot_reply": row.get("bot_reply"),
        "confidence": float(row.get("confidence") or 0),
        "stage": row.get("stage"),
        "topic": row.get("topic"),
        "ticket_number": row.get("ticket_number"),
        "quote_number": row.get("quote_number"),
        "booking_number": row.get("booking_number"),
        "review_text": row.get("review_text"),
        "created_at": row.get("created_at") or _now(),
    }


def _json_find_by_field(key: str, field: str, value: Any) -> dict[str, Any] | None:
    for row in _json_rows(key):
        if row.get(field) == value:
            return row
    return None


def _json_upsert_row(key: str, row: dict[str, Any], match_field: str) -> dict[str, Any]:
    rows = _json_rows(key)
    for index, existing in enumerate(rows):
        if existing.get(match_field) == row.get(match_field):
            rows[index] = {**existing, **row}
            _save_json_rows(key, rows)
            return rows[index]
    rows.append(row)
    _save_json_rows(key, rows)
    return row


def _merge_unique(existing: list[Any], incoming: list[Any]) -> list[Any]:
    seen = []
    for item in list(existing) + list(incoming):
        if item in (None, "", {}, []):
            continue
        if item not in seen:
            seen.append(item)
    return seen


def _next_ticket_number(ticket_type: str) -> str:
    prefix = {
        "LOST_ITEM": "LOST",
        "DRIVER_COMPLAINT": "DRV",
        "LATE_DRIVER": "EMG",
        "BREAKDOWN": "EMG",
        "AIRPORT_DELAY": "EMG",
        "WRONG_PICKUP": "EMG",
        "MEDICAL_CONCERN": "EMG",
        "PAYMENT_SUPPORT": "PAY",
        "GENERAL_SUPPORT": "TRS",
    }.get(ticket_type, "TRS")
    today = datetime.now().strftime("%Y%m%d")
    counter = 1
    rows = list_tickets(limit=500)
    for row in rows:
        if str(row.get("ticket_number", "")).startswith(f"{prefix}-{today}-"):
            counter += 1
    return f"{prefix}-{today}-{counter:04d}"


def create_or_get_conversation(session_id: str, user_context: dict[str, Any] | None = None) -> dict[str, Any]:
    user_context = user_context or {}
    mode = _db_mode()
    if mode == "postgres":
        try:
            row = _pg_execute(
                """
                select * from tarasi_bot_conversations
                where session_id = %s
                order by created_at desc
                limit 1
                """,
                (session_id,),
                fetch="one",
            )
            if row:
                return dict(row)
            payload = {
                "id": _new_id(),
                "session_id": session_id,
                "user_id": user_context.get("user_id"),
                "user_name": user_context.get("user_name"),
                "user_phone": user_context.get("user_phone"),
                "user_email": user_context.get("user_email"),
                "client_type": user_context.get("client_type", "general_client"),
                "mood": user_context.get("mood", "neutral"),
                "current_intent": user_context.get("current_intent", "general_support"),
                "last_topic": user_context.get("last_topic", ""),
                "status": "open",
            }
            row = _pg_execute(
                """
                insert into tarasi_bot_conversations
                (id, session_id, user_id, user_name, user_phone, user_email, client_type, mood, current_intent, last_topic, status)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(payload.values()),
                fetch="one",
            )
            if row:
                return dict(row)
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_conversations?{urlencode({'select': '*', 'session_id': f'eq.{session_id}', 'order': 'created_at.desc', 'limit': '1'})}",
            )
            if isinstance(data, list) and data:
                return data[0]
            payload = {
                "id": _new_id(),
                "session_id": session_id,
                "user_id": user_context.get("user_id"),
                "user_name": user_context.get("user_name"),
                "user_phone": user_context.get("user_phone"),
                "user_email": user_context.get("user_email"),
                "client_type": user_context.get("client_type", "general_client"),
                "mood": user_context.get("mood", "neutral"),
                "current_intent": user_context.get("current_intent", "general_support"),
                "last_topic": user_context.get("last_topic", ""),
                "status": "open",
            }
            created = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_conversations",
                payload,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(created, list) and created:
                return created[0]
        except Exception:
            pass
    existing = _json_find_by_field("conversations", "session_id", session_id)
    if existing:
        return existing
    row = {
        "id": _new_id(),
        "session_id": session_id,
        "user_id": user_context.get("user_id"),
        "user_name": user_context.get("user_name"),
        "user_phone": user_context.get("user_phone"),
        "user_email": user_context.get("user_email"),
        "client_type": user_context.get("client_type", "general_client"),
        "mood": user_context.get("mood", "neutral"),
        "current_intent": user_context.get("current_intent", "general_support"),
        "last_topic": user_context.get("last_topic", ""),
        "status": "open",
        "created_at": _now(),
        "updated_at": _now(),
    }
    return _json_upsert_row("conversations", row, "id")


def update_conversation(conversation_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    payload = {**payload, "updated_at": _now()}
    mode = _db_mode()
    if mode == "postgres":
        try:
            set_sql = ", ".join(f"{key} = %s" for key in payload.keys())
            values = tuple(payload.values()) + (conversation_id,)
            row = _pg_execute(
                f"update tarasi_bot_conversations set {set_sql} where id = %s returning *",
                values,
                fetch="one",
            )
            return dict(row) if row else None
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "PATCH",
                f"/rest/v1/tarasi_bot_conversations?{urlencode({'id': f'eq.{conversation_id}'})}",
                payload,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(data, list) and data:
                return data[0]
        except Exception:
            pass
    row = _json_find_by_field("conversations", "id", conversation_id)
    if not row:
        return None
    return _json_upsert_row("conversations", {**row, **payload}, "id")


def save_user_message(
    conversation_id: str,
    message: str,
    detected_intent: str,
    detected_mood: str,
    confidence: float = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    base_row = {
        "id": _new_id(),
        "conversation_id": conversation_id,
        "sender": "user",
        "message": message,
        "detected_intent": detected_intent,
        "detected_mood": detected_mood,
        "bot_reply": None,
        "confidence": confidence,
        "created_at": _now(),
    }
    row = {
        **base_row,
        "stage": metadata.get("stage"),
        "topic": metadata.get("topic"),
        "ticket_number": metadata.get("ticket_number"),
        "quote_number": metadata.get("quote_number"),
        "booking_number": metadata.get("booking_number"),
        "review_text": metadata.get("review_text"),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bot_messages
                (id, conversation_id, sender, message, detected_intent, detected_mood, bot_reply, confidence, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (
                    base_row["id"],
                    base_row["conversation_id"],
                    base_row["sender"],
                    base_row["message"],
                    base_row["detected_intent"],
                    base_row["detected_mood"],
                    base_row["bot_reply"],
                    base_row["confidence"],
                    base_row["created_at"],
                ),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_messages",
                base_row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows("messages")
    rows.append(row)
    _save_json_rows("messages", rows)
    return row


def save_bot_reply(
    conversation_id: str,
    reply: str,
    detected_intent: str,
    detected_mood: str,
    confidence: float = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    base_row = {
        "id": _new_id(),
        "conversation_id": conversation_id,
        "sender": "bot",
        "message": reply,
        "detected_intent": detected_intent,
        "detected_mood": detected_mood,
        "bot_reply": reply,
        "confidence": confidence,
        "created_at": _now(),
    }
    row = {
        **base_row,
        "stage": metadata.get("stage"),
        "topic": metadata.get("topic"),
        "ticket_number": metadata.get("ticket_number"),
        "quote_number": metadata.get("quote_number"),
        "booking_number": metadata.get("booking_number"),
        "review_text": metadata.get("review_text"),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bot_messages
                (id, conversation_id, sender, message, detected_intent, detected_mood, bot_reply, confidence, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (
                    base_row["id"],
                    base_row["conversation_id"],
                    base_row["sender"],
                    base_row["message"],
                    base_row["detected_intent"],
                    base_row["detected_mood"],
                    base_row["bot_reply"],
                    base_row["confidence"],
                    base_row["created_at"],
                ),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_messages",
                base_row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows("messages")
    rows.append(row)
    _save_json_rows("messages", rows)
    return row


def get_conversation_messages(conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute(
                """
                select * from tarasi_bot_messages
                where conversation_id = %s
                order by created_at asc
                limit %s
                """,
                (conversation_id, limit),
            )
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_messages?{urlencode({'select': '*', 'conversation_id': f'eq.{conversation_id}', 'order': 'created_at.asc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = [row for row in _json_rows("messages") if row.get("conversation_id") == conversation_id]
    rows.sort(key=lambda item: item.get("created_at", ""))
    return [_normalize_message(row) for row in rows[:limit]]


def create_ticket(
    ticket_type: str,
    subject: str,
    description: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    row = {
        "id": _new_id(),
        "ticket_number": _next_ticket_number(ticket_type),
        "conversation_id": conversation_id,
        "user_id": user_id,
        "ticket_type": ticket_type,
        "priority": priority,
        "status": "open",
        "subject": subject,
        "description": description,
        "admin_notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bot_tickets
                (id, ticket_number, conversation_id, user_id, ticket_type, priority, status, subject, description, admin_notes, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_tickets",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows("tickets")
    rows.append(row)
    _save_json_rows("tickets", rows)
    return row


def save_review(conversation_id: str | None, user_id: str | None, rating: int, review_text: str, sentiment: str) -> dict[str, Any]:
    row = {
        "id": _new_id(),
        "conversation_id": conversation_id,
        "user_id": user_id,
        "rating": int(rating),
        "review_text": review_text,
        "sentiment": sentiment,
        "created_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            result = _pg_execute(
                """
                insert into tarasi_bot_reviews
                (id, conversation_id, user_id, rating, review_text, sentiment, created_at)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                tuple(row.values()),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_reviews",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    rows = _json_rows("reviews")
    rows.append(row)
    _save_json_rows("reviews", rows)
    return row


def get_user_memory(user_key: str | None) -> dict[str, Any]:
    if not user_key:
        return {}
    mode = _db_mode()
    if mode == "postgres":
        try:
            row = _pg_execute(
                "select * from tarasi_bot_user_memory where user_key = %s limit 1",
                (user_key,),
                fetch="one",
            )
            if row:
                return dict(row)
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_user_memory?{urlencode({'select': '*', 'user_key': f'eq.{user_key}', 'limit': '1'})}",
            )
            if isinstance(data, list) and data:
                return data[0]
        except Exception:
            pass
    return _json_find_by_field("memory", "user_key", user_key) or {}


def update_user_memory(user_key: str | None, updates: dict[str, Any]) -> dict[str, Any]:
    if not user_key:
        return {}
    existing = get_user_memory(user_key)
    row = {
        "id": existing.get("id") or _new_id(),
        "user_key": user_key,
        "favorite_routes": _merge_unique(existing.get("favorite_routes", []), updates.get("favorite_routes", [])),
        "preferred_vehicle": updates.get("preferred_vehicle") or existing.get("preferred_vehicle"),
        "airport_habits": {**(existing.get("airport_habits") or {}), **(updates.get("airport_habits") or {})},
        "payment_style": updates.get("payment_style") or existing.get("payment_style"),
        "tourist_interests": _merge_unique(existing.get("tourist_interests", []), updates.get("tourist_interests", [])),
        "previous_complaints": _merge_unique(existing.get("previous_complaints", []), updates.get("previous_complaints", [])),
        "frequent_pickups": _merge_unique(existing.get("frequent_pickups", []), updates.get("frequent_pickups", [])),
        "last_context": {**(existing.get("last_context") or {}), **(updates.get("last_context") or {})},
        "client_type": updates.get("client_type") or existing.get("client_type"),
        "created_at": existing.get("created_at") or _now(),
        "updated_at": _now(),
    }
    mode = _db_mode()
    if mode == "postgres":
        try:
            found = existing.get("id")
            if found:
                result = _pg_execute(
                    """
                    update tarasi_bot_user_memory
                    set favorite_routes = %s, preferred_vehicle = %s, airport_habits = %s, payment_style = %s,
                        tourist_interests = %s, previous_complaints = %s, frequent_pickups = %s, last_context = %s,
                        client_type = %s, updated_at = %s
                    where user_key = %s
                    returning *
                    """,
                    (
                        json.dumps(row["favorite_routes"]),
                        row["preferred_vehicle"],
                        json.dumps(row["airport_habits"]),
                        row["payment_style"],
                        json.dumps(row["tourist_interests"]),
                        json.dumps(row["previous_complaints"]),
                        json.dumps(row["frequent_pickups"]),
                        json.dumps(row["last_context"]),
                        row["client_type"],
                        row["updated_at"],
                        user_key,
                    ),
                    fetch="one",
                )
                if result:
                    return dict(result)
            result = _pg_execute(
                """
                insert into tarasi_bot_user_memory
                (id, user_key, favorite_routes, preferred_vehicle, airport_habits, payment_style, tourist_interests, previous_complaints, frequent_pickups, last_context, client_type, created_at, updated_at)
                values (%s, %s, %s::jsonb, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
                returning *
                """,
                (
                    row["id"],
                    row["user_key"],
                    json.dumps(row["favorite_routes"]),
                    row["preferred_vehicle"],
                    json.dumps(row["airport_habits"]),
                    row["payment_style"],
                    json.dumps(row["tourist_interests"]),
                    json.dumps(row["previous_complaints"]),
                    json.dumps(row["frequent_pickups"]),
                    json.dumps(row["last_context"]),
                    row["client_type"],
                    row["created_at"],
                    row["updated_at"],
                ),
                fetch="one",
            )
            if result:
                return dict(result)
        except Exception:
            pass
    if mode == "supabase":
        try:
            if existing.get("id"):
                result = _supabase_request(
                    "PATCH",
                    f"/rest/v1/tarasi_bot_user_memory?{urlencode({'user_key': f'eq.{user_key}'})}",
                    row,
                    extra_headers={"Prefer": "return=representation"},
                )
                if isinstance(result, list) and result:
                    return result[0]
            result = _supabase_request(
                "POST",
                "/rest/v1/tarasi_bot_user_memory",
                row,
                extra_headers={"Prefer": "return=representation"},
            )
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            pass
    return _json_upsert_row("memory", row, "user_key")


def get_available_drivers(zone: str | None = None, vehicle_type: str | None = None) -> list[dict[str, Any]]:
    vehicle_type = (vehicle_type or "").lower()
    zone = (zone or "").lower()
    rows: list[dict[str, Any]] = []
    mode = _db_mode()
    if mode == "postgres":
        try:
            query = "select * from tarasi_drivers where status in ('online', 'available', 'active') order by rating desc nulls last, created_at desc"
            rows = [dict(row) for row in _pg_execute(query, (), fetch="all") or []]
        except Exception:
            rows = []
    elif mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_drivers?{urlencode({'select': '*', 'order': 'rating.desc', 'limit': '100'})}",
            )
            rows = data if isinstance(data, list) else []
        except Exception:
            rows = []
    if not rows:
        rows = load_json(BOT_JSON_FILES["drivers"], [])
        if not isinstance(rows, list) or not rows:
            rows = [
                {
                    "id": driver.get("id") or driver.get("driver_id"),
                    "name": driver.get("full_name"),
                    "phone": driver.get("phone"),
                    "vehicle_type": (driver.get("service_type") or driver.get("vehicle_name") or "").lower() or "sedan",
                    "vehicle_name": driver.get("vehicle_name") or "",
                    "status": str(driver.get("status") or driver.get("availability") or "offline").lower(),
                    "current_zone": driver.get("based_area") or "",
                    "rating": driver.get("rating") or 5,
                    "languages": [],
                    "vip_suitable": "vip" in str(driver.get("service_type") or "").lower(),
                }
                for driver in list_drivers()
            ]
    filtered = []
    for row in rows:
        status = str(row.get("status") or "").lower()
        current_zone = str(row.get("current_zone") or row.get("based_area") or "").lower()
        row_vehicle = str(row.get("vehicle_type") or row.get("vehicle_name") or "").lower()
        if status and status not in {"online", "available", "active", "assigned"}:
            continue
        if zone and zone not in current_zone and current_zone not in zone:
            continue
        if vehicle_type and vehicle_type not in row_vehicle and row_vehicle not in vehicle_type:
            continue
        filtered.append(row)
    filtered.sort(key=lambda item: float(item.get("rating") or 0), reverse=True)
    return filtered[:5]


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute(
                "select * from tarasi_bot_conversations order by updated_at desc nulls last, created_at desc limit %s",
                (limit,),
            )
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_conversations?{urlencode({'select': '*', 'order': 'updated_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = _json_rows("conversations")
    rows.sort(key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return rows[:limit]


def list_tickets(limit: int = 50) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute(
                "select * from tarasi_bot_tickets order by updated_at desc nulls last, created_at desc limit %s",
                (limit,),
            )
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_tickets?{urlencode({'select': '*', 'order': 'updated_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = _json_rows("tickets")
    rows.sort(key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return rows[:limit]


def list_reviews(limit: int = 50) -> list[dict[str, Any]]:
    mode = _db_mode()
    if mode == "postgres":
        try:
            rows = _pg_execute(
                "select * from tarasi_bot_reviews order by created_at desc limit %s",
                (limit,),
            )
            return [dict(row) for row in rows or []]
        except Exception:
            pass
    if mode == "supabase":
        try:
            data = _supabase_request(
                "GET",
                f"/rest/v1/tarasi_bot_reviews?{urlencode({'select': '*', 'order': 'created_at.desc', 'limit': str(limit)})}",
            )
            if isinstance(data, list):
                return data
        except Exception:
            pass
    rows = _json_rows("reviews")
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_dashboard_summary() -> dict[str, Any]:
    conversations = list_conversations(limit=200)
    tickets = list_tickets(limit=200)
    reviews = list_reviews(limit=200)
    knowledge = get_active_knowledge()
    
    # Count waiting support chats without importing service (to avoid circularity)
    waiting_support = 0
    mode = _db_mode()
    if mode == "postgres":
        try:
            res = _pg_execute("select count(*) as count from tarasi_support_chats where status = 'waiting'", fetch="one")
            waiting_support = res["count"] or 0
        except: pass
    elif mode == "supabase":
        try:
            res = _supabase_request("GET", "/rest/v1/tarasi_support_chats?status=eq.waiting&select=id")
            waiting_support = len(res) if isinstance(res, list) else 0
        except: pass
    else:
        try:
            from services.storage_service import load_json
            support_chats = load_json(BOT_DATA_DIR / "support_chats.json", [])
            waiting_support = len([c for c in support_chats if c.get("status") == "waiting"])
        except: pass

    ai_conversations = 0
    template_conversations = 0
    for row in conversations[:8]:
        messages = get_conversation_messages(row.get("id", ""), limit=20)
        user_messages = [item for item in messages if item.get("sender") == "user"]
        bot_messages = [item for item in messages if item.get("sender") == "bot"]
        last_user = user_messages[-1] if user_messages else {}
        last_bot = bot_messages[-1] if bot_messages else {}
        user_key = str(row.get("user_id") or row.get("user_phone") or row.get("user_email") or row.get("session_id") or "")
        memory = get_user_memory(user_key)
        last_context = memory.get("last_context") or {}
        row["stage"] = last_context.get("stage") or row.get("status") or "open"
        row["last_intent"] = last_context.get("intent") or row.get("current_intent") or "general_support"
        row["last_mood"] = row.get("mood") or "neutral"
        row["last_topic"] = last_context.get("topic") or row.get("last_topic") or "general"
        row["last_message"] = (messages[-1]["message"] if messages else "") or ""
        row["last_user_message"] = last_user.get("message") or ""
        row["last_bot_reply"] = last_bot.get("message") or ""
        row["ticket_number"] = last_context.get("ticket_number") or ""
        row["quote_number"] = last_context.get("quote_number") or ""
        row["booking_number"] = last_context.get("booking_number") or ""
    for row in conversations:
        user_key = str(row.get("user_id") or row.get("user_phone") or row.get("user_email") or row.get("session_id") or "")
        memory = get_user_memory(user_key)
        ai_mode = str((memory.get("last_context") or {}).get("ai_mode") or "template")
        if ai_mode == "ai":
            ai_conversations += 1
        else:
            template_conversations += 1
    total_conversations = len(conversations)
    open_tickets = [row for row in tickets if str(row.get("status", "")).lower() == "open"]
    emergency_tickets = [row for row in tickets if str(row.get("priority", "")).lower() in {"urgent", "high"}]
    
    # Count quotes
    quote_count = 0
    try:
        from services.tarasi_pricing_engine import list_quotes
        quote_count = len(list_quotes(limit=1000))
    except: pass

    ratings = [int(row.get("rating")) for row in reviews if row.get("rating") not in (None, "")]
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    return {
        "total_conversations": total_conversations,
        "open_tickets": len(open_tickets),
        "emergency_tickets": len(emergency_tickets),
        "average_rating": average_rating,
        "recent_conversations": conversations[:8],
        "recent_tickets": tickets[:8],
        "recent_reviews": reviews[:8],
        "ai_conversations": ai_conversations,
        "template_conversations": template_conversations,
        "knowledge_count": len(knowledge),
        "live_support_waiting": waiting_support,
        "quote_count": quote_count,
    }

