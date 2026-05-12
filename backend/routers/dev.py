"""Dev-only route: trigger a test call directly from the browser."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import Client, Campaign, PhoneNumber
from routers.auth import hash_password, create_access_token
from services.prompt_builder import build_system_prompt
from services.call_manager import initiate_call
from services.dnd_filter import filter_dnd_numbers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])

_TEST_EMAIL = "dev@aicaller.test"
_TEST_PASSWORD = "devpass123"
_TEST_COMPANY = "Dev Test"


@router.get("", response_class=HTMLResponse)
async def dev_home():
    """Simple browser UI to trigger a test call."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
  <title>AI Caller — Test Call</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: 80px auto; padding: 0 20px; }
    h2 { color: #4f46e5; }
    input { width: 100%; padding: 12px; font-size: 16px; border: 1px solid #d1d5db; border-radius: 8px; box-sizing: border-box; margin-bottom: 12px; }
    button { width: 100%; padding: 14px; background: #4f46e5; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; }
    button:hover { background: #4338ca; }
    #result { margin-top: 20px; padding: 14px; border-radius: 8px; display: none; }
    .ok { background: #d1fae5; color: #065f46; }
    .err { background: #fee2e2; color: #991b1b; }
  </style>
</head>
<body>
  <h2>📞 AI Caller Test</h2>
  <p>Enter your verified Twilio number to receive a test call in Hindi.</p>
  <input id="phone" type="tel" placeholder="+91XXXXXXXXXX" />
  <button onclick="makeCall()">Call Now</button>
  <div id="result"></div>
  <script>
    async function makeCall() {
      const phone = document.getElementById('phone').value.trim();
      const res = document.getElementById('result');
      res.style.display = 'none';
      if (!phone) { alert('Enter a phone number'); return; }
      const r = await fetch('/api/dev/call?to=' + encodeURIComponent(phone));
      const data = await r.json();
      res.style.display = 'block';
      if (r.ok) {
        res.className = 'ok';
        res.innerHTML = '✅ Call initiated! Your phone should ring in a few seconds.<br><small>Call SID: ' + data.call_sid + '</small>';
      } else {
        res.className = 'err';
        res.innerHTML = '❌ ' + (data.detail || JSON.stringify(data));
      }
    }
  </script>
</body>
</html>
""")


@router.get("/call")
async def trigger_test_call(
    to: str = Query(..., description="Phone number to call, e.g. +91XXXXXXXXXX"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a test account + campaign and immediately call the given number."""

    if not settings.dev_mode:
        return JSONResponse(status_code=403, content={"detail": "Only available in DEV_MODE=true"})

    # Get or create dev client
    result = await db.execute(select(Client).where(Client.email == _TEST_EMAIL))
    client = result.scalar_one_or_none()

    if not client:
        client = Client(
            email=_TEST_EMAIL,
            password_hash=hash_password(_TEST_PASSWORD),
            company_name=_TEST_COMPANY,
            wallet_balance=100000,  # ₹1000 test balance
        )
        db.add(client)
        await db.commit()
        await db.refresh(client)
        logger.info("Created dev test client: %s", client.id)

    # Create a fresh test campaign
    campaign_data = {
        "name": "Dev Test Campaign",
        "language": "hindi",
        "agent_name": "Priya",
        "agent_gender": "female",
        "agent_tone": "friendly",
        "company_name": _TEST_COMPANY,
        "product_name": "AI Calling Platform",
        "product_price": "₹999/month",
        "key_benefits": ["Saves time", "Qualifies leads 24/7", "Works in Hindi"],
        "goal": "qualify",
        "transfer_condition": "if customer wants to speak to a human",
    }
    campaign = Campaign(
        client_id=client.id,
        calling_schedule_start="09:00",
        calling_schedule_end="21:00",
        calling_days=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"],
        system_prompt=build_system_prompt(campaign_data),
        **{k: v for k, v in campaign_data.items() if k != "key_benefits"},
        key_benefits=campaign_data["key_benefits"],
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    # Check DND
    clean, blocked = await filter_dnd_numbers(db, [to], client.id)
    if not clean:
        return JSONResponse(status_code=400, content={"detail": f"{to} is on the DND/blacklist"})

    # Create phone number record
    pn = PhoneNumber(
        campaign_id=campaign.id,
        client_id=client.id,
        number=to,
    )
    db.add(pn)
    await db.commit()
    await db.refresh(pn)

    # Fire the call
    try:
        call_sid = await initiate_call(
            db=db,
            phone_number=to,
            campaign_id=str(campaign.id),
            phone_number_id=str(pn.id),
            client_id=client.id,
        )
    except Exception as exc:
        logger.error("Test call failed to %s: %s", to, exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    logger.info("Dev test call initiated to %s, SID=%s", to, call_sid)
    return JSONResponse(content={
        "ok": True,
        "call_sid": call_sid,
        "to": to,
        "campaign_id": str(campaign.id),
    })
