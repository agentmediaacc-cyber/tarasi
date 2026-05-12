from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from services.booking_service import create_booking
def main():
    print("creating_test_booking", flush=True)

    booking = create_booking(
        {
            "booking_type": "once-off",
            "full_name": "Tarasi Dev Test Booking",
            "phone": "+264810000001",
            "email": "dev-booking@tarasi.test",
            "pickup_location": "Windhoek",
            "dropoff_location": "Hosea Kutako Airport",
            "pickup": "Windhoek",
            "dropoff": "Hosea Kutako Airport",
            "date": "2026-05-15",
            "time": "09:30",
            "passengers": "2",
            "luggage": "2 bags",
            "preferred_vehicle": "Toyota Quantum",
            "amount": "850",
            "notes": "DEV ONLY TEST BOOKING. Safe test record created through booking_service.py.",
            "metadata": {
                "is_test_booking": True,
                "dev_test": True,
                "created_by_script": "scripts/create_test_booking.py",
                "dev_only": True,
            },
        }
    )
    print(booking["reference"], flush=True)


if __name__ == "__main__":
    main()
