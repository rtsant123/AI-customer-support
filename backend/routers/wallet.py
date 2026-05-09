"""Wallet balance, transaction history, and Razorpay top-up routes."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import Client, WalletTransaction
from models.schemas import TopupRequest
from routers.auth import get_current_user
from services import wallet_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])

_razorpay_client = razorpay.Client(
    auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
)


@router.get("/balance")
async def get_balance(
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return current wallet balance in paise and INR."""
    balance_paise = await wallet_manager.get_balance(db, current_user.id)
    return JSONResponse(
        content={
            "balance_paise": balance_paise,
            "balance_inr": round(balance_paise / 100, 2),
        }
    )


@router.get("/transactions")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return paginated wallet transaction history for the current client."""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(WalletTransaction)
        .where(WalletTransaction.client_id == current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    transactions = result.scalars().all()

    tx_list = [
        {
            "id": str(tx.id),
            "client_id": str(tx.client_id),
            "amount": tx.amount,
            "type": tx.type,
            "description": tx.description,
            "razorpay_payment_id": tx.razorpay_payment_id,
            "call_id": str(tx.call_id) if tx.call_id else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in transactions
    ]

    return JSONResponse(
        content={
            "transactions": tx_list,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/topup/create-order")
async def create_topup_order(
    body: TopupRequest,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Create a Razorpay order for wallet top-up.

    Returns the order details needed by the frontend to launch the Razorpay checkout.
    """
    amount_paise = body.amount_paise
    # Razorpay amount is in paise for INR
    try:
        order = _razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"topup_{current_user.id}_{uuid.uuid4().hex[:8]}",
                "notes": {
                    "client_id": str(current_user.id),
                    "purpose": "wallet_topup",
                },
            }
        )
    except Exception as exc:
        logger.error("Razorpay order creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create payment order. Please try again.",
        ) from exc

    return JSONResponse(
        content={
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": settings.razorpay_key_id,
        }
    )


@router.post("/topup/verify")
async def verify_topup(
    body: dict,
    current_user: Client = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Verify Razorpay payment signature and credit the wallet on success.

    Expected body:
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    """
    order_id: str = body.get("razorpay_order_id", "")
    payment_id: str = body.get("razorpay_payment_id", "")
    signature: str = body.get("razorpay_signature", "")

    if not all([order_id, payment_id, signature]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="razorpay_order_id, razorpay_payment_id, and razorpay_signature are required",
        )

    # Verify HMAC-SHA256 signature
    message = f"{order_id}|{payment_id}"
    expected_sig = hmac.new(
        key=settings.razorpay_key_secret.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        logger.warning(
            "Invalid Razorpay signature for client %s, order %s", current_user.id, order_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature",
        )

    # Fetch the order to get the amount
    try:
        order = _razorpay_client.order.fetch(order_id)
        amount_paise: int = int(order["amount"])
    except Exception as exc:
        logger.error("Failed to fetch Razorpay order %s: %s", order_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch order details",
        ) from exc

    await wallet_manager.credit(
        db=db,
        client_id=current_user.id,
        amount_paise=amount_paise,
        razorpay_payment_id=payment_id,
        description=f"Wallet top-up via Razorpay (order: {order_id})",
    )

    new_balance = await wallet_manager.get_balance(db, current_user.id)
    logger.info(
        "Wallet credited: client=%s, amount=%d paise, payment=%s",
        current_user.id,
        amount_paise,
        payment_id,
    )

    return JSONResponse(
        content={
            "success": True,
            "amount_paise": amount_paise,
            "new_balance_paise": new_balance,
            "new_balance_inr": round(new_balance / 100, 2),
        }
    )
