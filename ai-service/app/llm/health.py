from __future__ import annotations

import httpx

from app.config import Settings
from app.llm.router import SmallHealthState


async def check_endpoints(
    http_client: httpx.AsyncClient,
    settings: Settings,
    small_health: SmallHealthState,
) -> dict[str, str]:
    """Kiểm tra nhanh trạng thái endpoint small và cấu hình cloud."""
    if settings.router_mode == "cloud_only":
        small_status = "off"
    else:
        ok = await small_health.probe(http_client, settings.small_model_base_url)
        small_status = "up" if ok and not small_health.small_down else "down"

    if settings.router_mode == "small_only":
        cloud_status = "off"
    elif settings.cloud_model and settings.cloud_api_key:
        cloud_status = "up"
    else:
        cloud_status = "down"

    return {
        "status": "ok",
        "small": small_status,
        "cloud": cloud_status,
    }
