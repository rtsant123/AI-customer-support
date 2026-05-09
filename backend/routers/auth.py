"""Authentication routes: signup, login, and current-user dependency."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from database import supabase_admin, supabase_anon
from models.schemas import AuthResponse, LoginRequest, SignupRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Dependency: resolve the current authenticated client
# ---------------------------------------------------------------------------

async def get_current_user(authorization: str = Header(...)) -> dict:
    """
    Validate the Supabase JWT from the Authorization header.

    Expects: Authorization: Bearer <access_token>

    Returns:
        The client record from the clients table.

    Raises:
        HTTPException 401 if the token is missing, invalid, or the client record
        cannot be found.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )

    try:
        user_response = supabase_admin.auth.get_user(token)
        auth_user = user_response.user
        if auth_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
    except Exception as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    client_response = (
        supabase_admin.table("clients")
        .select("*")
        .eq("user_id", auth_user.id)
        .single()
        .execute()
    )
    if not client_response.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client account not found",
        )

    return client_response.data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest) -> JSONResponse:
    """Create a new Supabase Auth user and a corresponding client record."""
    try:
        auth_response = supabase_admin.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,
            }
        )
    except Exception as exc:
        logger.error("Supabase auth signup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signup failed: {exc}",
        ) from exc

    auth_user = auth_response.user
    if auth_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User creation returned no user object",
        )

    client_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    supabase_admin.table("clients").insert(
        {
            "id": client_id,
            "user_id": auth_user.id,
            "email": body.email,
            "company_name": body.company_name,
            "balance_paise": 0,
            "created_at": now,
        }
    ).execute()

    # Sign in to get a JWT for the response
    sign_in = supabase_anon.auth.sign_in_with_password(
        {"email": body.email, "password": body.password}
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "access_token": sign_in.session.access_token,
            "user_id": client_id,
            "email": body.email,
            "company_name": body.company_name,
        },
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> JSONResponse:
    """Authenticate with Supabase and return a JWT."""
    try:
        sign_in = supabase_anon.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        logger.warning("Login failed for %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc

    if sign_in.session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    auth_user = sign_in.user
    client_response = (
        supabase_admin.table("clients")
        .select("id, company_name")
        .eq("user_id", auth_user.id)
        .single()
        .execute()
    )
    if not client_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client record not found",
        )

    client = client_response.data

    return JSONResponse(
        content={
            "access_token": sign_in.session.access_token,
            "user_id": client["id"],
            "email": auth_user.email,
            "company_name": client["company_name"],
        }
    )


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> JSONResponse:
    """Return the current authenticated client's profile."""
    return JSONResponse(
        content={
            "id": current_user["id"],
            "email": current_user["email"],
            "company_name": current_user["company_name"],
            "balance_paise": current_user.get("balance_paise", 0),
            "created_at": str(current_user.get("created_at", "")),
        }
    )
