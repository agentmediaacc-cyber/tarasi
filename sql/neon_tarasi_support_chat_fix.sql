CREATE TABLE IF NOT EXISTS tarasi_support_chats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT,
  user_email TEXT,
  user_phone TEXT,
  customer_name TEXT,
  status TEXT DEFAULT 'waiting',
  assigned_admin_email TEXT,
  last_message TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tarasi_support_chats_session
ON tarasi_support_chats(session_id);

CREATE INDEX IF NOT EXISTS idx_tarasi_support_chats_status
ON tarasi_support_chats(status);
