-- Tarasi Bot Admin Knowledge Items

CREATE TABLE IF NOT EXISTS tarasi_bot_knowledge_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    category TEXT, -- routes, hotels, restaurants, support, pricing, tourism, safety, business_rules
    keywords TEXT[],
    content TEXT NOT NULL,
    priority INT DEFAULT 5,
    is_active BOOLEAN DEFAULT TRUE,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for searching keywords and categories
CREATE INDEX IF NOT EXISTS idx_bot_knowledge_category ON tarasi_bot_knowledge_items(category);
CREATE INDEX IF NOT EXISTS idx_bot_knowledge_active ON tarasi_bot_knowledge_items(is_active) WHERE is_active = TRUE;
