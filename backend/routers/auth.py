from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import Client
from models.schemas import LoginRequest, SignupRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": expire},
        settings.secret_key,
        algorithm=_ALGORITHM,
    )


async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Client:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        user_id: str = payload.get("sub", "")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    result = await db.execute(select(Client).where(Client.id == uuid.UUID(user_id)))
    client = result.scalar_one_or_none()
    if not client or not client.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return client


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    existing = await db.execute(select(Client).where(Client.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    client = Client(
        email=body.email,
        password_hash=hash_password(body.password),
        company_name=body.company_name,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)

    token = create_access_token(str(client.id), client.email)
    return JSONResponse(
        status_code=201,
        content={
            "access_token": token,
            "user_id": str(client.id),
            "email": client.email,
            "company_name": client.company_name,
        },
    )


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await db.execute(select(Client).where(Client.email == body.email))
    client = result.scalar_one_or_none()
    if not client or not verify_password(body.password, client.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not client.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    token = create_access_token(str(client.id), client.email)
    return JSONResponse(content={
        "access_token": token,
        "user_id": str(client.id),
        "email": client.email,
        "company_name": client.company_name,
    })


@router.get("/me")
async def get_me(current_user: Client = Depends(get_current_user)) -> JSONResponse:
    return JSONResponse(content={
        "id": str(current_user.id),
        "email": current_user.email,
        "company_name": current_user.company_name,
        "wallet_balance": current_user.wallet_balance,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at.isoformat(),
    })
