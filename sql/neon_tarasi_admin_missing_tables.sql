CREATE TABLE IF NOT EXISTS pricing_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_name TEXT,
  rule_type TEXT,
  vehicle_type TEXT,
  value NUMERIC(12,2) DEFAULT 0,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pricing_rules_active
ON pricing_rules(is_active);

CREATE INDEX IF NOT EXISTS idx_pricing_rules_type
ON pricing_rules(rule_type, vehicle_type);

CREATE TABLE IF NOT EXISTS pricing_zones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone_name TEXT,
  suburb_area TEXT,
  description TEXT,
  base_fare NUMERIC(12,2) DEFAULT 0,
  price_per_km NUMERIC(12,2) DEFAULT 0,
  airport_fee NUMERIC(12,2) DEFAULT 0,
  minimum_fare NUMERIC(12,2) DEFAULT 0,
  night_fee NUMERIC(12,2) DEFAULT 0,
  luggage_fee NUMERIC(12,2) DEFAULT 0,
  waiting_fee NUMERIC(12,2) DEFAULT 0,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  map_radius_km NUMERIC(8,2) DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pricing_zones_active
ON pricing_zones(is_active);

CREATE INDEX IF NOT EXISTS idx_pricing_zones_name
ON pricing_zones(zone_name);

CREATE INDEX IF NOT EXISTS idx_pricing_zones_suburb
ON pricing_zones(suburb_area);

CREATE TABLE IF NOT EXISTS homepage_content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  section_name TEXT,
  content JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_homepage_content_section
ON homepage_content(section_name);

CREATE TABLE IF NOT EXISTS quotes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quote_number TEXT,
  user_id TEXT,
  session_id TEXT,
  customer_name TEXT,
  email TEXT,
  phone TEXT,
  pickup_text TEXT,
  dropoff_text TEXT,
  pickup_zone TEXT,
  dropoff_zone TEXT,
  distance_km NUMERIC(12,2) DEFAULT 0,
  duration_minutes INTEGER DEFAULT 0,
  vehicle_type TEXT,
  passengers INTEGER DEFAULT 1,
  luggage_count INTEGER DEFAULT 0,
  service_type TEXT,
  base_fare NUMERIC(12,2) DEFAULT 0,
  distance_fee NUMERIC(12,2) DEFAULT 0,
  zone_fee NUMERIC(12,2) DEFAULT 0,
  waiting_fee NUMERIC(12,2) DEFAULT 0,
  luggage_fee NUMERIC(12,2) DEFAULT 0,
  night_fee NUMERIC(12,2) DEFAULT 0,
  service_fee NUMERIC(12,2) DEFAULT 0,
  subtotal NUMERIC(12,2) DEFAULT 0,
  driver_payout NUMERIC(12,2) DEFAULT 0,
  tarasi_commission NUMERIC(12,2) DEFAULT 0,
  estimated_profit NUMERIC(12,2) DEFAULT 0,
  amount NUMERIC(12,2) DEFAULT 0,
  final_price NUMERIC(12,2) DEFAULT 0,
  currency TEXT DEFAULT 'NAD',
  price_confidence TEXT,
  pricing_notes TEXT,
  status TEXT DEFAULT 'quoted',
  pdf_url TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_quotes_number
ON quotes(quote_number);

CREATE INDEX IF NOT EXISTS idx_quotes_created
ON quotes(created_at DESC);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_user_id TEXT,
  admin_email TEXT,
  action TEXT,
  table_name TEXT,
  record_id TEXT,
  old_value JSONB,
  new_value JSONB,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_created
ON admin_audit_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_action
ON admin_audit_logs(action);

CREATE TABLE IF NOT EXISTS fleet_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fleet_groups_name
ON fleet_groups(name);

CREATE TABLE IF NOT EXISTS driver_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID,
  document_type TEXT,
  document_url TEXT,
  status TEXT DEFAULT 'active',
  expiry_date DATE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_driver_documents_driver
ON driver_documents(driver_id);

CREATE TABLE IF NOT EXISTS vehicle_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id UUID,
  document_type TEXT,
  document_url TEXT,
  status TEXT DEFAULT 'active',
  expiry_date DATE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vehicle_documents_vehicle
ON vehicle_documents(vehicle_id);

CREATE TABLE IF NOT EXISTS bot_training_data (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  category TEXT,
  keywords JSONB DEFAULT '[]'::jsonb,
  content TEXT,
  priority INTEGER DEFAULT 5,
  linked_id UUID,
  is_active BOOLEAN DEFAULT TRUE,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bot_training_data_category
ON bot_training_data(category, is_active);

CREATE TABLE IF NOT EXISTS bot_faq (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question TEXT,
  answer TEXT,
  category TEXT,
  priority INTEGER DEFAULT 5,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bot_faq_category
ON bot_faq(category, is_active);

CREATE TABLE IF NOT EXISTS bot_route_knowledge (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  route_name TEXT,
  pickup_zone TEXT,
  dropoff_zone TEXT,
  vehicle_type TEXT,
  guidance_text TEXT,
  price_hint NUMERIC(12,2),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bot_route_knowledge_route
ON bot_route_knowledge(route_name, is_active);
