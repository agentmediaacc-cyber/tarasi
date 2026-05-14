create extension if not exists pgcrypto;

create table if not exists tarasi_bot_conversations (
    id uuid primary key default gen_random_uuid(),
    session_id text not null,
    user_id text null,
    user_name text null,
    user_phone text null,
    user_email text null,
    client_type text,
    mood text,
    current_intent text,
    last_topic text,
    status text default 'open',
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_tarasi_bot_conversations_session_id
    on tarasi_bot_conversations(session_id);

create table if not exists tarasi_bot_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid references tarasi_bot_conversations(id) on delete cascade,
    sender text not null,
    message text,
    detected_intent text,
    detected_mood text,
    bot_reply text,
    confidence numeric default 0,
    created_at timestamptz default now()
);

create index if not exists idx_tarasi_bot_messages_conversation_id
    on tarasi_bot_messages(conversation_id);

create table if not exists tarasi_bot_tickets (
    id uuid primary key default gen_random_uuid(),
    ticket_number text unique not null,
    conversation_id uuid null references tarasi_bot_conversations(id) on delete set null,
    user_id text null,
    ticket_type text not null,
    priority text default 'normal',
    status text default 'open',
    subject text,
    description text,
    admin_notes text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_tarasi_bot_tickets_status
    on tarasi_bot_tickets(status);

create table if not exists tarasi_bot_reviews (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid null references tarasi_bot_conversations(id) on delete set null,
    user_id text null,
    rating int,
    review_text text,
    sentiment text,
    created_at timestamptz default now()
);

create table if not exists tarasi_bot_user_memory (
    id uuid primary key default gen_random_uuid(),
    user_key text unique not null,
    favorite_routes jsonb default '[]'::jsonb,
    preferred_vehicle text,
    airport_habits jsonb default '{}'::jsonb,
    payment_style text,
    tourist_interests jsonb default '[]'::jsonb,
    previous_complaints jsonb default '[]'::jsonb,
    frequent_pickups jsonb default '[]'::jsonb,
    last_context jsonb default '{}'::jsonb,
    client_type text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create table if not exists tarasi_drivers (
    id uuid primary key default gen_random_uuid(),
    name text,
    phone text,
    vehicle_type text,
    vehicle_name text,
    status text default 'offline',
    current_zone text,
    rating numeric default 5,
    languages text[],
    vip_suitable boolean default false,
    created_at timestamptz default now()
);
