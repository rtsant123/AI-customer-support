-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- clients table (extends Supabase auth.users)
CREATE TABLE clients (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    wallet_balance BIGINT NOT NULL DEFAULT 0,  -- stored in paise
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- wallet_transactions
CREATE TABLE wallet_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL,  -- positive=credit, negative=debit, in paise
    type TEXT NOT NULL CHECK (type IN ('topup','deduction','refund')),
    description TEXT,
    razorpay_payment_id TEXT,
    call_id UUID,  -- FK added after calls table
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- campaigns
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','completed','deleted')),
    language TEXT NOT NULL CHECK (language IN ('hindi','english','bangla','tamil')),
    agent_name TEXT NOT NULL,
    agent_gender TEXT NOT NULL CHECK (agent_gender IN ('male','female')),
    agent_tone TEXT NOT NULL CHECK (agent_tone IN ('friendly','professional','urgent')),
    company_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    product_price TEXT NOT NULL,
    key_benefits TEXT[] NOT NULL DEFAULT '{}',
    goal TEXT NOT NULL CHECK (goal IN ('qualify','book_appointment','reminder','survey')),
    transfer_condition TEXT,
    system_prompt TEXT NOT NULL,
    calling_schedule_start TEXT NOT NULL DEFAULT '09:00',
    calling_schedule_end TEXT NOT NULL DEFAULT '20:00',
    calling_days TEXT[] NOT NULL DEFAULT '{monday,tuesday,wednesday,thursday,friday,saturday}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- phone_numbers
CREATE TABLE phone_numbers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','calling','called','interested','not_interested','callback','wrong_number','dnd','failed','language_barrier')),
    callback_datetime TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(campaign_id, number)
);

-- calls
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    phone_number_id UUID NOT NULL REFERENCES phone_numbers(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    exotel_call_sid TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'initiated' CHECK (status IN ('initiated','ringing','connected','completed','failed','no_answer','busy')),
    duration_seconds INTEGER DEFAULT 0,
    cost_paise BIGINT DEFAULT 0,
    recording_url TEXT,
    transcript JSONB DEFAULT '[]',  -- array of {role, content, timestamp}
    ai_summary TEXT,
    lead_status TEXT CHECK (lead_status IN ('interested','not_interested','callback','wrong_number','language_barrier')),
    follow_up_date TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add FK from wallet_transactions to calls
ALTER TABLE wallet_transactions ADD CONSTRAINT fk_call FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE SET NULL;

-- blacklist (per client)
CREATE TABLE blacklist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, phone_number)
);

-- dnd_numbers (global TRAI DND registry)
CREATE TABLE dnd_numbers (
    phone_number TEXT PRIMARY KEY,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_phone_numbers_campaign_id ON phone_numbers(campaign_id);
CREATE INDEX idx_phone_numbers_status ON phone_numbers(campaign_id, status);
CREATE INDEX idx_calls_client_id ON calls(client_id);
CREATE INDEX idx_calls_campaign_id ON calls(campaign_id);
CREATE INDEX idx_calls_exotel_sid ON calls(exotel_call_sid);
CREATE INDEX idx_wallet_transactions_client_id ON wallet_transactions(client_id);
CREATE INDEX idx_campaigns_client_id ON campaigns(client_id);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER campaigns_updated_at BEFORE UPDATE ON campaigns
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
