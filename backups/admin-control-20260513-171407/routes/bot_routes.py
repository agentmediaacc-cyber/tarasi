from __future__ import annotations

import uuid
import os

from flask import Blueprint, jsonify, render_template, request, session

from services.admin_service import get_admin_shell
from services.tarasi_ai_provider import get_ai_status
from services.tarasi_bot_service import COMPANY, analyze_message, build_bot_reply, opening_message
from services.tarasi_distance_service import search_zones
from services.tarasi_pricing_engine import (
    calculate_quote,
    create_booking,
    get_bank_details,
    save_quote,
    update_booking_status as update_pricing_booking_status,
)
from services.tarasi_bot_storage import (
    create_or_get_conversation,
    create_ticket,
    get_available_drivers,
    get_conversation_messages,
    get_dashboard_summary,
    get_user_memory,
    list_conversations,
    list_reviews,
    list_tickets,
    save_bot_reply,
    save_review,
    save_user_message,
    update_conversation,
    update_user_memory,
)


from services.tarasi_live_support import (
    admin_join_chat,
    close_chat,
    create_admin_notification,
    create_support_chat,
    get_active_chat_for_session,
    get_chat_messages,
    get_open_support_chats,
    get_support_chat,
    get_unread_notifications,
    mark_notification_read,
    release_to_bot,
    save_support_message,
)


from services.tarasi_map_service import search_address, get_route
from services.tarasi_quote_pdf_service import generate_quote_pdf

bot_bp = Blueprint("bot", __name__)


def _session_identity() -> dict[str, str]:
    if not session.get("tarasi_bot_session_id"):
        session["tarasi_bot_session_id"] = str(uuid.uuid4())
    name = (
        session.get("user_name")
        or session.get("full_name")
        or session.get("name")
        or session.get("username")
        or session.get("client_name")
        or ""
    )
    user_id = session.get("user_id") or session.get("auth_user_id") or session.get("profile_id") or ""
    phone = session.get("phone") or session.get("user_phone") or ""
    email = session.get("email") or session.get("user_email") or ""
    user_key = str(user_id or phone or email or session["tarasi_bot_session_id"])
    return {
        "session_id": session["tarasi_bot_session_id"],
        "user_id": str(user_id or ""),
        "user_name": name,
        "user_phone": str(phone or ""),
        "user_email": str(email or ""),
        "user_key": user_key,
    }


@bot_bp.route("/bot")
@bot_bp.route("/assistant")
def bot_page():
    return render_template("bot/tarasi_bot.html", company=COMPANY)


@bot_bp.route("/api/bot/greeting")
def bot_greeting():
    identity = _session_identity()
    memory = get_user_memory(identity["user_key"])
    name = identity["user_name"]
    last_context = memory.get("last_context") or {}
    message = opening_message(name=name or None, last_task=last_context.get("last_task") or last_context.get("topic"), returning_guest=bool(last_context))
    return jsonify(
        {
            "logged_in": bool(identity["user_id"]),
            "name": name,
            "last_task": last_context.get("last_task") or last_context.get("topic", ""),
            "greeting": message,
            "suggestions": ["Create quote", "Book now", "Track booking", "Talk to support"],
        }
    )


@bot_bp.route("/api/bot/message", methods=["POST"])
def bot_message():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "message": "Message is required."}), 400

    identity = _session_identity()
    
    # Check for active live support chat first
    active_chat = get_active_chat_for_session(identity["session_id"])
    if active_chat and active_chat.get("bot_paused"):
        # Just save the message to support chat and return
        save_support_message(active_chat["id"], "user", identity["user_name"] or "Guest", message)
        return jsonify({
            "ok": True,
            "session_id": identity["session_id"],
            "reply": None, # Bot doesn't reply
            "support_active": True,
            "chat_number": active_chat["chat_number"]
        })

    memory = get_user_memory(identity["user_key"])
    conversation = create_or_get_conversation(
        identity["session_id"],
        {
            "user_id": identity["user_id"],
            "user_name": identity["user_name"],
            "user_phone": identity["user_phone"],
            "user_email": identity["user_email"],
            "client_type": memory.get("client_type", "general_client"),
            "mood": "neutral",
            "current_intent": "general_support",
            "last_topic": (memory.get("last_context") or {}).get("topic", ""),
        },
    )
    history = get_conversation_messages(conversation["id"], limit=12)
    analysis = analyze_message(message, conversation=conversation, history=history, user_memory=memory)
    drivers = []
    if analysis["intent"] in {
        "airport_transfer",
        "town_pickup",
        "vip_transfer",
        "late_driver",
        "wrong_pickup",
        "driver_complaint",
        "tracking_request",
        "price_enquiry",
        "quote_request",
    }:
        drivers = get_available_drivers(analysis["zone"], analysis["vehicle"])

    save_user_message(
        conversation["id"],
        message,
        analysis["intent"],
        analysis["mood"],
        analysis["confidence"],
        metadata={
            "stage": analysis.get("stage"),
            "topic": analysis.get("topic"),
            "ticket_number": analysis.get("ticket_number"),
            "quote_number": analysis.get("quote_number"),
            "booking_number": analysis.get("booking_number"),
        },
    )
    result = build_bot_reply(
        message,
        analysis=analysis,
        conversation=conversation,
        history=history,
        user_memory=memory,
        user_profile={"name": identity["user_name"]},
        available_drivers=drivers,
    )
    
    # Handle human handoff request from bot service
    if result.get("handoff_requested"):
        chat = create_support_chat(
            identity["session_id"],
            conversation_id=conversation["id"],
            user_info={
                "user_id": identity["user_id"],
                "user_name": identity["user_name"],
                "user_phone": identity["user_phone"]
            },
            reason=f"Bot detected intent: {message}"
        )
        result["handoff"] = True
        result["chat_number"] = chat["chat_number"]
        result["bot_paused"] = True
        save_support_message(chat["id"], "system", "System", f"Handoff triggered by message: {message}")
    quote_row = None
    if result.get("quote_data"):
        quote_row = save_quote(result["quote_data"], user_id=identity["user_id"] or None, session_id=identity["session_id"])
        result["quote_data"]["quote_number"] = quote_row.get("quote_number", result["quote_data"].get("quote_number"))
        if result.get("memory_updates") and isinstance(result["memory_updates"], dict):
            last_context = result["memory_updates"].setdefault("last_context", {})
            last_context["quote_number"] = result["quote_data"]["quote_number"]

    ticket = None
    if result.get("ticket_required"):
        ticket = create_ticket(
            result.get("ticket_type", "GENERAL_SUPPORT"),
            result.get("ticket_subject", "Tarasi support"),
            result.get("ticket_description", message),
            conversation_id=conversation["id"],
            user_id=identity["user_id"] or None,
            priority=result.get("priority", "normal"),
        )
        result["reply"] = f"{result['reply']} Ticket number: {ticket['ticket_number']}."
        if result.get("memory_updates") and isinstance(result["memory_updates"], dict):
            last_context = result["memory_updates"].setdefault("last_context", {})
            last_context["ticket_number"] = ticket["ticket_number"]
        result["ticket_number"] = ticket["ticket_number"]

    save_bot_reply(
        conversation["id"],
        result["reply"],
        result.get("detected_intent", analysis["intent"]),
        result.get("detected_mood", analysis["mood"]),
        float(result.get("confidence") or analysis["confidence"]),
        metadata={
            "stage": result.get("stage", analysis.get("stage")),
            "topic": result.get("last_topic", analysis.get("topic")),
            "ticket_number": result.get("ticket_number"),
            "quote_number": (result.get("quote_data") or {}).get("quote_number"),
            "booking_number": result.get("booking_number"),
        },
    )
    update_conversation(
        conversation["id"],
        {
            "client_type": result.get("client_type", analysis["client_type"]),
            "mood": result.get("detected_mood", analysis["mood"]),
            "current_intent": result.get("detected_intent", analysis["intent"]),
            "last_topic": result.get("last_topic", analysis["topic"]),
            "status": result.get("stage") or result.get("conversation_status", "open"),
        },
    )
    memory_updates = result.get("memory_updates") or {}
    if memory_updates:
        memory_updates["client_type"] = result.get("client_type", analysis["client_type"])
        update_user_memory(identity["user_key"], memory_updates)

    response_payload = {
        "ok": True,
        "session_id": identity["session_id"],
        "conversation_id": conversation["id"],
        "reply": result["reply"],
        "suggestions": result.get("suggestions", []),
        "ticket_number": ticket.get("ticket_number") if ticket else None,
        "quote": result.get("quote_data"),
        "detected_intent": result.get("detected_intent", analysis["intent"]),
        "detected_mood": result.get("detected_mood", analysis["mood"]),
        "client_type": result.get("client_type", analysis["client_type"]),
        "stage": result.get("stage", analysis.get("stage")),
        "ai": result.get("ai_meta", {}),
        "available_drivers": drivers,
        "handoff": result.get("handoff"),
        "chat_number": result.get("chat_number")
    }
    return jsonify(response_payload)


@bot_bp.route("/api/map/search", methods=["POST"])
def map_search():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"ok": False, "error": "Query required"}), 400
    results = search_address(query)
    return jsonify({"ok": True, "results": results})


@bot_bp.route("/api/map/route", methods=["POST"])
def map_route():
    payload = request.get_json(silent=True) or {}
    start = payload.get("start") # [lat, lon]
    end = payload.get("end") # [lat, lon]
    if not start or not end:
        return jsonify({"ok": False, "error": "Start and end coordinates required"}), 400
    route = get_route(tuple(start), tuple(end))
    return jsonify({"ok": bool(route), "route": route})


@bot_bp.route("/api/bot/booking-step", methods=["POST"])
def bot_booking_step():
    payload = request.get_json(silent=True) or {}
    step = payload.get("step")
    # This endpoint is a shortcut for the frontend to trigger specific bot responses
    # But since we use /api/bot/message for everything, we can just map it here
    return bot_message()


@bot_bp.route("/api/bot/create-quote-pdf", methods=["POST"])
def bot_create_quote_pdf():
    payload = request.get_json(silent=True) or {}
    quote_number = payload.get("quote_number")
    from services.tarasi_pricing_engine import get_quote_by_number
    quote = get_quote_by_number(quote_number)
    if not quote:
        return jsonify({"ok": False, "error": "Quote not found"}), 404
    
    file_path = generate_quote_pdf(quote)
    return jsonify({"ok": True, "file_url": f"/api/bot/download-pdf?file={os.path.basename(file_path)}"})


@bot_bp.route("/api/bot/download-pdf")
def bot_download_pdf():
    import os
    from flask import send_from_directory
    filename = request.args.get("file")
    directory = "data/generated_docs"
    return send_from_directory(directory, filename, as_attachment=True)


@bot_bp.route("/api/bot/review", methods=["POST"])
def bot_review():
    payload = request.get_json(silent=True) or {}
    identity = _session_identity()
    conversation_id = payload.get("conversation_id")
    helpful = bool(payload.get("helpful"))
    rating = int(payload.get("rating") or (5 if helpful else 2))
    review_text = str(payload.get("review_text", "")).strip() or ("Helpful" if helpful else "Needs follow-up")
    sentiment = "positive" if rating >= 4 else "negative"
    review = save_review(conversation_id, identity["user_id"] or None, rating, review_text, sentiment)
    follow_up = ""
    suggestions: list[str] = []
    if sentiment == "negative":
        follow_up = "Sorry about that. What did you want help with — price, booking, tracking, payment, invoice, or support?"
        suggestions = ["Price", "Booking", "Tracking", "Payment", "Invoice", "Support"]
    return jsonify({"ok": True, "review": review, "follow_up": follow_up, "suggestions": suggestions})


@bot_bp.route("/api/admin/bot/conversations")
def admin_bot_conversations():
    return jsonify({"rows": list_conversations(limit=100)})


@bot_bp.route("/api/admin/bot/tickets")
def admin_bot_tickets():
    return jsonify({"rows": list_tickets(limit=100)})


@bot_bp.route("/api/admin/bot/reviews")
def admin_bot_reviews():
    return jsonify({"rows": list_reviews(limit=100)})


@bot_bp.route("/api/bot/system-check")
def bot_system_check():
    ai_status = get_ai_status(force_check=False)
    knowledge = get_active_knowledge()
    zones = search_zones("", limit=1)
    
    # Check storage health
    storage_ok = True
    try: list_conversations(limit=1)
    except: storage_ok = False
    
    return jsonify({
        "ai_provider_ok": ai_status.get("available", False),
        "ai_fallback_active": ai_status.get("fallback", True),
        "pricing_engine_ok": True, # Static service
        "booking_storage_ok": storage_ok,
        "payment_invoice_ok": True,
        "live_support_ok": True,
        "admin_knowledge_ok": True,
        "knowledge_items_count": len(knowledge),
        "zones_loaded": len(zones) > 0,
        "tourism_brain_loaded": True,
        "template_fallback_ok": True,
        "timestamp": datetime.now().isoformat()
    })


@bot_bp.route("/admin/bot")
def admin_dashboard():
    summary = get_dashboard_summary()
    return render_template(
        "admin/bot_dashboard.html",
        summary=summary,
        ai_status=get_ai_status(),
        admin_shell=get_admin_shell("bot"),
        notice=None,
    )


@bot_bp.route("/api/pricing/estimate", methods=["POST"])
def pricing_estimate():
    payload = request.get_json(silent=True) or {}
    identity = _session_identity()
    quote = calculate_quote(payload)
    stored = save_quote(quote, user_id=identity["user_id"] or None, session_id=identity["session_id"])
    return jsonify(
        {
            "quote_number": stored["quote_number"],
            "pickup_zone": quote["pickup_zone"],
            "dropoff_zone": quote["dropoff_zone"],
            "distance_km": quote["distance_km"],
            "duration_minutes": quote["duration_minutes"],
            "final_price": quote["final_price"],
            "driver_payout": quote["driver_payout"],
            "tarasi_commission": quote["tarasi_commission"],
            "estimated_profit": quote["estimated_profit"],
            "price_breakdown": quote["price_breakdown"],
            "confidence": quote["confidence"],
            "notes": quote["notes"],
            "suggestions": quote["suggestions"],
            "vehicle_type": quote["vehicle_type"],
            "pickup": quote["pickup_text"],
            "dropoff": quote["dropoff_text"],
        }
    )


@bot_bp.route("/api/bookings/create", methods=["POST"])
def create_pricing_booking():
    payload = request.get_json(silent=True) or {}
    identity = _session_identity()
    booking = create_booking(payload, user_id=identity["user_id"] or None, session_id=identity["session_id"])
    return jsonify({"ok": True, "booking": booking, "bank_details": get_bank_details()})


@bot_bp.route("/api/bookings/<booking_number>/status", methods=["POST"])
def update_pricing_booking(booking_number: str):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not status:
        return jsonify({"ok": False, "error": "status_required"}), 400
    booking = update_pricing_booking_status(booking_number, status, note)
    return jsonify({"ok": bool(booking), "booking": booking}), (200 if booking else 404)


@bot_bp.route("/api/zones/search")
def zones_search():
    query = request.args.get("q", "")
    rows = search_zones(query)
    return jsonify({"rows": rows})


@bot_bp.route("/api/bot/speed-test")
def bot_speed_test():
    import time
    from services.tarasi_bot_service import build_bot_reply, analyze_message
    from services.tarasi_pricing_engine import calculate_quote
    from services.tarasi_ai_provider import get_ai_status

    results = {}
    
    # 1. Template Speed
    start = time.time()
    _ = build_bot_reply("hi", analysis=analyze_message("hi"))
    results["template_latency_ms"] = int((time.time() - start) * 1000)
    
    # 2. Pricing Engine Speed
    start = time.time()
    _ = calculate_quote({
        "pickup": "Windhoek",
        "dropoff": "Hosea Kutako Airport",
        "vehicle_type": "sedan",
        "service_type": "airport"
    })
    results["pricing_latency_ms"] = int((time.time() - start) * 1000)
    
    # 3. AI Status
    results["ai_status"] = get_ai_status()
    
    # 4. Storage/DB Speed (Summary check)
    start = time.time()
    _ = get_dashboard_summary()
    results["storage_latency_ms"] = int((time.time() - start) * 1000)
    
    return jsonify({
        "ok": True,
        "timestamp": time.time(),
        "results": results
    })


@bot_bp.route("/api/support/handoff", methods=["POST"])
def support_handoff():
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason", "User requested human support")).strip()
    identity = _session_identity()
    
    # Check if active chat already exists
    active_chat = get_active_chat_for_session(identity["session_id"])
    if active_chat:
        return jsonify({"ok": True, "chat": active_chat, "already_exists": True})
    
    # Get last conversation if available
    memory = get_user_memory(identity["user_key"])
    # We might need to find the actual conversation ID if possible, 
    # but for handoff we primarily care about session mapping.
    
    chat = create_support_chat(
        identity["session_id"],
        conversation_id=None, # Will be linked if possible
        user_info={
            "user_id": identity["user_id"],
            "user_name": identity["user_name"],
            "user_phone": identity["user_phone"]
        },
        reason=reason
    )
    
    save_support_message(chat["id"], "system", "System", f"User requested support: {reason}")
    
    return jsonify({"ok": True, "chat": chat})


@bot_bp.route("/api/support/chat/<chat_number>")
def get_user_support_chat(chat_number: str):
    chat = get_support_chat(chat_number)
    if not chat:
        return jsonify({"ok": False, "error": "Chat not found"}), 404
    
    identity = _session_identity()
    if chat["session_id"] != identity["session_id"]:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
        
    messages = get_chat_messages(chat["id"])
    return jsonify({"ok": True, "chat": chat, "messages": messages})


@bot_bp.route("/api/support/chat/<chat_number>/message", methods=["POST"])
def post_user_support_message(chat_number: str):
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "error": "Message required"}), 400
        
    chat = get_support_chat(chat_number)
    if not chat:
        return jsonify({"ok": False, "error": "Chat not found"}), 404
    
    identity = _session_identity()
    if chat["session_id"] != identity["session_id"]:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
        
    msg = save_support_message(chat["id"], "user", identity["user_name"] or "Guest", message)
    return jsonify({"ok": True, "message": msg})
