from __future__ import annotations

from typing import Literal, Protocol

Mode = Literal["ask_always", "by_risk", "auto"]
Source = Literal["chat", "proactive", "document"]
Risk = Literal["read", "low", "medium", "high"]


class ToolLike(Protocol):
    """Tối thiểu các thuộc tính của tool để kiểm quyền."""

    name: str
    risk: Risk


def check(tool: ToolLike, mode: Mode, source: Source) -> Literal["run", "ask"]:
    """Kiểm quyền chạy tool theo ma trận chế độ × rủi ro (QĐ-HARNESS-004, [INV-HARNESS-01..03])."""
    if tool.risk == "read":
        return "run"
    if source == "proactive":
        return "ask"
    if tool.name == "create_task_tree":
        return "ask"
    if tool.risk == "high":
        return "ask"
    if mode == "ask_always":
        return "ask"
    if mode == "by_risk":
        return "ask" if tool.risk == "medium" else "run"
    return "run"
