from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.llm.router import LLMClientProtocol, ModelRouter
from app.store.memory import InMemoryStore
from app.tools.be_client import BEClient
from app.tools.server_tools import build_p0_registry


def create_app(
    *,
    settings: Settings | None = None,
    llm_client: LLMClientProtocol | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    """Khởi tạo FastAPI app cho AI service (QĐ-HARNESS-002)."""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_client = http_client is None
        client = http_client or httpx.AsyncClient()
        app.state.settings = resolved_settings
        app.state.http_client = client
        app.state.store = InMemoryStore()
        app.state.registry = build_p0_registry()
        app.state.router = ModelRouter(resolved_settings, client=llm_client)
        app.state.be_client = BEClient(
            client,
            base_url=resolved_settings.be_base_url,
            timeout_s=resolved_settings.be_timeout_s,
        )
        try:
            yield
        finally:
            if owns_client:
                await client.aclose()

    app = FastAPI(title="Fix Myself AI Service", version="0.1.0", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(health_router)
    return app


app = create_app()
