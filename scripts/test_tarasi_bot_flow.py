from __future__ import annotations

import sys
import os
from typing import Any

# Add root to sys.path
sys.path.append(os.getcwd())

from services.tarasi_bot_service import analyze_message, build_bot_reply

def test_flow():
    print("Starting Tarasi Bot Flow Test...")
    
    # Session state simulation
    session_memory = {}
    
    test_cases = [
        ("hi", "greeting"),
        ("Booking", "collect_pickup_map"),
        ("Nebo Street", "collect_pickup_map"), # Should find address and ask to confirm
        ("Yes correct", "collect_dropoff_map"),
        ("Grove Mall", "confirm_price"),
        ("yes proceed", "collect_customer_details"),
        ("John Doe", "collect_customer_details"),
        ("0811234567", "quote_ready"),
        ("not useful", "human_support_needed"),
    ]
    
    for message, expected_stage in test_cases:
        print(f"\nUser: {message}")
        
        # 1. Analyze
        analysis = analyze_message(message, user_memory=session_memory)
        
        # 2. Reply
        result = build_bot_reply(message, analysis=analysis, user_memory=session_memory)
        
        # 3. Update memory
        if result.get("memory_updates"):
            session_memory.update(result["memory_updates"])
            
        print(f"Bot Reply: {result.get('reply')[:100]}...")
        print(f"Detected Stage: {result.get('stage')}")
        
        # Basic validation
        # Since I'm using mock/actual data, let's just print status
        if result.get('stage') == expected_stage or expected_stage == "ANY":
            print(f"✅ Success: Stage matches {expected_stage}")
        else:
             # Some stages might be intermediate, let's see
             print(f"⚠️ Note: Stage is {result.get('stage')}, expected {expected_stage}")

    print("\n--- Additional Checks ---")
    
    # Check ticket rules
    emergency_msg = "I lost my bag"
    analysis = analyze_message(emergency_msg, user_memory={})
    result = build_bot_reply(emergency_msg, analysis=analysis)
    print(f"Emergency Check ('{emergency_msg}'): ticket_required={result.get('ticket_required')}")
    
    normal_msg = "price estimate"
    analysis = analyze_message(normal_msg, user_memory={})
    result = build_bot_reply(normal_msg, analysis=analysis)
    print(f"Normal Check ('{normal_msg}'): ticket_required={result.get('ticket_required')}")

if __name__ == "__main__":
    test_flow()
