-- Tarasi Live Support & Admin Notifications

CREATE TABLE IF NOT EXISTS tarasi_support_chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_number TEXT UNIQUE NOT NULL,
    conversation_id UUID REFERENCES tarasi_bot_conversations(id) ON DELETE SET NULL,
    session_id TEXT NOT NULL,
    user_id TEXT,
    user_name TEXT,
    user_phone TEXT,
    status TEXT DEFAULT 'waiting', -- waiting, active, closed
    assigned_admin TEXT,
    handoff_reason TEXT,
    last_message TEXT,
    bot_paused BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tarasi_support_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID REFERENCES tarasi_support_chats(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL, -- user, admin, system
    sender_name TEXT,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tarasi_admin_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_type TEXT NOT NULL, -- support_handoff, system_alert
    title TEXT NOT NULL,
    message TEXT,
    link_url TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_support_chats_session ON tarasi_support_chats(session_id);
CREATE INDEX IF NOT EXISTS idx_support_messages_chat ON tarasi_support_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_admin_notifications_unread ON tarasi_admin_notifications(is_read) WHERE is_read = FALSE;
