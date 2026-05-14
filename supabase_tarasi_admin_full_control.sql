-- Supabase/Neon SQL for Tarasi Admin Full Control
-- SAFE CREATE TABLE IF NOT EXISTS

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Admin Users & Roles
CREATE TABLE IF NOT EXISTS admin_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name TEXT UNIQUE NOT NULL, -- owner, manager, finance, support, dispatcher, marketing
    permissions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role_id UUID REFERENCES admin_roles(id),
    status TEXT DEFAULT 'active', -- active, disabled
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Audit Logs
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID REFERENCES admin_users(id),
    admin_email TEXT,
    action TEXT NOT NULL, -- create, update, delete, login, etc.
    table_name TEXT,
    record_id TEXT,
    old_value JSONB,
    new_value JSONB,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Pricing Zones & Rules
CREATE TABLE IF NOT EXISTS pricing_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_name TEXT UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pricing_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL, -- base_fare, per_km, minimum_fare, airport_fee, luggage_fee, night_fee, waiting_fee, vehicle_multiplier
    vehicle_type TEXT,
    zone_id UUID REFERENCES pricing_zones(id),
    value NUMERIC NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Fleet Management
CREATE TABLE IF NOT EXISTS vehicle_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_name TEXT UNIQUE NOT NULL, -- Sedan, SUV, Minibus, etc.
    capacity_passengers INT,
    capacity_luggage TEXT,
    multiplier NUMERIC DEFAULT 1.0,
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fleet_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Extend existing vehicles table if needed (via separate migration if already exists)
-- This SQL is for new setup or manual run
CREATE TABLE IF NOT EXISTS vehicles_new (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    vehicle_type TEXT,
    plate_number TEXT UNIQUE,
    fleet_group_id UUID REFERENCES fleet_groups(id),
    status TEXT DEFAULT 'available', -- available, maintenance, busy, offline
    current_driver_id UUID,
    seats INT,
    luggage_capacity TEXT,
    last_maintenance_date DATE,
    next_maintenance_date DATE,
    documents_status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Drivers Extension
CREATE TABLE IF NOT EXISTS driver_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL,
    document_type TEXT NOT NULL, -- license, insurance, permit
    document_url TEXT NOT NULL,
    expiry_date DATE,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Bot & Support
CREATE TABLE IF NOT EXISTS bot_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT, -- email or session_id
    customer_name TEXT,
    status TEXT DEFAULT 'active', -- active, transferred, closed
    last_message_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES bot_conversations(id),
    sender TEXT NOT NULL, -- user, bot, admin
    sender_name TEXT,
    message_text TEXT,
    is_useful BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 7. Finance: Refunds & Coupons
CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID,
    booking_reference TEXT,
    amount NUMERIC NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending', -- pending, completed, rejected
    processed_by UUID REFERENCES admin_users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS coupons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT UNIQUE NOT NULL,
    discount_type TEXT NOT NULL, -- percentage, fixed
    discount_value NUMERIC NOT NULL,
    max_uses INT,
    current_uses INT DEFAULT 0,
    expiry_date TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 8. Marketing & Content
CREATE TABLE IF NOT EXISTS marketing_banners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    subtitle TEXT,
    image_url TEXT,
    link_url TEXT,
    priority INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type TEXT DEFAULT 'all', -- all, customer, driver, admin
    target_id TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS homepage_content (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_name TEXT UNIQUE NOT NULL,
    content JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 9. Initial Data
INSERT INTO admin_roles (role_name, permissions) VALUES 
('owner', '{"all": true}'),
('manager', '{"bookings": true, "drivers": true, "fleet": true, "support": true}'),
('finance', '{"payments": true, "invoices": true, "refunds": true, "reports": true}'),
('support', '{"support": true, "bot": true, "bookings": "view"}'),
('dispatcher', '{"bookings": true, "drivers": "view", "fleet": "view"}'),
('marketing', '{"content": true, "coupons": true, "tours": true}');

-- Add initial admins
INSERT INTO admin_users (email, full_name, role_id) 
SELECT 'magnus@tarasi.com', 'Magnus', id FROM admin_roles WHERE role_name = 'owner'
ON CONFLICT (email) DO NOTHING;

INSERT INTO admin_users (email, full_name, role_id) 
SELECT 'kasera@tarasi.com', 'Kasera', id FROM admin_roles WHERE role_name = 'owner'
ON CONFLICT (email) DO NOTHING;

-- Seed some pricing rules if empty
INSERT INTO pricing_rules (rule_name, rule_type, value) VALUES
('Base Fare', 'base_fare', 50),
('Price per KM', 'per_km', 15),
('Minimum Fare', 'minimum_fare', 100),
('Airport Fee', 'airport_fee', 200),
('Night Fee', 'night_fee', 50);
