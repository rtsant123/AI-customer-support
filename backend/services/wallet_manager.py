"""Wallet management — balance checks, deductions, and credits with atomic DB ops."""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Client, WalletTransaction

logger = logging.getLogger(__name__)


async def get_balance(db: AsyncSession, client_id) -> int:
    """Return the current balance in paise for the given client."""
    result = await db.execute(select(Client.wallet_balance).where(Client.id == client_id))
    return result.scalar_one_or_none() or 0


async def has_sufficient_balance(db: AsyncSession, client_id, min_paise: int = 2400) -> bool:
    """Check whether the client can afford at least the given number of paise (default 2 min)."""
    return await get_balance(db, client_id) >= min_paise


async def deduct(
    db: AsyncSession,
    client_id,
    amount_paise: int,
    description: str,
    call_id=None,
) -> bool:
    """
    Atomically deduct amount from client wallet.

    Checks current balance first; if insufficient returns False without modifying DB.
    On success inserts a wallet_transaction record and updates the client balance.

    Returns:
        True if deduction succeeded, False if insufficient balance.
    """
    current = await get_balance(db, client_id)
    if current < amount_paise:
        logger.warning(
            "Insufficient balance for client %s: has %d paise, needs %d paise",
            client_id,
            current,
            amount_paise,
        )
        return False

    await db.execute(
        update(Client)
        .where(Client.id == client_id)
        .values(wallet_balance=Client.wallet_balance - amount_paise)
    )
    tx = WalletTransaction(
        client_id=client_id,
        amount=-amount_paise,
        type="deduction",
        description=description,
        call_id=call_id,
    )
    db.add(tx)
    await db.commit()

    logger.info(
        "Deducted %d paise from client %s (call_id=%s). New balance: %d",
        amount_paise,
        client_id,
        call_id,
        current - amount_paise,
    )
    return True


async def credit(
    db: AsyncSession,
    client_id,
    amount_paise: int,
    razorpay_payment_id: str,
    description: str,
) -> None:
    """
    Credit the client wallet and record the transaction.

    Args:
        db: Async database session.
        client_id: The client's UUID.
        amount_paise: Amount in paise to add.
        razorpay_payment_id: Razorpay payment reference for the transaction record.
        description: Human-readable description for the transaction history.
    """
    await db.execute(
        update(Client)
        .where(Client.id == client_id)
        .values(wallet_balance=Client.wallet_balance + amount_paise)
    )
    tx = WalletTransaction(
        client_id=client_id,
        amount=amount_paise,
        type="topup",
        description=description,
        razorpay_payment_id=razorpay_payment_id,
    )
    db.add(tx)
    await db.commit()

    logger.info(
        "Credited %d paise to client %s (payment=%s)",
        amount_paise,
        client_id,
        razorpay_payment_id,
    )
