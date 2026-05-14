-- Tarasi Phase 2: Live Operations & Advanced Control
-- SAFE CREATE TABLE IF NOT EXISTS

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Live Operations
CREATE TABLE IF NOT EXISTS live_trip_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_reference TEXT NOT NULL,
    event_type TEXT NOT NULL, -- pickup_arrived, passenger_picked_up, delay_reported, emergency_reported, etc.
    event_message TEXT,
    lat NUMERIC,
    lng NUMERIC,
    status_color TEXT DEFAULT 'green', -- green, orange, red
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS live_driver_locations (
    driver_id UUID PRIMARY KEY,
    lat NUMERIC NOT NULL,
    lng NUMERIC NOT NULL,
    bearing NUMERIC,
    speed NUMERIC,
    last_updated TIMESTAMPTZ DEFAULT now()
);

-- 2. Advanced Pricing
CREATE TABLE IF NOT EXISTS surge_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL,
    multiplier NUMERIC DEFAULT 1.0,
    is_active BOOLEAN DEFAULT true,
    start_time TIME,
    end_time TIME,
    conditions JSONB DEFAULT '{}'::jsonb, -- e.g. {"weather": "rainy", "zone": "Airport"}
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corporate_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT UNIQUE NOT NULL,
    contact_person TEXT,
    email TEXT UNIQUE,
    billing_address TEXT,
    pricing_multiplier NUMERIC DEFAULT 1.0,
    credit_limit NUMERIC DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Bot Training & Knowledge
CREATE TABLE IF NOT EXISTS bot_training_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_failed_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_message TEXT NOT NULL,
    bot_reply TEXT,
    session_id TEXT,
    confidence NUMERIC,
    reason TEXT, -- low_confidence, no_match, human_required
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Finance & Payouts
CREATE TABLE IF NOT EXISTS driver_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID REFERENCES drivers(id),
    amount NUMERIC NOT NULL,
    currency TEXT DEFAULT 'NAD',
    status TEXT DEFAULT 'pending', -- pending, processed, failed
    payout_method TEXT,
    reference_period TEXT, -- e.g. "May 2026"
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Security & Sessions
CREATE TABLE IF NOT EXISTS security_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email TEXT,
    event_type TEXT NOT NULL, -- login_attempt, login_success, login_failure, record_delete, pricing_change
    ip_address TEXT,
    user_agent TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID REFERENCES admin_users(id),
    session_token TEXT UNIQUE NOT NULL,
    ip_address TEXT,
    last_activity TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Support Assignments
CREATE TABLE IF NOT EXISTS support_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID REFERENCES support_tickets(id),
    admin_id UUID REFERENCES admin_users(id),
    assigned_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'assigned' -- assigned, reassigned, unassigned
);

-- 7. Document Management tracking
-- (Assuming driver_documents and vehicle_documents tables were already planned or created in Phase 1)
-- We add some columns for auto-blocking logic support if they are missing
ALTER TABLE IF EXISTS driver_documents 
    ADD COLUMN IF NOT EXISTS auto_block_on_expiry BOOLEAN DEFAULT true;

ALTER TABLE IF EXISTS vehicle_documents 
    ADD COLUMN IF NOT EXISTS auto_block_on_expiry BOOLEAN DEFAULT true;

-- 8. Indexes for Phase 2 Performance
CREATE INDEX IF NOT EXISTS idx_live_trip_events_ref ON live_trip_events(booking_reference);
CREATE INDEX IF NOT EXISTS idx_security_logs_email ON security_logs(user_email);
CREATE INDEX IF NOT EXISTS idx_bot_failed_replies_created ON bot_failed_replies(created_at);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_status ON driver_payouts(status);

-- Seed initial surge rules
INSERT INTO surge_rules (rule_name, multiplier, conditions) VALUES
('Night Surge', 1.25, '{"start_hour": 21, "end_hour": 5}'),
('Peak Hour Morning', 1.15, '{"start_hour": 7, "end_hour": 9}'),
('Peak Hour Evening', 1.15, '{"start_hour": 16, "end_hour": 18}');
