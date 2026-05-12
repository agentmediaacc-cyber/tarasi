from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from services.booking_service import BOOKING_STATUSES
from services.db_service import EXPECTED_TABLES, get_neon_connection, resolve_table_name


def main():
    missing_tables = [table for table in EXPECTED_TABLES if not resolve_table_name(table)]
    if missing_tables:
        print("missing_tables", ",".join(missing_tables))
        raise SystemExit(1)

    bookings_table = resolve_table_name("bookings")
    with get_neon_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"select reference, customer_name, phone, booking_type, status from {bookings_table}")
            rows = [dict(row) for row in cursor.fetchall()]

    references = [row["reference"] for row in rows if row.get("reference")]
    duplicates = [ref for ref, count in Counter(references).items() if count > 1]
    valid_statuses = {status.lower().replace(" ", "_") for status in BOOKING_STATUSES}
    invalid_statuses = [row["reference"] for row in rows if str(row.get("status", "")).strip().lower() not in valid_statuses]
    incomplete_rows = [
        row["reference"] for row in rows
        if not row.get("reference") or not row.get("customer_name") or not row.get("phone") or not row.get("booking_type")
    ]

    print(f"tables_ok={True}")
    print(f"booking_rows={len(rows)}")
    print(f"duplicate_references={len(duplicates)}")
    print(f"invalid_status_rows={len(invalid_statuses)}")
    print(f"incomplete_booking_rows={len(incomplete_rows)}")

    if duplicates:
        print("duplicate_list", ",".join(duplicates))
    if invalid_statuses:
        print("invalid_status_list", ",".join(invalid_statuses))
    if incomplete_rows:
        print("incomplete_list", ",".join(incomplete_rows))

    if duplicates or invalid_statuses or incomplete_rows:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
