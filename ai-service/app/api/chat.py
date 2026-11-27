from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent.loop import SSEEvent, handle_turn

router = APIRouter(prefix="/ai", tags=["ai"])
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class ChatRequest(BaseModel):
    """Thân request POST /ai/chat."""

    message: str = Field(min_length=1)
    conversationId: str | None = None
    inputMode: Literal["text", "voice"] = "text"


def _extract_bearer_token(authorization: str | None) -> str:
    """Kiểm tra header Authorization: Bearer <JWT>; thiếu hoặc sai định dạng trả 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai Authorization Bearer JWT")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="JWT rỗng")
    return token


def _extract_user_id_from_jwt(jwt: str) -> str:
    """Trích user_id từ claim sub của JWT (không log JWT)."""
    parts = jwt.split(".")
    if len(parts) == 3:
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
            if isinstance(claims, dict) and claims.get("sub"):
                return str(claims["sub"])
        except Exception:
            pass
    digest = hashlib.sha256(jwt.encode("utf-8")).hexdigest()[:16]
    return f"user-{digest}"


async def _mock_sse_stream() -> AsyncIterator[dict[str, str]]:
    """Phát đủ 6 loại sự kiện SSE mẫu cho FE dựng giao diện (QĐ-HARNESS-010)."""
    now = datetime.now(VN_TZ).replace(microsecond=0)
    turn_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())
    pending_id = str(uuid.uuid4())
    reminder_id = str(uuid.uuid4())

    mock_events = [
        SSEEvent(event="text", data={"delta": "Đã thêm task mẫu và đặt nhắc nhở cho bạn. "}),
        SSEEvent(
            event="tool_done",
            data={
                "turnId": turn_id,
                "tool": "create_task",
                "summary": "Đã tạo task 'Nộp báo cáo' · hạn Th 6 27/11 23:59",
                "actionId": action_id,
                "undoable": True,
            },
        ),
        SSEEvent(
            event="pending_action",
            data={
                "id": pending_id,
                "tool": "delete_task",
                "risk": "high",
                "title": "Xoá 1 task",
                "preview": {
                    "kind": "list",
                    "items": [
                        {"title": "Họp nhóm cũ", "deadline": (now + timedelta(days=1)).isoformat()}
                    ],
                },
                "expiresAt": (now + timedelta(minutes=30)).isoformat(),
            },
        ),
        SSEEvent(
            event="client_action",
            data={
                "type": "schedule_notification",
                "payload": {
                    "reminderId": reminder_id,
                    "at": (now + timedelta(hours=2)).isoformat(),
                    "title": "Nhắc nhở",
                    "body": "Nộp báo cáo trước 23:59",
                },
            },
        ),
        SSEEvent(
            event="error",
            data={"code": "MOCK_SAMPLE_ERROR", "message": "Sự kiện error mẫu để FE kiểm UI."},
        ),
        SSEEvent(event="done", data={"turnId": turn_id, "model": "small", "toolCalls": 2}),
    ]

    for ev in mock_events:
        yield {"event": ev.event, "data": json.dumps(ev.data, ensure_ascii=False)}


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    mock: int = Query(default=0),
    authorization: str | None = Header(default=None),
) -> EventSourceResponse:
    """Stream phản hồi AI bằng Server-Sent Events (QĐ-HARNESS-002, QĐ-HARNESS-010)."""
    jwt = _extract_bearer_token(authorization)
    if mock == 1:
        return EventSourceResponse(_mock_sse_stream())

    user_id = _extract_user_id_from_jwt(jwt)
    conversation_id = body.conversationId or str(uuid.uuid4())
    state = request.app.state

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for ev in handle_turn(
            user_id=user_id,
            jwt=jwt,
            message=body.message,
            conversation_id=conversation_id,
            settings=state.settings,
            store=state.store,
            router=state.router,
            registry=state.registry,
            be=state.be_client,
        ):
            yield {"event": ev.event, "data": json.dumps(ev.data, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
