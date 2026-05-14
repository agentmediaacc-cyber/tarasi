-- Tarasi Performance Optimization Indexes (Corrected for Real Neon Schema)
-- Focus on speed for admin dashboard and operational queries

-- Bookings optimization
CREATE INDEX IF NOT EXISTS idx_bookings_created_at ON bookings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_reference ON bookings(reference);
CREATE INDEX IF NOT EXISTS idx_bookings_customer_email ON bookings(email);

-- Support Tickets optimization
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_created_at ON support_tickets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_email ON support_tickets(email);

-- Payments & Invoices
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payments_payment_status ON payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number);

-- Fleet & Drivers
CREATE INDEX IF NOT EXISTS idx_drivers_status ON drivers(status);
CREATE INDEX IF NOT EXISTS idx_drivers_created_at ON drivers(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
CREATE INDEX IF NOT EXISTS idx_vehicles_created_at ON vehicles(created_at DESC);

-- Analytics & Reporting
CREATE INDEX IF NOT EXISTS idx_bookings_pickup_date ON bookings(pickup_date DESC);
CREATE INDEX IF NOT EXISTS idx_tarasi_users_email ON tarasi_users(email);
CREATE INDEX IF NOT EXISTS idx_routes_created_at ON routes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tours_created_at ON tours(created_at DESC);
