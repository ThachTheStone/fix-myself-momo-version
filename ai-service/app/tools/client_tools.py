from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def build_client_action(tool_name: str, data: Any) -> dict[str, Any] | None:
    """Sinh sự kiện SSE client_action sau khi tool server_client chạy xong (QĐ-HARNESS-001)."""
    if not isinstance(data, dict):
        return None
    if tool_name == "create_reminder":
        at_raw = data.get("remindAt") or data.get("at")
        if at_raw:
            dt = datetime.fromisoformat(str(at_raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=VN_TZ)
            at_iso = dt.isoformat()
        else:
            at_iso = ""
        return {
            "type": "schedule_notification",
            "payload": {
                "reminderId": str(data.get("id", "")),
                "at": at_iso,
                "title": "Nhắc nhở",
                "body": str(data.get("message", "")),
            },
        }
    if tool_name == "start_focus_session":
        return {
            "type": "start_focus",
            "payload": {
                "sessionId": str(data.get("id", "")),
                "durationMin": data.get("durationMin"),
                "taskTitle": data.get("taskTitle"),
            },
        }
    return None
