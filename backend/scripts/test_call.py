"""
Quick test: sign up, create a campaign, and trigger one call to a phone number.

Usage:
    cd backend
    python scripts/test_call.py +919XXXXXXXXXX
"""

import asyncio
import sys
import httpx

BASE = "http://localhost:8000/api"

TEST_EMAIL = "test@aicaller.dev"
TEST_PASSWORD = "testpass123"
TEST_COMPANY = "Test Company"


async def main(phone_number: str):
    async with httpx.AsyncClient(timeout=30) as client:

        # 1. Sign up (ignore error if already exists)
        r = await client.post(f"{BASE}/auth/signup", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "company_name": TEST_COMPANY,
        })
        if r.status_code == 201:
            token = r.json()["access_token"]
            print(f"✓ Signed up as {TEST_EMAIL}")
        else:
            # Login instead
            r = await client.post(f"{BASE}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
            })
            r.raise_for_status()
            token = r.json()["access_token"]
            print(f"✓ Logged in as {TEST_EMAIL}")

        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create campaign
        r = await client.post(f"{BASE}/campaigns", headers=headers, json={
            "name": "Test Call Campaign",
            "language": "hindi",
            "agent_name": "Priya",
            "agent_gender": "female",
            "agent_tone": "friendly",
            "company_name": TEST_COMPANY,
            "product_name": "AI Calling Platform",
            "product_price": "₹999/month",
            "key_benefits": ["Save time", "Qualify leads faster", "Works 24/7"],
            "goal": "qualify",
            "transfer_condition": "if customer wants to speak to a human",
            "calling_schedule_start": "09:00",
            "calling_schedule_end": "21:00",
            "calling_days": ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"],
        })
        r.raise_for_status()
        campaign = r.json()["campaign"]
        campaign_id = campaign["id"]
        print(f"✓ Created campaign: {campaign_id}")

        # 3. Upload the test phone number
        r = await client.post(
            f"{BASE}/campaigns/{campaign_id}/numbers",
            headers=headers,
            json={"numbers": [phone_number]},
        )
        r.raise_for_status()
        result = r.json()
        print(f"✓ Uploaded number: {result}")

        if result["added"] == 0:
            print("✗ Number was blocked (DND) or invalid. Try a different number.")
            return

        # 4. Launch the campaign — this enqueues the call
        r = await client.post(f"{BASE}/campaigns/{campaign_id}/launch", headers=headers)
        r.raise_for_status()
        print(f"✓ Campaign launched: {r.json()}")
        print()
        print(f"📞 Calling {phone_number} now...")
        print("   Watch your FastAPI logs for the AI conversation pipeline.")
        print("   The call uses Twilio trial — make sure the number is verified in Twilio console.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_call.py +919XXXXXXXXXX")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
