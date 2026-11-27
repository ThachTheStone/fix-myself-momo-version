from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.store.memory import InMemoryStore, PendingActionRecord
from app.tools.registry import ToolRegistry

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass
class PendingActionError(Exception):
    """Lỗi khi duyệt hoặc từ chối pending_action (404/410/422)."""

    status_code: int
    code: str
    message: str


def build_action_preview(
    tool_name: str,
    args_dict: dict[str, Any],
    summary_text: str,
    *,
    task_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sinh dữ liệu preview cho thẻ xác nhận (QĐ-HARNESS-005)."""
    if tool_name == "delete_task":
        snap = task_snapshot or {}
        children = snap.get("children")
        child_count = len(children) if isinstance(children, list) else 0
        return {
            "kind": "list",
            "items": [
                {
                    "taskId": args_dict.get("taskId"),
                    "title": snap.get("title", f"Task {args_dict.get('taskId', '')}"),
                    "deadline": snap.get("deadline"),
                    "childCount": child_count,
                }
            ],
        }

    if tool_name in ("reprioritize_tasks", "reschedule_tasks"):
        field_name = "priority" if tool_name == "reprioritize_tasks" else "deadline"
        diff_items = [
            {
                "taskId": item.get("taskId"),
                "title": item.get("title") or f"Task {item.get('taskId', '')}",
                "field": field_name,
                "from": item.get("from"),
                "to": item.get(field_name),
            }
            for item in args_dict.get("items", [])
            if isinstance(item, dict)
        ]
        return {"kind": "diff", "items": diff_items}

    if tool_name == "create_task_tree":
        root = args_dict.get("root", args_dict)
        return {"kind": "tree", "items": [root]}

    return {
        "kind": "list",
        "items": [{"label": summary_text or tool_name, "args": args_dict}],
    }


async def prepare_approval(
    *,
    store: InMemoryStore,
    registry: ToolRegistry,
    action_id: str,
    user_id: str,
    edited_args: dict[str, Any] | None,
    now: datetime | None = None,
) -> tuple[PendingActionRecord, BaseModel]:
    """Kiểm tra hạn, validate editedArgs và chuyển nguyên tử pending -> approved."""
    current_now = now or datetime.now(VN_TZ)
    existing = await store.get_pending_action(action_id, user_id)
    if existing is None:
        raise PendingActionError(404, "PENDING_NOT_FOUND", "Không tìm thấy yêu cầu chờ duyệt")
    if existing.status == "expired":
        raise PendingActionError(410, "PENDING_EXPIRED", "Yêu cầu duyệt đã hết hạn")
    if existing.status != "pending":
        raise PendingActionError(404, "PENDING_NOT_FOUND", "Yêu cầu đã được xử lý trước đó")
    if current_now > existing.expires_at:
        await store.transition_pending_status(action_id, user_id, "expired", current_now)
        raise PendingActionError(410, "PENDING_EXPIRED", "Yêu cầu duyệt đã hết hạn")

    tool = registry.get(existing.tool)
    if tool is None:
        raise PendingActionError(404, "UNKNOWN_TOOL", f"Không tồn tại tool '{existing.tool}'")

    raw_args = edited_args if edited_args is not None else existing.args
    try:
        validated_args = tool.args_model.model_validate(raw_args, context={"now": current_now})
    except (ValueError, ValidationError) as exc:
        raise PendingActionError(422, "TOOL_ARGS_INVALID", str(exc)) from exc

    status, record = await store.transition_pending_status(
        action_id, user_id, "approved", current_now
    )
    if status == "EXPIRED":
        raise PendingActionError(410, "PENDING_EXPIRED", "Yêu cầu duyệt đã hết hạn")
    if status != "OK" or record is None:
        raise PendingActionError(404, "PENDING_NOT_FOUND", "Yêu cầu đã được xử lý trước đó")

    return record, validated_args


async def reject_pending_action(
    *,
    store: InMemoryStore,
    action_id: str,
    user_id: str,
    now: datetime | None = None,
) -> None:
    """Từ chối pending_action và chuyển trạng thái rejected (QĐ-HARNESS-005)."""
    current_now = now or datetime.now(VN_TZ)
    status, _ = await store.transition_pending_status(action_id, user_id, "rejected", current_now)
    if status == "EXPIRED":
        raise PendingActionError(410, "PENDING_EXPIRED", "Yêu cầu duyệt đã hết hạn")
    if status != "OK":
        raise PendingActionError(404, "PENDING_NOT_FOUND", "Không tìm thấy yêu cầu chờ duyệt")
