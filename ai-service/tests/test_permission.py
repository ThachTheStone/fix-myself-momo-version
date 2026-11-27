from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.policy.permission import Mode, Risk, Source, check


@dataclass
class _DummyTool:
    name: str
    risk: Risk


@pytest.mark.parametrize(
    ("tool_name", "risk", "mode", "source", "expected"),
    [
        # read luôn chạy ở mọi chế độ và mọi source
        ("list_tasks", "read", "ask_always", "chat", "run"),
        ("list_tasks", "read", "by_risk", "proactive", "run"),
        ("list_tasks", "read", "auto", "document", "run"),
        # [INV-HARNESS-03]: proactive không bao giờ tự ghi
        ("create_task", "low", "auto", "proactive", "ask"),
        ("reprioritize_tasks", "medium", "auto", "proactive", "ask"),
        # QĐ-HARNESS-012: create_task_tree luôn hỏi
        ("create_task_tree", "medium", "auto", "document", "ask"),
        ("create_task_tree", "medium", "auto", "chat", "ask"),
        # [INV-HARNESS-02]: high luôn hỏi kể cả auto
        ("delete_task", "high", "auto", "chat", "ask"),
        ("delete_task", "high", "by_risk", "chat", "ask"),
        ("delete_task", "high", "ask_always", "chat", "ask"),
        # ask_always hỏi tất cả tool ghi
        ("create_task", "low", "ask_always", "chat", "ask"),
        ("reprioritize_tasks", "medium", "ask_always", "chat", "ask"),
        # by_risk: low chạy, medium hỏi
        ("create_task", "low", "by_risk", "chat", "run"),
        ("reprioritize_tasks", "medium", "by_risk", "chat", "ask"),
        # auto: low và medium chạy
        ("create_task", "low", "auto", "chat", "run"),
        ("reprioritize_tasks", "medium", "auto", "chat", "run"),
    ],
)
def test_permission_matrix(
    tool_name: str,
    risk: Risk,
    mode: Mode,
    source: Source,
    expected: str,
) -> None:
    """Kiểm đủ ma trận risk × mode × source theo QĐ-HARNESS-004 và [INV-HARNESS-01..03]."""
    assert check(_DummyTool(name=tool_name, risk=risk), mode, source) == expected
