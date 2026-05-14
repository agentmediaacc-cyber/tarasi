create table if not exists public.tarasi_routes (
  id uuid primary key default gen_random_uuid(),
  name text,
  pickup text not null,
  dropoff text not null,
  category text default 'Route',
  region text,
  road_type text,
  distance_km numeric default 0,
  duration text,
  recommended_vehicle text,
  starting_price numeric default 0,
  comfort text default 'Premium',
  best_for text,
  status text default 'active',
  origin_lat numeric,
  origin_lng numeric,
  destination_lat numeric,
  destination_lng numeric,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.tarasi_routes enable row level security;

create policy if not exists "Public can read active Tarasi routes"
on public.tarasi_routes
for select
using (status in ('active', 'published', 'available'));

create index if not exists tarasi_routes_status_idx
on public.tarasi_routes(status);

create index if not exists tarasi_routes_created_at_idx
on public.tarasi_routes(created_at desc);
