# AI Calling SaaS Platform

An AI-powered outbound calling platform that enables businesses to run automated voice campaigns at scale. Clients create campaigns, upload phone number lists, and an AI agent (powered by a large language model) conducts real conversations in multiple languages (Hindi, English, Bangla, Tamil). Each call is transcribed, summarized, and billed per minute from the client's prepaid wallet. The platform integrates with Exotel for telephony, Razorpay for payments, and is built on a FastAPI backend with a Next.js frontend backed by Supabase (Postgres + Auth).

---

## Quick Start

### Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in your values
uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local      # fill in your values
npm run dev                     # visit http://localhost:3000
```

---

## Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (bypasses RLS) |
| `SUPABASE_JWT_SECRET` | JWT secret from Supabase dashboard |
| `OPENAI_API_KEY` | OpenAI API key for the AI agent |
| `EXOTEL_SID` | Exotel account SID |
| `EXOTEL_TOKEN` | Exotel API token |
| `EXOTEL_API_KEY` | Exotel API key |
| `EXOTEL_API_SECRET` | Exotel API secret |
| `EXOTEL_FROM_NUMBER` | Exotel caller ID / ExoPhone |
| `RAZORPAY_KEY_ID` | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay key secret |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook signing secret |
| `BASE_URL` | Publicly accessible backend URL (for webhooks) |
| `COST_PER_MINUTE_PAISE` | Call cost in paise per minute (e.g. 100 = ₹1/min) |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `NEXT_PUBLIC_API_URL` | Backend API base URL |

---

## Database Setup

1. Create a new project at [supabase.com](https://supabase.com).
2. In the Supabase dashboard, open the **SQL Editor**.
3. Run the migrations in order:

```bash
# Using Supabase CLI (recommended)
supabase login
supabase link --project-ref <your-project-ref>
supabase db push

# Or manually paste each file into the SQL Editor:
# 1. supabase/migrations/001_initial_schema.sql
# 2. supabase/migrations/002_rls_policies.sql
```

4. Enable **Row Level Security** is handled by migration `002`. Verify in the Supabase dashboard under Authentication > Policies.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                           │
│                  Next.js Frontend (Vercel)                      │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST / Supabase Realtime
          ┌──────────────┴──────────────┐
          │                             │
          ▼                             ▼
┌─────────────────┐          ┌──────────────────────┐
│  FastAPI Backend│          │  Supabase (Postgres)  │
│  (Railway)      │◄────────►│  + Auth + Storage     │
└────────┬────────┘          └──────────────────────┘
         │
    ┌────┴──────────────────────────┐
    │                               │
    ▼                               ▼
┌──────────┐                ┌──────────────┐
│  Exotel  │                │   Razorpay   │
│ (Calls)  │                │  (Payments)  │
└──────────┘                └──────────────┘
    │
    ▼
┌──────────────┐
│  OpenAI API  │
│ (AI Agent /  │
│  Whisper STT)│
└──────────────┘

Call Flow:
  Backend scheduler → Exotel outbound call → Customer answers
  → Exotel streams audio → Backend WebSocket → OpenAI STT
  → LLM generates reply → TTS → Exotel plays audio → repeat
  → Call ends → transcript saved → wallet deducted
```

---

## Phase 1 Checklist

- [ ] Supabase project created and migrations applied
- [ ] Backend environment variables configured
- [ ] Frontend environment variables configured
- [ ] Exotel account set up with a caller ID (ExoPhone)
- [ ] Razorpay account set up with webhook configured to `POST /api/payments/webhook`
- [ ] Backend deployed to Railway
- [ ] Frontend deployed to Vercel
- [ ] Admin user created (set `is_admin = true` in `clients` table)
- [ ] End-to-end test call placed from dashboard
- [ ] DND number list imported into `dnd_numbers` table
