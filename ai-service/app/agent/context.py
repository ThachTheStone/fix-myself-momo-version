from __future__ import annotations

from typing import Any

MAX_USER_MESSAGE_CHARS = 2000


def build_messages(
    system_prompt: str,
    summary: str | None,
    recent_messages: list[dict[str, Any]],
    user_message: str,
) -> list[dict[str, Any]]:
    """Dựng ngữ cảnh: system prompt + tóm tắt + 10 lượt gần nhất + tin mới (QĐ-HARNESS-014)."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"Tóm tắt hội thoại trước đó: {summary}",
            }
        )
    messages.extend(recent_messages)
    trimmed = user_message[:MAX_USER_MESSAGE_CHARS]
    messages.append({"role": "user", "content": trimmed})
    return messages
