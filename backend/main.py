"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis singleton — modules import this directly
# ---------------------------------------------------------------------------

redis_client: aioredis.Redis  # declared here, initialised in lifespan


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Redis on startup and close on shutdown."""
    global redis_client

    logger.info("Connecting to Redis at %s …", settings.redis_url)
    redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )
    try:
        await redis_client.ping()
        logger.info("Redis connection established.")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)
        raise

    yield

    logger.info("Closing Redis connection …")
    await redis_client.aclose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Calling SaaS API",
    description="Backend for the AI-powered outbound calling platform (Indian market).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal server error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check() -> dict[str, Any]:
    """Return service health status including Redis connectivity."""
    redis_ok = False
    try:
        await redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Routers — imported after app is defined to avoid circular deps
# ---------------------------------------------------------------------------

from routers.auth import router as auth_router  # noqa: E402
from routers.campaigns import router as campaigns_router  # noqa: E402
from routers.calls import router as calls_router  # noqa: E402
from routers.wallet import router as wallet_router  # noqa: E402
from routers.webhook import router as webhook_router  # noqa: E402

app.include_router(auth_router, prefix="/api")
app.include_router(campaigns_router, prefix="/api")
app.include_router(calls_router, prefix="/api")
app.include_router(wallet_router, prefix="/api")
app.include_router(webhook_router, prefix="/api")
