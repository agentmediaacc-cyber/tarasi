create extension if not exists pgcrypto;

create table if not exists tarasi_booking_quotes (
    id uuid primary key default gen_random_uuid(),
    quote_number text unique not null,
    user_id text null,
    session_id text not null,
    pickup_text text,
    dropoff_text text,
    pickup_zone text,
    dropoff_zone text,
    distance_km numeric,
    duration_minutes numeric,
    vehicle_type text,
    passengers int,
    luggage_count int,
    service_type text,
    base_fare numeric,
    distance_fee numeric,
    zone_fee numeric,
    waiting_fee numeric,
    luggage_fee numeric,
    night_fee numeric,
    service_fee numeric,
    subtotal numeric,
    driver_payout numeric,
    tarasi_commission numeric,
    estimated_profit numeric,
    final_price numeric,
    price_confidence text,
    pricing_notes text,
    status text default 'quoted',
    created_at timestamptz default now()
);

create index if not exists idx_tarasi_booking_quotes_quote_number
    on tarasi_booking_quotes(quote_number);

create table if not exists tarasi_bookings (
    id uuid primary key default gen_random_uuid(),
    booking_number text unique not null,
    quote_id uuid null,
    user_id text null,
    session_id text not null,
    client_name text,
    client_phone text,
    pickup_text text,
    dropoff_text text,
    pickup_zone text,
    dropoff_zone text,
    travel_date date null,
    travel_time time null,
    vehicle_type text,
    passengers int,
    luggage_count int,
    service_type text,
    final_price numeric,
    driver_id uuid null,
    status text default 'pending',
    payment_status text default 'unpaid',
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_tarasi_bookings_booking_number
    on tarasi_bookings(booking_number);

create table if not exists tarasi_booking_status_history (
    id uuid primary key default gen_random_uuid(),
    booking_id uuid,
    status text,
    note text,
    created_at timestamptz default now()
);

create index if not exists idx_tarasi_booking_status_history_booking_id
    on tarasi_booking_status_history(booking_id);
