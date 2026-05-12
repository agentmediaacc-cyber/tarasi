create extension if not exists pgcrypto;

create or replace function bookme_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists bookme_users (
  id uuid primary key default gen_random_uuid(),
  supabase_user_id text unique,
  full_name text,
  email text unique,
  phone text,
  account_type text,
  avatar_url text,
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists customers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references bookme_users(id),
  customer_type text,
  preferred_contact text,
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists drivers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references bookme_users(id),
  driver_code text unique,
  license_number text,
  phone text,
  status text default 'pending',
  rating numeric default 5.0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists vehicles (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid references drivers(id),
  name text,
  vehicle_type text,
  plate_number text unique,
  seats int,
  luggage_capacity text,
  aircon boolean default true,
  image_url text,
  status text default 'available',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists routes (
  id uuid primary key default gen_random_uuid(),
  pickup text,
  dropoff text,
  distance_km numeric,
  base_price numeric,
  price_per_extra_passenger numeric default 0,
  vehicle_type text,
  route_type text,
  is_active boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists bookings (
  id uuid primary key default gen_random_uuid(),
  reference text unique not null,
  user_id uuid references bookme_users(id),
  customer_name text not null,
  phone text not null,
  email text,
  booking_type text not null,
  pickup_location text,
  dropoff_location text,
  pickup_date date,
  pickup_time time,
  return_date date,
  return_time time,
  passengers int default 1,
  luggage text,
  preferred_vehicle text,
  estimated_price numeric,
  status text default 'booking_received',
  payment_status text default 'pending',
  storage_source text default 'neon',
  notes text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists booking_status_history (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid references bookings(id) on delete cascade,
  status text not null,
  note text,
  changed_by uuid references bookme_users(id),
  created_at timestamptz default now()
);

create table if not exists tours (
  id uuid primary key default gen_random_uuid(),
  slug text unique,
  title text,
  destination text,
  duration text,
  price_from numeric,
  description text,
  itinerary jsonb default '[]'::jsonb,
  includes jsonb default '[]'::jsonb,
  image_url text,
  is_active boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists school_transport_profiles (
  id uuid primary key default gen_random_uuid(),
  guardian_user_id uuid references bookme_users(id),
  child_full_name text,
  child_grade text,
  school_name text,
  morning_pickup text,
  afternoon_dropoff text,
  emergency_contact text,
  weekdays jsonb default '[]'::jsonb,
  safety_notes text,
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists monthly_plans (
  id uuid primary key default gen_random_uuid(),
  plan_name text,
  plan_type text,
  price_from numeric,
  billing_cycle text default 'monthly',
  features jsonb default '[]'::jsonb,
  is_active boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists support_tickets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references bookme_users(id),
  name text,
  phone text,
  email text,
  category text,
  message text,
  status text default 'open',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists payments (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid references bookings(id),
  amount numeric,
  currency text default 'NAD',
  payment_method text,
  payment_status text default 'pending',
  transaction_reference text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists invoices (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid references bookings(id),
  invoice_number text unique,
  customer_name text,
  amount numeric,
  currency text default 'NAD',
  status text default 'draft',
  pdf_url text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_bookme_users_email on bookme_users(email);
create index if not exists idx_bookme_users_supabase_user_id on bookme_users(supabase_user_id);
create index if not exists idx_customers_user_id on customers(user_id);
create index if not exists idx_drivers_user_id on drivers(user_id);
create index if not exists idx_drivers_status on drivers(status);
create index if not exists idx_vehicles_driver_id on vehicles(driver_id);
create index if not exists idx_vehicles_status on vehicles(status);
create index if not exists idx_routes_pickup_dropoff on routes(pickup, dropoff);
create index if not exists idx_routes_active on routes(is_active);
create index if not exists idx_bookings_reference on bookings(reference);
create index if not exists idx_bookings_user_id on bookings(user_id);
create index if not exists idx_bookings_status on bookings(status);
create index if not exists idx_bookings_pickup_date on bookings(pickup_date);
create index if not exists idx_booking_status_history_booking_id on booking_status_history(booking_id);
create index if not exists idx_tours_slug on tours(slug);
create index if not exists idx_tours_active on tours(is_active);
create index if not exists idx_school_transport_guardian_user_id on school_transport_profiles(guardian_user_id);
create index if not exists idx_monthly_plans_active on monthly_plans(is_active);
create index if not exists idx_support_tickets_user_id on support_tickets(user_id);
create index if not exists idx_support_tickets_status on support_tickets(status);
create index if not exists idx_payments_booking_id on payments(booking_id);
create index if not exists idx_invoices_booking_id on invoices(booking_id);

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'trg_bookme_users_updated_at') then
    create trigger trg_bookme_users_updated_at before update on bookme_users for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_customers_updated_at') then
    create trigger trg_customers_updated_at before update on customers for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_drivers_updated_at') then
    create trigger trg_drivers_updated_at before update on drivers for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_vehicles_updated_at') then
    create trigger trg_vehicles_updated_at before update on vehicles for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_routes_updated_at') then
    create trigger trg_routes_updated_at before update on routes for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_bookings_updated_at') then
    create trigger trg_bookings_updated_at before update on bookings for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_tours_updated_at') then
    create trigger trg_tours_updated_at before update on tours for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_school_transport_profiles_updated_at') then
    create trigger trg_school_transport_profiles_updated_at before update on school_transport_profiles for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_monthly_plans_updated_at') then
    create trigger trg_monthly_plans_updated_at before update on monthly_plans for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_support_tickets_updated_at') then
    create trigger trg_support_tickets_updated_at before update on support_tickets for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_payments_updated_at') then
    create trigger trg_payments_updated_at before update on payments for each row execute function bookme_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_invoices_updated_at') then
    create trigger trg_invoices_updated_at before update on invoices for each row execute function bookme_set_updated_at();
  end if;
end
$$;

insert into routes (pickup, dropoff, distance_km, base_price, price_per_extra_passenger, vehicle_type, route_type)
select 'Windhoek', 'Hosea Kutako Airport', 45, 850, 120, 'Toyota Quantum', 'Airport transfer'
where not exists (select 1 from routes where pickup = 'Windhoek' and dropoff = 'Hosea Kutako Airport');

insert into routes (pickup, dropoff, distance_km, base_price, price_per_extra_passenger, vehicle_type, route_type)
select 'Windhoek', 'Swakopmund', 361, 950, 180, 'Minibus', 'Tourist route'
where not exists (select 1 from routes where pickup = 'Windhoek' and dropoff = 'Swakopmund');

insert into routes (pickup, dropoff, distance_km, base_price, price_per_extra_passenger, vehicle_type, route_type)
select 'Windhoek', 'Etosha', 420, 1800, 220, 'SUV', 'Tourist route'
where not exists (select 1 from routes where pickup = 'Windhoek' and dropoff = 'Etosha');

insert into routes (pickup, dropoff, distance_km, base_price, price_per_extra_passenger, vehicle_type, route_type)
select 'Windhoek', 'Sossusvlei', 350, 1650, 200, 'SUV', 'Tourist route'
where not exists (select 1 from routes where pickup = 'Windhoek' and dropoff = 'Sossusvlei');

insert into routes (pickup, dropoff, distance_km, base_price, price_per_extra_passenger, vehicle_type, route_type)
select 'Windhoek', 'Rundu', 703, 2250, 250, 'Bus', 'Long-distance shuttle'
where not exists (select 1 from routes where pickup = 'Windhoek' and dropoff = 'Rundu');

insert into vehicles (name, vehicle_type, plate_number, seats, luggage_capacity, aircon, image_url, status)
select 'Toyota Quantum', 'Shuttle Van', 'TAR-QUANTUM-001', 14, '10 bags', true, null, 'available'
where not exists (select 1 from vehicles where plate_number = 'TAR-QUANTUM-001');

insert into vehicles (name, vehicle_type, plate_number, seats, luggage_capacity, aircon, image_url, status)
select 'SUV', 'Executive SUV', 'TAR-SUV-001', 6, '5 bags', true, null, 'available'
where not exists (select 1 from vehicles where plate_number = 'TAR-SUV-001');

insert into vehicles (name, vehicle_type, plate_number, seats, luggage_capacity, aircon, image_url, status)
select 'Minibus', 'Minibus', 'TAR-MINI-001', 22, '16 bags', true, null, 'available'
where not exists (select 1 from vehicles where plate_number = 'TAR-MINI-001');

insert into tours (slug, title, destination, duration, price_from, description, itinerary, includes, image_url, is_active)
select
  'sossusvlei-desert-experience',
  'Sossusvlei Desert Experience',
  'Sossusvlei',
  '2 days',
  4900,
  'Sunrise dunes, lodge pickups and premium desert transfers.',
  '["Windhoek pickup","Desert route transfer","Dune sunrise coordination","Sesriem return"]'::jsonb,
  '["Transport","Driver coordination","Water"]'::jsonb,
  null,
  true
where not exists (select 1 from tours where slug = 'sossusvlei-desert-experience');

insert into tours (slug, title, destination, duration, price_from, description, itinerary, includes, image_url, is_active)
select
  'etosha-safari-shuttle',
  'Etosha Safari Shuttle',
  'Etosha',
  '2-3 days',
  5600,
  'Safari-focused road transfer for couples, families and groups.',
  '["Pickup","Northbound route","Safari stopovers","Lodge drop-off"]'::jsonb,
  '["Transport","Cooling water","Route planning"]'::jsonb,
  null,
  true
where not exists (select 1 from tours where slug = 'etosha-safari-shuttle');

insert into tours (slug, title, destination, duration, price_from, description, itinerary, includes, image_url, is_active)
select
  'swakopmund-coastal-adventure',
  'Swakopmund Coastal Adventure',
  'Swakopmund',
  'Full day',
  3850,
  'Ocean roads, dune scenery and premium coastal mobility.',
  '["Departure","Coastal transfer","Activity windows","Evening return"]'::jsonb,
  '["Transport","Refreshments","Coordination"]'::jsonb,
  null,
  true
where not exists (select 1 from tours where slug = 'swakopmund-coastal-adventure');

insert into monthly_plans (plan_name, plan_type, price_from, billing_cycle, features, is_active)
select
  'Family monthly shuttle',
  'family',
  2900,
  'monthly',
  '["Fixed morning and afternoon timing","Shared family billing","Priority support"]'::jsonb,
  true
where not exists (select 1 from monthly_plans where plan_name = 'Family monthly shuttle');

insert into monthly_plans (plan_name, plan_type, price_from, billing_cycle, features, is_active)
select
  'School monthly plan',
  'school',
  2200,
  'monthly',
  '["Guardian updates","Attendance checklist","Emergency contact support"]'::jsonb,
  true
where not exists (select 1 from monthly_plans where plan_name = 'School monthly plan');

insert into monthly_plans (plan_name, plan_type, price_from, billing_cycle, features, is_active)
select
  'Company employee transport',
  'business',
  6500,
  'monthly',
  '["Recurring staff routes","Flexible pickups","Invoice billing"]'::jsonb,
  true
where not exists (select 1 from monthly_plans where plan_name = 'Company employee transport');
