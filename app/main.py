from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingestion import router as ingestion_router
from app.api.protocols import router as protocols_router
from app.api.rules import router as rules_router
from app.api.sse import router as sse_router
from app.api.tasks import router as tasks_router
from app.api.routes import router as testing_router
from app.config import settings
from app.memory.factory import init_app_storage, shutdown_app_storage
from app.mock_api.router import router as mock_api_router

try:
    from fastapi_mcp import FastApiMCP
except ImportError:  # pragma: no cover - optional dependency
    FastApiMCP = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_app_storage(app)
    try:
        yield
    finally:
        await shutdown_app_storage(app)


def create_app() -> FastAPI:
    app = FastAPI(title="InvariantFlow", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(mock_api_router)
    app.include_router(testing_router)
    app.include_router(ingestion_router)
    app.include_router(rules_router)
    app.include_router(sse_router)
    app.include_router(tasks_router)
    app.include_router(protocols_router)

    if FastApiMCP is not None:
        try:
            mcp = FastApiMCP(app, name="InvariantFlow MCP")
            if hasattr(mcp, "mount_http"):
                mcp.mount_http()
            else:  # pragma: no cover - older fastapi-mcp
                mcp.mount()
        except Exception:  # pragma: no cover - optional dependency runtime issue
            logger.exception("fastapi-mcp mount failed")
    return app


app = create_app()
