from __future__ import annotations

import sys
import os
from typing import Any

# Add root to sys.path
sys.path.append(os.getcwd())

from services.tarasi_bot_service import analyze_message, build_bot_reply

def test_full_booking_flow():
    print("=== Testing Full Booking Flow ===")
    session_memory = {}
    
    flow = [
        ("hi", "greeting"),
        ("Booking", "collect_pickup_map"),
        ("Nebo Street", "collect_pickup_map"), # Asks to confirm
        ("Yes", "collect_dropoff_map"),
        ("Grove Mall", "confirm_price"),
        ("Yes proceed", "collect_customer_details"),
        ("John Doe", "collect_customer_details"),
        ("0811234567", "collect_customer_details"),
        ("Tomorrow", "collect_customer_details"),
        ("08:00", "quote_ready"),
    ]
    
    for message, expected_stage in flow:
        analysis = analyze_message(message, user_memory=session_memory)
        result = build_bot_reply(message, analysis=analysis, user_memory=session_memory)
        if result.get("memory_updates"):
            session_memory.update(result["memory_updates"])
        
        print(f"User: {message: <20} | Bot Stage: {result.get('stage'): <25} | Result: {'✅' if result.get('stage') == expected_stage else '❌'}")
        if result.get('stage') != expected_stage:
            print(f"   Details: {result.get('reply')[:100]}")

def test_support_rules():
    print("\n=== Testing Support Rules ===")
    
    cases = [
        ("hi", False),
        ("booking", False),
        ("price estimate", False),
        ("I want a quote", False),
        ("Wanaheda to Airport", False),
        ("not useful", True),
        ("talk to support", True),
        ("I lost my item", True),
        ("late driver", True)
    ]
    
    for message, expect_ticket in cases:
        analysis = analyze_message(message, user_memory={})
        result = build_bot_reply(message, analysis=analysis)
        ticket_req = result.get('ticket_required', False)
        handoff_req = result.get('handoff_requested', False)
        triggered = ticket_req or handoff_req
        print(f"Msg: {message: <20} | Support Triggered: {triggered: <5} | Result: {'✅' if triggered == expect_ticket else '❌'}")

if __name__ == "__main__":
    test_full_booking_flow()
    test_support_rules()
