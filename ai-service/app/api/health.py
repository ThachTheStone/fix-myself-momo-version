from __future__ import annotations

from fastapi import APIRouter, Request

from app.llm.health import check_endpoints

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Kiểm tra trạng thái service, model nhỏ và cloud."""
    state = request.app.state
    return await check_endpoints(state.http_client, state.settings, state.router.health)
