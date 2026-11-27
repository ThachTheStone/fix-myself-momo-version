from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.agent.context import build_messages, summarize_older_turns
from app.agent.prompt import build_system_prompt
from app.config import Settings
from app.llm.router import ModelRouter, RouterError, TaskKind
from app.policy import permission
from app.policy.pending import build_action_preview
from app.policy.permission import Mode, Source
from app.store.memory import InMemoryStore, PendingActionRecord
from app.tools.be_client import BEClient, BEError, BEResponse
from app.tools.client_tools import build_client_action
from app.tools.registry import Tool, ToolContext, ToolRegistry

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass
class SSEEvent:
    """Sự kiện SSE chuẩn hoá (QĐ-HARNESS-010)."""

    event: str
    data: dict[str, Any]


@dataclass
class ToolExecutionResult:
    """Kết quả sau khi chạy một tool qua run_tool()."""

    for_model: str
    events: list[SSEEvent] = field(default_factory=list)
    schema_error: bool = False
    executed_ok: bool = False
    summary_line: str = ""


def _parse_raw_arguments(raw_args: str | dict[str, Any]) -> dict[str, Any]:
    """Giải mã tham số tool call từ string JSON hoặc dict."""
    if isinstance(raw_args, dict):
        return raw_args
    if not raw_args or not raw_args.strip():
        return {}
    parsed = json.loads(raw_args)
    if not isinstance(parsed, dict):
        raise ValueError("Tham số tool phải là JSON object")
    return parsed


async def _execute_tool_and_build_events(
    tool: Tool,
    validated_args: BaseModel,
    ctx: ToolContext,
) -> tuple[list[SSEEvent], str, BEResponse]:
    """Chạy tool.call và đóng gói SSE tool_done (+ client_action nếu có)."""
    be_res = await tool.call(validated_args, ctx)
    summary = tool.summarize(be_res)
    event_data: dict[str, Any] = {
        "turnId": ctx.turn_id,
        "tool": tool.name,
        "summary": summary,
        "undoable": tool.risk != "read",
    }
    if be_res.action_id is not None:
        event_data["actionId"] = be_res.action_id

    events: list[SSEEvent] = [SSEEvent(event="tool_done", data=event_data)]
    if tool.runs_on == "server_client":
        client_payload = build_client_action(tool.name, be_res.data)
        if client_payload is not None:
            events.append(SSEEvent(event="client_action", data=client_payload))
    return events, summary, be_res


async def execute_approved_tool(
    *,
    registry: ToolRegistry,
    tool_name: str,
    validated_args: BaseModel,
    ctx: ToolContext,
) -> list[SSEEvent]:
    """Thực thi tool đã được người dùng duyệt qua pending_action ([INV-HARNESS-01])."""
    tool = registry.get(tool_name)
    if tool is None:
        return [
            SSEEvent(
                event="error",
                data={"code": "UNKNOWN_TOOL", "message": f"Không tồn tại tool '{tool_name}'"},
            )
        ]
    events, _, _ = await _execute_tool_and_build_events(tool, validated_args, ctx)
    return events


async def run_tool(
    *,
    registry: ToolRegistry,
    store: InMemoryStore,
    settings: Settings,
    tool_name: str,
    raw_args: str | dict[str, Any],
    ctx: ToolContext,
    mode: Mode,
    source: Source,
    now: datetime,
) -> ToolExecutionResult:
    """Đường duy nhất thực thi tool: schema -> permission.check -> BE/pending ([INV-HARNESS-01])."""
    tool = registry.get(tool_name)
    if tool is None:
        return ToolExecutionResult(
            for_model=json.dumps(
                {"error": "UNKNOWN_TOOL", "message": f"Không tồn tại tool '{tool_name}'"},
                ensure_ascii=False,
            ),
            schema_error=True,
        )

    try:
        args_dict = _parse_raw_arguments(raw_args)
        validated_args = tool.args_model.model_validate(args_dict, context={"now": now})
    except (ValueError, ValidationError) as exc:
        return ToolExecutionResult(
            for_model=json.dumps(
                {"error": "TOOL_ARGS_INVALID", "message": str(exc)},
                ensure_ascii=False,
            ),
            schema_error=True,
        )

    decision = permission.check(tool, mode, source)
    if decision == "ask":
        action_uuid = str(uuid.uuid4())
        dumped_args = validated_args.model_dump(mode="json", by_alias=True, exclude_none=True)
        expires_at = now + timedelta(minutes=settings.pending_ttl_min)
        task_snapshot: dict[str, Any] | None = None
        if tool.name == "delete_task" and dumped_args.get("taskId"):
            try:
                snap_res = await ctx.be.get(
                    f"/api/tasks/{dumped_args['taskId']}",
                    jwt=ctx.jwt,
                    turn_id=ctx.turn_id,
                    params={"includeChildren": "true"},
                )
                if isinstance(snap_res.data, dict):
                    task_snapshot = snap_res.data
            except BEError:
                task_snapshot = None

        preview = build_action_preview(
            tool.name,
            dumped_args,
            f"Chạy {tool.name}",
            task_snapshot=task_snapshot,
        )
        record = PendingActionRecord(
            id=action_uuid,
            user_id=ctx.user_id,
            turn_id=ctx.turn_id,
            tool=tool.name,
            args=dumped_args,
            risk=tool.risk,
            source=source,
            preview=preview,
            status="pending",
            expires_at=expires_at,
            created_at=now,
        )
        await store.save_pending_action(record)
        pending_payload: dict[str, Any] = {
            "id": action_uuid,
            "tool": tool.name,
            "risk": tool.risk,
            "title": f"Xác nhận {tool.name}",
            "preview": preview,
            "expiresAt": expires_at.isoformat(),
        }
        return ToolExecutionResult(
            for_model=json.dumps(
                {
                    "status": "pending_approval",
                    "pendingActionId": action_uuid,
                    "message": "Thao tác đang chờ người dùng duyệt.",
                },
                ensure_ascii=False,
            ),
            events=[SSEEvent(event="pending_action", data=pending_payload)],
            executed_ok=True,
            summary_line=f"Đang chờ duyệt {tool.name}",
        )

    events, summary, be_res = await _execute_tool_and_build_events(tool, validated_args, ctx)
    return ToolExecutionResult(
        for_model=json.dumps({"data": be_res.data}, ensure_ascii=False, default=str),
        events=events,
        executed_ok=True,
        summary_line=summary,
    )


async def _persist_turn_and_summary(
    store: InMemoryStore,
    user_id: str,
    conversation_id: str,
    turn_id: str,
    turn_messages: list[dict[str, Any]],
) -> None:
    await store.append_turn_messages(user_id, conversation_id, turn_id, turn_messages)
    summary_text = summarize_older_turns(store.list_turn_messages(user_id, conversation_id))
    if summary_text:
        await store.update_conversation_summary(user_id, conversation_id, summary_text)


async def _fetch_autonomy_mode(
    store: InMemoryStore,
    be: BEClient,
    settings: Settings,
    *,
    user_id: str,
    jwt: str,
    turn_id: str,
) -> Mode:
    """Đọc autonomyMode từ BE (cache 60 giây) ([INV-HARNESS-04])."""
    now_mono = time.monotonic()
    cached = store.get_cached_autonomy_mode(user_id, now_mono, settings.settings_cache_ttl_s)
    if cached is not None:
        return cached

    resp = await be.get("/api/users/me/settings", jwt=jwt, turn_id=turn_id)
    mode: Mode = "by_risk"
    if isinstance(resp.data, dict):
        raw_mode = resp.data.get("autonomyMode")
        if raw_mode in ("ask_always", "by_risk", "auto"):
            mode = raw_mode
    store.set_cached_autonomy_mode(user_id, mode, now_mono)
    return mode


async def handle_turn(
    *,
    user_id: str,
    jwt: str,
    message: str,
    conversation_id: str,
    settings: Settings,
    store: InMemoryStore,
    router: ModelRouter,
    registry: ToolRegistry,
    be: BEClient,
    source: Source = "chat",
    task_kind: TaskKind = "chat",
    now: datetime | None = None,
) -> AsyncIterator[SSEEvent]:
    """Xử lý lượt chat và phát SSE (QĐ-HARNESS-010, [INV-HARNESS-07], [INV-HARNESS-08])."""
    current_now = now or datetime.now(VN_TZ)
    turn_id = str(uuid.uuid4())
    today_str = current_now.astimezone(VN_TZ).date().isoformat()
    tool_calls_count = 0

    allowed, _ = await store.check_and_increment_quota(
        user_id, today_str, settings.daily_message_limit
    )
    if not allowed:
        yield SSEEvent(
            event="error",
            data={
                "code": "QUOTA_EXCEEDED",
                "message": f"Bạn đã dùng hết {settings.daily_message_limit} tin nhắn hôm nay.",
            },
        )
        yield SSEEvent(
            event="done",
            data={"turnId": turn_id, "model": router.last_target, "toolCalls": 0},
        )
        return

    try:
        mode = await _fetch_autonomy_mode(
            store, be, settings, user_id=user_id, jwt=jwt, turn_id=turn_id
        )
    except BEError as exc:
        yield SSEEvent(event="error", data={"code": exc.code, "message": exc.message})
        yield SSEEvent(
            event="done",
            data={"turnId": turn_id, "model": router.last_target, "toolCalls": 0},
        )
        return

    system_prompt = build_system_prompt(current_now)
    summary, recent = await store.get_context(user_id, conversation_id, limit_turns=10)
    msgs = build_messages(system_prompt, summary, recent, message)

    ctx = ToolContext(
        user_id=user_id,
        jwt=jwt,
        turn_id=turn_id,
        be=be,
        last_write_turn_id=store.get_last_write_turn_id(user_id, conversation_id),
    )
    turn_messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
    done_summaries: list[str] = []
    schema_errors = 0
    force_cloud = False

    for step in range(settings.max_tool_steps + 1):
        try:
            resp = await router.complete(
                msgs,
                registry.specs(),
                task_kind=task_kind,
                force_cloud=force_cloud,
            )
        except RouterError as exc:
            yield SSEEvent(event="error", data={"code": exc.code, "message": exc.message})
            yield SSEEvent(
                event="done",
                data={
                    "turnId": turn_id,
                    "model": router.last_target,
                    "toolCalls": tool_calls_count,
                },
            )
            return

        if not resp.tool_calls:
            if resp.content:
                yield SSEEvent(event="text", data={"delta": resp.content})
                turn_messages.append({"role": "assistant", "content": resp.content})
            await _persist_turn_and_summary(store, user_id, conversation_id, turn_id, turn_messages)
            yield SSEEvent(
                event="done",
                data={
                    "turnId": turn_id,
                    "model": router.last_target,
                    "toolCalls": tool_calls_count,
                },
            )
            return

        if step == settings.max_tool_steps:
            summary_text = (
                "Đã chạm giới hạn 6 bước. Đã thực hiện: " + "; ".join(done_summaries)
                if done_summaries
                else (
                    "Đã chạm giới hạn 6 bước thao tác cho một lượt. "
                    "Bạn gửi tiếp yêu cầu nếu cần làm thêm nhé."
                )
            )
            yield SSEEvent(event="text", data={"delta": summary_text})
            turn_messages.append({"role": "assistant", "content": summary_text})
            await _persist_turn_and_summary(store, user_id, conversation_id, turn_id, turn_messages)
            yield SSEEvent(
                event="done",
                data={
                    "turnId": turn_id,
                    "model": router.last_target,
                    "toolCalls": tool_calls_count,
                },
            )
            return

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": resp.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": (
                            tc.arguments
                            if isinstance(tc.arguments, str)
                            else json.dumps(tc.arguments, ensure_ascii=False)
                        ),
                    },
                }
                for tc in resp.tool_calls
            ],
        }
        msgs.append(assistant_msg)
        turn_messages.append(assistant_msg)

        abort_after_retries = False
        for tc in resp.tool_calls:
            try:
                result = await run_tool(
                    registry=registry,
                    store=store,
                    settings=settings,
                    tool_name=tc.name,
                    raw_args=tc.arguments,
                    ctx=ctx,
                    mode=mode,
                    source=source,
                    now=current_now,
                )
            except BEError as exc:
                yield SSEEvent(event="error", data={"code": exc.code, "message": exc.message})
                yield SSEEvent(
                    event="done",
                    data={
                        "turnId": turn_id,
                        "model": router.last_target,
                        "toolCalls": tool_calls_count,
                    },
                )
                return

            for ev in result.events:
                yield ev

            if result.executed_ok:
                tool_calls_count += 1
                if result.summary_line:
                    done_summaries.append(result.summary_line)
                if any(
                    ev.event == "tool_done"
                    and ev.data.get("undoable")
                    and tc.name != "undo_last_action"
                    for ev in result.events
                ):
                    store.set_last_write_turn_id(user_id, conversation_id, turn_id)
                    ctx.last_write_turn_id = turn_id

            if result.schema_error:
                schema_errors += 1
                if schema_errors > settings.max_schema_retries:
                    if settings.router_mode == "hybrid" and not force_cloud:
                        force_cloud = True
                    else:
                        abort_after_retries = True

            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.name,
                "content": result.for_model,
            }
            msgs.append(tool_msg)
            turn_messages.append(tool_msg)

        if abort_after_retries:
            fallback_msg = "Mình chưa hiểu đúng tham số yêu cầu, bạn kiểm tra và nói rõ lại nhé."
            yield SSEEvent(event="text", data={"delta": fallback_msg})
            turn_messages.append({"role": "assistant", "content": fallback_msg})
            await _persist_turn_and_summary(store, user_id, conversation_id, turn_id, turn_messages)
            yield SSEEvent(
                event="done",
                data={
                    "turnId": turn_id,
                    "model": router.last_target,
                    "toolCalls": tool_calls_count,
                },
            )
            return
