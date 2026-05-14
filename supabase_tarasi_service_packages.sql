create table if not exists public.tarasi_service_packages (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  package_type text default 'Transport',
  description text,
  icon text,
  badge text default 'Premium',
  starting_price numeric default 0,
  duration text default 'Flexible',
  best_for text default 'Namibia travel',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.tarasi_service_packages enable row level security;

create policy if not exists "Public can read active Tarasi service packages"
on public.tarasi_service_packages
for select
using (status in ('active', 'published', 'available'));

create index if not exists tarasi_service_packages_status_idx
on public.tarasi_service_packages(status);
