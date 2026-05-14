create extension if not exists pgcrypto;

create table if not exists tarasi_booking_payments (
    id uuid primary key default gen_random_uuid(),
    booking_id uuid null,
    booking_number text,
    payment_reference text unique,
    amount numeric,
    payment_method text default 'bank_transfer',
    proof_url text,
    status text default 'pending',
    admin_notes text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create table if not exists tarasi_booking_invoices (
    id uuid primary key default gen_random_uuid(),
    booking_id uuid null,
    booking_number text,
    invoice_number text unique,
    document_type text default 'Invoice',
    client_name text,
    client_phone text,
    pickup_text text,
    dropoff_text text,
    vehicle_type text,
    service_type text,
    amount numeric,
    payment_status text default 'unpaid',
    status text default 'issued',
    qr_url text,
    created_at timestamptz default now()
);

alter table if exists tarasi_bookings
    add column if not exists proof_url text,
    add column if not exists invoice_number text,
    add column if not exists assigned_driver_id uuid,
    add column if not exists assigned_driver_name text,
    add column if not exists assigned_vehicle text;
