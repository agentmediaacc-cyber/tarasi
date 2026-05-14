from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from services.tarasi_ai_provider import generate_human_reply
from services.tarasi_pricing_engine import (
    calculate_quote,
    calculate_customer_quote,
    get_bank_details,
    get_booking_by_number,
    get_invoice_by_booking_number,
    get_payment_by_booking_number,
    infer_service_type,
    save_quote,
)
from services.tarasi_bot_storage import get_active_knowledge, search_knowledge
from services.tarasi_map_service import search_address, get_route


KNOWLEDGE_PATH = Path("data/bot_knowledge/tarasi_ai_brain.json")
TEMPLATES_PATH = Path("data/bot_knowledge/tarasi_reply_templates.json")
RULES_PATH = Path("data/bot_knowledge/tarasi_conversation_rules.json")
ZONES_PATH = Path("data/tarasi_zones.json")

COMPANY = {
    "name": "Tarasi Shuttle and Transfer Services CC",
    "tin": "15733730-011",
    "reg_no": "CC/2025/11107",
    "email": "tarasishuttle@gmail.com",
    "bank": "First National Bank (FNB)",
    "account_name": "Tarasi Shuttle and Transfer Services CC",
    "account_number": "64289981259",
    "branch": "Maerua Mall",
    "branch_code": "282273",
}

STAGES = {
    "greeting",
    "choose_service",
    "collect_pickup_map",
    "collect_dropoff_map",
    "confirm_price",
    "collect_customer_details",
    "quote_ready",
    "ask_if_helpful",
    "closed",
    "human_support_needed",
}

TICKET_TYPES = {
    "lost_item": "LOST_ITEM",
    "driver_complaint": "DRIVER_COMPLAINT",
    "late_driver": "LATE_DRIVER",
    "breakdown": "BREAKDOWN",
    "airport_delay": "AIRPORT_DELAY",
    "wrong_pickup": "WRONG_PICKUP",
    "medical_concern": "MEDICAL_CONCERN",
    "payment_banking_request": "PAYMENT_SUPPORT",
    "general_support": "GENERAL_SUPPORT",
}

def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

BRAIN = _load_json(KNOWLEDGE_PATH)
REPLY_TEMPLATES = _load_json(TEMPLATES_PATH)
CONVERSATION_RULES = _load_json(RULES_PATH)
ZONE_DATA = _load_json(ZONES_PATH) if ZONES_PATH.suffix == ".json" else {}
SYNONYMS = CONVERSATION_RULES.get("fuzzy_synonyms", {})

def opening_message(name: str | None = None, last_task: str | None = None, returning_guest: bool = False) -> str:
    if returning_guest:
        greet = f"Welcome back{', ' + name if name else ''}! 👋"
        if last_task:
            return f"{greet} I see we were talking about {last_task.replace('_', ' ')}. How can I help you today?"
        return f"{greet} How can I help you today?"
    
    return "Hi 👋 I'm the Tarasi Bot. I can help you book a ride, check prices, or connect you to support. What would you like to do?"


def normalise(text: str | None) -> str:
    cleaned = (text or "").lower().replace("’", "'").replace("`", "'")
    cleaned = re.sub(r"[^a-z0-9\s'/&-]+", " ", cleaned)
    return " ".join(cleaned.strip().split())

def _replace_synonyms(text: str) -> str:
    cleaned = f" {normalise(text)} "
    for canonical, terms in SYNONYMS.items():
        for term in terms:
            pattern = f" {normalise(term)} "
            if pattern.strip() and pattern in cleaned:
                cleaned = cleaned.replace(pattern, f" {canonical} ")
    return " ".join(cleaned.split())

def should_open_support_ticket(intent: str, message: str, stage: str) -> bool:
    """Strict check for ticket creation."""
    msg = normalise(message)
    
    # 1. User clicks/taps "Talk to support" or explicit request
    if any(term in msg for term in ["talk to support", "talk to human", "real person", "agent", "manager", "representative"]):
        return True
        
    # 2. User says bot answer was not useful
    if any(term in msg for term in ["not useful", "useless", "bad bot", "horrible", "terrible"]):
        return True

    if stage == "ask_if_helpful" and any(term in msg for term in ["no", "nope", "did not help"]):
        return True
        
    # 3. Emergency/complaint/lost item/driver late/payment problem
    emergency_intents = {
        "lost_item", "driver_complaint", "late_driver", "breakdown", 
        "medical_concern", "wrong_pickup"
    }
    if intent in emergency_intents:
        return True
        
    if intent == "payment_banking_request" and any(term in msg for term in ["problem", "error", "fail", "wrong", "didn't work"]):
        return True
        
    return False

def should_start_booking_flow(intent: str, message: str) -> bool:
    msg = normalise(message)
    return intent == "booking_request" or msg in ["booking", "book", "book ride", "i want to book", "new booking", "ride"]

def should_use_map_search(stage: str) -> bool:
    return stage in ["collect_pickup_map", "collect_dropoff_map"]

def detect_intent(text: str, context: dict[str, Any] | None = None) -> str:
    msg = normalise(text)
    stage = str((context or {}).get("stage") or "")
    
    if msg in {"hi", "hello", "hey", "hola", "morning", "afternoon", "evening", "start"}:
        return "greeting"
    
    if any(term in msg for term in ["booking", "book ride", "create booking", "new booking"]):
        return "booking_request"
        
    if any(term in msg for term in ["price", "estimate", "how much", "cost", "quote"]):
        return "price_enquiry"
        
    if any(term in msg for term in ["airport", "aiport", "hosea kutako", "hkia"]):
        return "airport_transfer"

    if any(term in msg for term in ["what do you do", "capabilities", "help", "who are you", "what can you"]):
        return "capabilities_enquiry"

    handoff_triggers = ["talk to human", "real person", "support", "agent", "manager", "not useful"]
    if any(trigger in msg for trigger in handoff_triggers):
        return "human_support_needed"

    return "general_support"

def _memory_updates(analysis: dict[str, Any], extras: dict[str, Any] | None = None) -> dict[str, Any]:
    updates = {
        "last_context": {
            "stage": analysis.get("stage"),
            "intent": analysis.get("intent"),
            "pickup": analysis.get("pickup"),
            "dropoff": analysis.get("dropoff"),
            "passengers": analysis.get("passengers"),
            "luggage_count": analysis.get("luggage_count"),
            "vehicle_type": analysis.get("vehicle"),
            "travel_date": analysis.get("travel_date"),
            "travel_time": analysis.get("travel_time"),
            "service_type": analysis.get("service_type"),
            "full_name": analysis.get("full_name"),
            "phone": analysis.get("phone"),
            "email": analysis.get("email"),
            "quote_number": analysis.get("quote_number"),
        },
    }
    if extras:
        updates["last_context"].update(extras)
    return updates

def analyze_message(
    message: str,
    conversation: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    user_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_memory = user_memory or {}
    last_context = user_memory.get("last_context") or {}
    stage = last_context.get("stage") or "greeting"
    intent = detect_intent(message, context=last_context)
    
    # Extract details based on stage
    pickup = last_context.get("pickup")
    dropoff = last_context.get("dropoff")
    
    # Simple state transition for booking flow
    if should_start_booking_flow(intent, message) and stage != "collect_pickup_map":
        stage = "collect_pickup_map"

    return {
        "message": message,
        "intent": intent,
        "stage": stage,
        "pickup": pickup,
        "dropoff": dropoff,
        "user_memory": user_memory,
        "context": last_context,
        "mood": "neutral",
        "confidence": 0.9,
        "topic": "booking" if "booking" in intent or stage.startswith("collect") else "general"
    }

def _finalize_reply(
    user_message: str,
    analysis: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    # Skip AI for speed in booking flow
    instant_stages = {
        "greeting", "collect_pickup_map", "collect_dropoff_map", 
        "confirm_price", "collect_customer_details", "quote_ready"
    }
    if analysis["stage"] in instant_stages or result.get("stage") in instant_stages:
        return result

    # Only use AI for general questions or tourism with a strict timeout
    if analysis["intent"] in ["capabilities_enquiry", "general_support", "tour_enquiry"]:
        try:
            ai_response = generate_human_reply(user_message, {}, analysis.get("context", {}), result)
            if ai_response.get("ok"):
                result["reply"] = ai_response["reply"]
        except Exception:
            # Fallback to the default reply if AI fails or is too slow
            pass
            
    return result

def build_bot_reply(
    message: str,
    analysis: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    user_memory: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
    available_drivers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    analysis = analysis or analyze_message(message, conversation, history, user_memory)
    stage = analysis["stage"]
    intent = analysis["intent"]
    msg = normalise(message)
    context = analysis.get("context") or {}

    if " to " in msg and intent in {"price_enquiry", "airport_transfer", "booking_request", "general_support"}:
        left, right = message.split(" to ", 1)
        direct_quote = calculate_customer_quote(
            {
                "pickup_text": left.strip(),
                "dropoff_text": right.strip(),
                "vehicle_type": context.get("vehicle_type") or "sedan",
                "service_type": context.get("service_type") or infer_service_type(left.strip(), right.strip(), vehicle_type=context.get("vehicle_type") or "sedan"),
                "passengers": context.get("passengers") or 1,
                "luggage_count": context.get("luggage_count") or 0,
                "pickup_time": context.get("travel_time") or "",
            }
        )
        return {
            "reply": (
                f"Estimate for {direct_quote['pickup_text']} to {direct_quote['dropoff_text']}:\n"
                f"Distance: {direct_quote['distance_km']} km\n"
                f"Estimated time: {direct_quote['duration_minutes']} min\n"
                f"Vehicle: {str(direct_quote['vehicle_type']).upper()}\n"
                f"Price: N${direct_quote['final_price']:.2f}\n"
                f"Confidence: {direct_quote['price_confidence']}\n"
                f"Note: {direct_quote.get('short_note') or direct_quote.get('pricing_notes')}\n"
                "Would you like to create a booking or a quotation?"
            ),
            "suggestions": ["Create booking", "Create quote", "Change route"],
            "stage": "confirm_price",
            "quote_data": direct_quote,
            "memory_updates": _memory_updates(
                analysis,
                {
                    "pickup": direct_quote["pickup_text"],
                    "dropoff": direct_quote["dropoff_text"],
                    "distance_km": direct_quote["distance_km"],
                    "final_price": direct_quote["final_price"],
                    "stage": "confirm_price",
                },
            ),
        }
    
    # 1. Human Support Override
    if should_open_support_ticket(intent, message, stage):
        return {
            "reply": "I understand. I'm connecting you to our live support team right now. They will be with you in a moment.",
            "suggestions": ["Emergency", "Lost item", "Payment problem"],
            "stage": "human_support_needed",
            "handoff_requested": True,
            "ticket_required": True,
            "memory_updates": _memory_updates(analysis, {"stage": "human_support_needed"})
        }

    # 2. Greeting
    if intent == "greeting" and stage == "greeting":
        return _finalize_reply(message, analysis, {
            "reply": "Hi 👋 Welcome to Tarasi. I can help you book a ride, check a price, create a quote, or connect you to support. What would you like to do?",
            "suggestions": ["Booking", "Price estimate", "Talk to support"],
            "stage": "greeting",
            "memory_updates": _memory_updates(analysis, {"stage": "greeting"})
        })

    # 3. Booking Flow
    if stage == "collect_pickup_map":
        if msg in ["yes correct", "yes", "correct"] and context.get("pickup"):
            return {
                "reply": "Perfect. Now type your drop-off street, suburb, airport, mall, hotel, or landmark.",
                "suggestions": ["Hosea Kutako Airport", "Eros Airport", "Grove Mall", "Maerua Mall"],
                "stage": "collect_dropoff_map",
                "memory_updates": _memory_updates(analysis, {"stage": "collect_dropoff_map"})
            }
        
        results = search_address(message)
        if results:
            selected = results[0]
            return {
                "reply": f"Found pickup: {selected['display_name']}. Is this correct?",
                "suggestions": ["Yes, correct", "No, search again"],
                "stage": "collect_pickup_map",
                "pickup": selected['display_name'],
                "pickup_lat": selected['lat'],
                "pickup_lon": selected['lon'],
                "memory_updates": _memory_updates(analysis, {
                    "pickup": selected['display_name'],
                    "pickup_lat": selected['lat'],
                    "pickup_lon": selected['lon']
                })
            }
            
        # Fallback to zones
        from services.tarasi_distance_service import resolve_zone
        zone = resolve_zone(message)
        if zone:
            return {
                "reply": f"I couldn't find the exact street on the map, but I found the zone: {zone['name']}. Is this pickup correct?",
                "suggestions": ["Yes, correct", "No, search again"],
                "stage": "collect_pickup_map",
                "pickup": zone['name'],
                "memory_updates": _memory_updates(analysis, {"pickup": zone['name']})
            }
            
        return {
            "reply": "Great. Let’s create your booking. Please type your pickup street, suburb, or landmark (e.g., Nebo Street or Wanaheda).",
            "suggestions": ["Nebo Street", "Wanaheda", "Windhoek CBD"],
            "stage": "collect_pickup_map",
            "memory_updates": _memory_updates(analysis, {"stage": "collect_pickup_map"})
        }

    if stage == "collect_dropoff_map":
        if msg in ["yes correct", "yes", "correct"] and context.get("dropoff"):
             return _calculate_and_respond_price(analysis)

        results = search_address(message)
        if results:
            selected = results[0]
            pickup_lat = context.get("pickup_lat")
            pickup_lon = context.get("pickup_lon")
            if pickup_lat and pickup_lon:
                route = get_route((pickup_lat, pickup_lon), (selected['lat'], selected['lon']))
                distance = route["distance_km"] if route else 15.0 # fallback
                
                quote = calculate_quote({
                    "pickup": context.get("pickup"),
                    "dropoff": selected['display_name'],
                    "distance_km": distance,
                    "vehicle_type": context.get("vehicle_type") or "sedan"
                })
                
                return {
                    "reply": f"Found drop-off: {selected['display_name']}.\nDistance: {distance}km\nEstimated Price: N${quote['final_price']:.2f}\nWould you like to proceed with this quote?",
                    "suggestions": ["Yes, proceed", "Change details", "Talk to support"],
                    "stage": "confirm_price",
                    "quote_data": quote,
                    "memory_updates": _memory_updates(analysis, {
                        "dropoff": selected['display_name'],
                        "distance_km": distance,
                        "final_price": quote['final_price'],
                        "stage": "confirm_price"
                    })
                }
            else:
                # Pickup was a zone fallback without lat/lon
                return _calculate_and_respond_price(analysis, dropoff=selected['display_name'])

        # Fallback to zones for dropoff
        from services.tarasi_distance_service import resolve_zone
        zone = resolve_zone(message)
        if zone:
            return _calculate_and_respond_price(analysis, dropoff=zone['name'])

        return {
            "reply": "Please type your drop-off street or landmark (e.g., Grove Mall or Hosea Kutako Airport).",
            "suggestions": ["Grove Mall", "Hosea Kutako Airport", "Maerua Mall"],
            "stage": "collect_dropoff_map"
        }

    if stage == "confirm_price":
        if msg in ["yes proceed", "yes", "proceed"]:
            return {
                "reply": "Great. Please send your full name to finalize the quote.",
                "stage": "collect_customer_details",
                "memory_updates": _memory_updates(analysis, {"stage": "collect_customer_details"})
            }
        if msg in ["change", "change details", "no"]:
            return {
                "reply": "No problem. Let's start over. What is your pickup location?",
                "stage": "collect_pickup_map",
                "memory_updates": _memory_updates(analysis, {"stage": "collect_pickup_map", "pickup": None, "dropoff": None})
            }
            
    if stage == "collect_customer_details":
        if not context.get("full_name"):
            return {
                "reply": f"Thank you, {message}. Now please send your cell number.",
                "memory_updates": _memory_updates(analysis, {"full_name": message, "stage": "collect_customer_details"})
            }
        elif not context.get("phone"):
            return {
                "reply": "Got it. What date would you like to travel? (e.g., Tomorrow, or 20 May)",
                "suggestions": ["Today", "Tomorrow", "Next Monday"],
                "memory_updates": _memory_updates(analysis, {"phone": message, "stage": "collect_customer_details"})
            }
        elif not context.get("travel_date"):
            return {
                "reply": "Thank you. And what time should the driver arrive? (e.g., 08:00 or 2 PM)",
                "suggestions": ["08:00", "12:00", "15:30", "18:00"],
                "memory_updates": _memory_updates(analysis, {"travel_date": message, "stage": "collect_customer_details"})
            }
        elif not context.get("travel_time"):
            # Current message is time
            travel_time = message
            # Finalize quote with all details
            quote_payload = {
                "pickup": context.get("pickup"),
                "dropoff": context.get("dropoff"),
                "final_price": context.get("final_price"),
                "full_name": context.get("full_name"),
                "phone": context.get("phone"),
                "travel_date": context.get("travel_date"),
                "travel_time": travel_time,
                "distance_km": context.get("distance_km"),
                "vehicle_type": context.get("vehicle_type") or "sedan"
            }
            final_quote = calculate_quote(quote_payload)
            final_quote["client_name"] = context.get("full_name")
            final_quote["client_phone"] = context.get("phone")
            final_quote["travel_date"] = context.get("travel_date")
            final_quote["travel_time"] = travel_time
            
            saved_quote = save_quote(final_quote)
            
            return {
                "reply": f"Your quotation {saved_quote['quote_number']} is ready. A quote is for your records and valid for 14 days. Once you pay, we will issue a Tax Invoice.\nWould you like to download it as PDF?",
                "suggestions": ["Download PDF", "Book now", "Talk to support"],
                "stage": "quote_ready",
                "quote_data": saved_quote,
                "memory_updates": _memory_updates(analysis, {
                    "stage": "quote_ready",
                    "travel_time": travel_time,
                    "quote_number": saved_quote['quote_number']
                })
            }

    # 4. Invoices and Quotes explanations
    if any(term in msg for term in ["invoice", "quotation", "quote", "difference"]):
        return {
            "reply": "A **Quotation** is an estimate of costs before you book. A **Tax Invoice** is issued after a booking is confirmed or payment is received. Which one do you need?",
            "suggestions": ["Create quote", "Get invoice", "Talk to support"],
            "stage": "greeting"
        }

    # 5. Price Enquiry / Airport Transfer
    if intent in ["price_enquiry", "airport_transfer"]:
        return {
            "reply": "I can help you with a price estimate. Let's start the booking flow to get an accurate price. What is your pickup location?",
            "suggestions": ["Windhoek CBD", "Klein Windhoek", "Hosea Kutako"],
            "stage": "collect_pickup_map",
            "memory_updates": _memory_updates(analysis, {"stage": "collect_pickup_map"})
        }

    # 6. Capabilities Enquiry
    if intent == "capabilities_enquiry":
        return {
            "reply": "I can help you check shuttle prices, create bookings, track trips, generate invoices, verify payments, or guide you through Namibia routes. How can I help?",
            "suggestions": ["Booking", "Price estimate", "Support"],
            "stage": "greeting"
        }

    # Fallback
    return {
        "reply": "I’m not sure I understood. Would you like to book a ride, check a price, or talk to support?",
        "suggestions": ["Booking", "Price estimate", "Support"],
        "stage": "greeting"
    }

def _calculate_and_respond_price(analysis: dict[str, Any], dropoff: str | None = None) -> dict[str, Any]:
    context = analysis.get("context") or {}
    pickup = context.get("pickup") or analysis["pickup"]
    dropoff = dropoff or context.get("dropoff") or analysis["dropoff"]
    
    # Use pricing engine directly for fallback
    quote = calculate_quote({
        "pickup": pickup,
        "dropoff": dropoff,
        "vehicle_type": context.get("vehicle_type") or "sedan"
    })
    
    return {
        "reply": f"Estimate for {dropoff}:\nDistance: {quote['distance_km']}km\nPrice: N${quote['final_price']:.2f}\nWould you like to proceed with this quote?",
        "suggestions": ["Yes, proceed", "Change details", "Talk to support"],
        "stage": "confirm_price",
        "quote_data": quote,
        "memory_updates": _memory_updates(analysis, {
            "dropoff": dropoff,
            "distance_km": quote['distance_km'],
            "final_price": quote['final_price'],
            "stage": "confirm_price"
        })
    }
