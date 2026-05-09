-- Enable RLS on all tables
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE blacklist ENABLE ROW LEVEL SECURITY;

-- clients: users see only themselves
CREATE POLICY "clients_self" ON clients FOR ALL USING (auth.uid() = id);

-- campaigns: users see only their campaigns
CREATE POLICY "campaigns_owner" ON campaigns FOR ALL USING (auth.uid() = client_id);

-- phone_numbers: users see only their numbers
CREATE POLICY "phone_numbers_owner" ON phone_numbers FOR ALL USING (auth.uid() = client_id);

-- calls: users see only their calls
CREATE POLICY "calls_owner" ON calls FOR ALL USING (auth.uid() = client_id);

-- wallet_transactions: users see only theirs
CREATE POLICY "wallet_transactions_owner" ON wallet_transactions FOR ALL USING (auth.uid() = client_id);

-- blacklist: users see only theirs
CREATE POLICY "blacklist_owner" ON blacklist FOR ALL USING (auth.uid() = client_id);

-- dnd_numbers: readable by all authenticated, writable by service role only
CREATE POLICY "dnd_read" ON dnd_numbers FOR SELECT USING (auth.role() = 'authenticated');
