from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(".env")

from services.tarasi_pricing_engine import calculate_customer_quote, save_quote


TEST_CASES = [
    {
        "payload": {"pickup_text": "Katutura", "dropoff_text": "Maerua Mall", "vehicle_type": "sedan", "service_type": "town", "passengers": 1, "luggage_count": 0, "pickup_time": "14:00"},
        "allowed_dropoff": {"olympia", "maerua mall"},
    },
    {
        "payload": {"pickup_text": "Wanaheda", "dropoff_text": "Grove Mall", "vehicle_type": "sedan", "service_type": "town", "passengers": 1, "luggage_count": 0, "pickup_time": "14:00"},
        "allowed_dropoff": {"kleine kuppe", "prosperita", "grove mall"},
    },
    {
        "payload": {"pickup_text": "CBD", "dropoff_text": "Eros Airport", "vehicle_type": "sedan", "service_type": "airport", "passengers": 1, "luggage_count": 0, "pickup_time": "14:00"},
        "allowed_dropoff": {"eros airport"},
    },
    {
        "payload": {"pickup_text": "CBD", "dropoff_text": "Hilton Windhoek", "vehicle_type": "sedan", "service_type": "town", "passengers": 1, "luggage_count": 0, "pickup_time": "14:00"},
        "allowed_dropoff": {"cbd", "hilton windhoek"},
    },
    {
        "payload": {"pickup_text": "Unknown Street", "dropoff_text": "Grove Mall", "vehicle_type": "sedan", "service_type": "town", "passengers": 1, "luggage_count": 0, "pickup_time": "14:00"},
        "allowed_dropoff": {"kleine kuppe", "prosperita", "grove mall"},
        "expect_low_confidence": True,
    },
]


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def main() -> None:
    failures: list[str] = []
    for index, case in enumerate(TEST_CASES, start=1):
        payload = dict(case["payload"])
        quote = calculate_customer_quote(payload)
        saved_number = ""
        if index == 1:
            saved = save_quote(quote, session_id="taximeter-script")
            saved_number = saved.get("quote_number", "")
        dropoff_zone = _norm(quote.get("dropoff_zone"))
        if quote.get("final_price", 0) <= 0:
            failures.append(f"{payload['pickup_text']} -> {payload['dropoff_text']}: final_price <= 0")
        if case.get("allowed_dropoff") and dropoff_zone not in case["allowed_dropoff"]:
            failures.append(
                f"{payload['pickup_text']} -> {payload['dropoff_text']}: dropoff_zone={quote.get('dropoff_zone')} not in {sorted(case['allowed_dropoff'])}"
            )
        if case.get("expect_low_confidence") and _norm(quote.get("price_confidence")) != "low":
            failures.append(f"{payload['pickup_text']} -> {payload['dropoff_text']}: expected low confidence, got {quote.get('price_confidence')}")
        print(
            {
                "case": f"{payload['pickup_text']} -> {payload['dropoff_text']}",
                "quote_number": quote.get("quote_number"),
                "saved_quote_number": saved_number,
                "final_price": quote.get("final_price"),
                "distance_km": quote.get("distance_km"),
                "duration_minutes": quote.get("duration_minutes"),
                "pickup_zone": quote.get("pickup_zone"),
                "dropoff_zone": quote.get("dropoff_zone"),
                "confidence": quote.get("price_confidence"),
                "support_ticket_opened": False,
            }
        )
    if failures:
        for failure in failures:
            print({"failure": failure})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
