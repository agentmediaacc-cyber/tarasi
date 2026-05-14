alter table public.tarasi_routes
add column if not exists origin_lat numeric,
add column if not exists origin_lng numeric,
add column if not exists destination_lat numeric,
add column if not exists destination_lng numeric,
add column if not exists hotspot_lat numeric,
add column if not exists hotspot_lng numeric,
add column if not exists hotspot_name text,
add column if not exists route_polyline text,
add column if not exists map_notes text,
add column if not exists live_status text default 'Available';

create index if not exists tarasi_routes_origin_coords_idx
on public.tarasi_routes(origin_lat, origin_lng);

create index if not exists tarasi_routes_destination_coords_idx
on public.tarasi_routes(destination_lat, destination_lng);
