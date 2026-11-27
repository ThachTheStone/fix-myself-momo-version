from __future__ import annotations

from typing import Any

MAX_USER_MESSAGE_CHARS = 2000
MAX_RECENT_TURNS = 10
MAX_SUMMARY_CHARS = 1000


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


def summarize_older_turns(
    turn_items: list[dict[str, Any]],
    *,
    keep_recent_turns: int = MAX_RECENT_TURNS,
) -> str | None:
    """Tóm tắt các lượt cũ ngoài 10 lượt gần nhất (≤ 300 token) (QĐ-HARNESS-014)."""
    ordered_turns: list[str] = []
    for item in turn_items:
        tid = str(item.get("turn_id") or "")
        if tid and tid not in ordered_turns:
            ordered_turns.append(tid)
    if len(ordered_turns) <= keep_recent_turns:
        return None

    older_turns = set(ordered_turns[:-keep_recent_turns])
    snippets: list[str] = []
    for item in turn_items:
        if str(item.get("turn_id") or "") not in older_turns:
            continue
        msg = item.get("message", {})
        role = msg.get("role")
        content = str(msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            prefix = "User" if role == "user" else "AI"
            snippets.append(f"{prefix}: {content[:120]}")

    if not snippets:
        return None
    joined = " | ".join(snippets)
    if len(joined) > MAX_SUMMARY_CHARS:
        return joined[-MAX_SUMMARY_CHARS:]
    return joined
