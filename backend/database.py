from supabase import create_client, Client
from config import settings

supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_key,
)

supabase_anon: Client = create_client(
    settings.supabase_url,
    settings.supabase_anon_key,
)
