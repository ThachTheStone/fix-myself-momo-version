from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agent.loop import execute_approved_tool
from app.api.chat import _extract_bearer_token, _extract_user_id_from_jwt
from app.policy.pending import PendingActionError, prepare_approval, reject_pending_action
from app.tools.be_client import BEError
from app.tools.registry import ToolContext

router = APIRouter(prefix="/ai/actions", tags=["actions"])
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class ApproveRequest(BaseModel):
    """Thân request POST /ai/actions/{id}/approve (QĐ-HARNESS-005)."""

    editedArgs: dict[str, Any] | None = None


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: str,
    request: Request,
    body: ApproveRequest | None = None,
    authorization: str | None = Header(default=None),
) -> EventSourceResponse:
    """Duyệt một pending_action còn hạn và thực thi qua vòng lặp agent ([INV-HARNESS-01])."""
    jwt = _extract_bearer_token(authorization)
    user_id = _extract_user_id_from_jwt(jwt)
    state = request.app.state
    now = getattr(state, "clock_now", None)
    current_now = now() if callable(now) else datetime.now(VN_TZ)

    try:
        record, validated_args = await prepare_approval(
            store=state.store,
            registry=state.registry,
            action_id=action_id,
            user_id=user_id,
            edited_args=body.editedArgs if body else None,
            now=current_now,
        )
    except PendingActionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    ctx = ToolContext(
        user_id=user_id,
        jwt=jwt,
        turn_id=record.turn_id,
        be=state.be_client,
        last_write_turn_id=state.store.get_last_write_turn_id(user_id, record.turn_id),
    )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            events = await execute_approved_tool(
                registry=state.registry,
                tool_name=record.tool,
                validated_args=validated_args,
                ctx=ctx,
            )
            for ev in events:
                yield {"event": ev.event, "data": json.dumps(ev.data, ensure_ascii=False)}
        except BEError as exc:
            err = {"code": exc.code, "message": exc.message}
            yield {"event": "error", "data": json.dumps(err, ensure_ascii=False)}
        done_payload = {
            "turnId": record.turn_id,
            "model": state.router.last_target,
            "toolCalls": 1,
        }
        yield {"event": "done", "data": json.dumps(done_payload, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/{action_id}/reject", status_code=204)
async def reject_action(
    action_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    """Từ chối một pending_action và trả về 204 No Content (QĐ-HARNESS-005)."""
    jwt = _extract_bearer_token(authorization)
    user_id = _extract_user_id_from_jwt(jwt)
    state = request.app.state
    now = getattr(state, "clock_now", None)
    current_now = now() if callable(now) else datetime.now(VN_TZ)

    try:
        await reject_pending_action(
            store=state.store,
            action_id=action_id,
            user_id=user_id,
            now=current_now,
        )
    except PendingActionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return Response(status_code=204)
