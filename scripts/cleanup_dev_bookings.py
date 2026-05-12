from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from services.db_service import get_neon_connection, resolve_table_name


def main():
    table_name = resolve_table_name("bookings")
    if not table_name:
        raise SystemExit("Bookings table is not available.")

    with get_neon_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                delete from {table_name}
                where coalesce((metadata->>'dev_test')::boolean, false) = true
                   or coalesce((metadata->>'dev_only')::boolean, false) = true
                   or coalesce((metadata->>'is_test_booking')::boolean, false) = true
                returning reference
                """
            )
            rows = cursor.fetchall()
        conn.commit()

    print(f"deleted_dev_bookings={len(rows)}")
    for row in rows:
        print(row["reference"])


if __name__ == "__main__":
    main()
