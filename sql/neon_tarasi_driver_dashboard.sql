-- Tarasi Driver Dashboard & Operational Schema
-- Neon Production Schema

-- Live Tracking
CREATE TABLE IF NOT EXISTS live_driver_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id TEXT NOT NULL, -- Links to drivers(driver_id) or drivers(id)
    booking_id TEXT, -- Optional, current active booking
    lat DECIMAL(10, 8) NOT NULL,
    lng DECIMAL(11, 8) NOT NULL,
    speed DECIMAL(5, 2), -- in km/h
    heading DECIMAL(5, 2), -- 0-360 degrees
    accuracy DECIMAL(5, 2), -- in meters
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_live_driver_locations_driver_id ON live_driver_locations(driver_id);
CREATE INDEX IF NOT EXISTS idx_live_driver_locations_created_at ON live_driver_locations(created_at DESC);

-- Driver Trip Events (Logs for every status change)
CREATE TABLE IF NOT EXISTS driver_trip_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id TEXT NOT NULL,
    booking_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- accepted, started, arrived_pickup, picked_up, arrived_dropoff, completed, rejected
    lat DECIMAL(10, 8),
    lng DECIMAL(11, 8),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_driver_trip_events_booking_id ON driver_trip_events(booking_id);

-- Driver Documents
CREATE TABLE IF NOT EXISTS driver_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    document_url TEXT NOT NULL,
    expiry_date DATE,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected, expired
    verified_at TIMESTAMP WITH TIME ZONE,
    verified_by UUID, -- admin_user_id
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Ensure drivers table has necessary operational fields
-- We add columns if they don't exist in the lean version found in audit
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle_id TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle_name TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS based_area TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS service_type TEXT;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS verification_status TEXT DEFAULT 'Pending';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS admin_approved BOOLEAN DEFAULT FALSE;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS total_trips INTEGER DEFAULT 0;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS completed_trips INTEGER DEFAULT 0;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS cancelled_trips INTEGER DEFAULT 0;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS balance DECIMAL(12, 2) DEFAULT 0.00;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS current_lat DECIMAL(10, 8);
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS current_lng DECIMAL(11, 8);
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location_at TIMESTAMP WITH TIME ZONE;
