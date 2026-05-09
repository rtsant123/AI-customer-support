"""Wallet management — balance checks, deductions, and credits with atomic DB ops."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from database import supabase_admin

logger = logging.getLogger(__name__)


async def get_balance(client_id: str) -> int:
    """Return the current balance in paise for the given client."""
    response = (
        supabase_admin.table("clients")
        .select("balance_paise")
        .eq("id", client_id)
        .single()
        .execute()
    )
    if not response.data:
        raise ValueError(f"Client {client_id} not found")
    return int(response.data["balance_paise"])


async def has_sufficient_balance(client_id: str, min_paise: int = 2400) -> bool:
    """Check whether the client can afford at least the given number of paise (default 2 min)."""
    try:
        balance = await get_balance(client_id)
        return balance >= min_paise
    except ValueError:
        return False


async def deduct(
    client_id: str,
    amount_paise: int,
    description: str,
    call_id: str | None = None,
) -> bool:
    """
    Atomically deduct amount from client wallet.

    Checks current balance first; if insufficient returns False without modifying DB.
    On success inserts a wallet_transaction record and updates the client balance.

    Returns:
        True if deduction succeeded, False if insufficient balance.
    """
    try:
        current_balance = await get_balance(client_id)
    except ValueError:
        logger.error("Cannot deduct — client %s not found", client_id)
        return False

    if current_balance < amount_paise:
        logger.warning(
            "Insufficient balance for client %s: has %d paise, needs %d paise",
            client_id,
            current_balance,
            amount_paise,
        )
        return False

    new_balance = current_balance - amount_paise

    # Update balance
    supabase_admin.table("clients").update({"balance_paise": new_balance}).eq(
        "id", client_id
    ).execute()

    # Record transaction
    transaction: dict = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "amount_paise": -amount_paise,
        "type": "debit",
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if call_id:
        transaction["call_id"] = call_id

    supabase_admin.table("wallet_transactions").insert(transaction).execute()

    logger.info(
        "Deducted %d paise from client %s (call_id=%s). New balance: %d",
        amount_paise,
        client_id,
        call_id,
        new_balance,
    )
    return True


async def credit(
    client_id: str,
    amount_paise: int,
    razorpay_payment_id: str,
    description: str,
) -> None:
    """
    Credit the client wallet and record the transaction.

    Args:
        client_id: The client's UUID.
        amount_paise: Amount in paise to add.
        razorpay_payment_id: Razorpay payment reference for the transaction record.
        description: Human-readable description for the transaction history.
    """
    current_balance = await get_balance(client_id)
    new_balance = current_balance + amount_paise

    supabase_admin.table("clients").update({"balance_paise": new_balance}).eq(
        "id", client_id
    ).execute()

    transaction: dict = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "amount_paise": amount_paise,
        "type": "credit",
        "description": description,
        "razorpay_payment_id": razorpay_payment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase_admin.table("wallet_transactions").insert(transaction).execute()

    logger.info(
        "Credited %d paise to client %s (payment=%s). New balance: %d",
        amount_paise,
        client_id,
        razorpay_payment_id,
        new_balance,
    )
