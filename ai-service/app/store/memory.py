from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol


@dataclass
class PendingActionRecord:
    """Bản ghi pending_action chờ người dùng duyệt (QĐ-HARNESS-005)."""

    id: str
    user_id: str
    turn_id: str
    tool: str
    args: dict[str, Any]
    risk: Literal["read", "low", "medium", "high"]
    source: Literal["chat", "proactive", "document"]
    preview: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "expired"]
    expires_at: datetime
    created_at: datetime


@dataclass
class UserSettingsCacheEntry:
    """Cache autonomyMode của người dùng trong 60 giây."""

    autonomy_mode: Literal["ask_always", "by_risk", "auto"]
    cached_at: float


class ConversationStoreProtocol(Protocol):
    """Giao diện lưu trữ schema ai để thay thế bằng Supabase asyncpg ở Giai đoạn 2."""

    async def check_and_increment_quota(
        self, user_id: str, date_str: str, limit: int
    ) -> tuple[bool, int]: ...

    async def get_context(
        self, user_id: str, conversation_id: str, limit_turns: int = 10
    ) -> tuple[str | None, list[dict[str, Any]]]: ...

    async def append_turn_messages(
        self,
        user_id: str,
        conversation_id: str,
        turn_id: str,
        messages: list[dict[str, Any]],
    ) -> None: ...

    async def save_pending_action(self, record: PendingActionRecord) -> PendingActionRecord: ...

    async def get_pending_action(
        self, action_id: str, user_id: str
    ) -> PendingActionRecord | None: ...

    async def transition_pending_status(
        self,
        action_id: str,
        user_id: str,
        new_status: Literal["approved", "rejected", "expired"],
        now: datetime,
    ) -> tuple[Literal["OK", "NOT_FOUND", "EXPIRED"], PendingActionRecord | None]: ...

    async def update_conversation_summary(
        self, user_id: str, conversation_id: str, summary: str
    ) -> None: ...


class InMemoryStore:
    """Store trong bộ nhớ cho Giai đoạn 1 (QĐ-HARNESS-017)."""

    def __init__(self) -> None:
        self._usage_daily: dict[tuple[str, str], int] = defaultdict(int)
        self._messages: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._summaries: dict[tuple[str, str], str] = {}
        self._pending_actions: dict[str, PendingActionRecord] = {}
        self._settings_cache: dict[str, UserSettingsCacheEntry] = {}
        self._last_write_turn: dict[tuple[str, str], str] = {}

    async def check_and_increment_quota(
        self, user_id: str, date_str: str, limit: int
    ) -> tuple[bool, int]:
        """Kiểm tra quota ngày và tăng bộ đếm nếu chưa vượt (QĐ-HARNESS-014)."""
        key = (user_id, date_str)
        current = self._usage_daily[key]
        if current >= limit:
            return False, current
        self._usage_daily[key] = current + 1
        return True, current + 1

    async def get_context(
        self, user_id: str, conversation_id: str, limit_turns: int = 10
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Lấy tóm tắt hội thoại và tối đa 10 lượt gần nhất (QĐ-HARNESS-014)."""
        key = (user_id, conversation_id)
        summary = self._summaries.get(key)
        history = self._messages.get(key, [])
        # Mỗi lượt trung bình 2–4 message; giữ tối đa 10 lượt gần nhất theo turn_id
        seen_turns: list[str] = []
        for item in reversed(history):
            tid = item.get("turn_id", "")
            if tid and tid not in seen_turns:
                seen_turns.append(tid)
                if len(seen_turns) >= limit_turns:
                    break
        allowed_turns = set(seen_turns)
        recent = [
            item["message"]
            for item in history
            if not allowed_turns or item.get("turn_id") in allowed_turns
        ]
        return summary, recent

    async def append_turn_messages(
        self,
        user_id: str,
        conversation_id: str,
        turn_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Lưu các message phát sinh trong lượt chat hiện tại."""
        key = (user_id, conversation_id)
        for msg in messages:
            self._messages[key].append({"turn_id": turn_id, "message": msg})

    async def save_pending_action(self, record: PendingActionRecord) -> PendingActionRecord:
        """Lưu pending_action vào bộ nhớ."""
        self._pending_actions[record.id] = record
        return record

    async def get_pending_action(self, action_id: str, user_id: str) -> PendingActionRecord | None:
        """Tìm pending_action thuộc về user_id."""
        rec = self._pending_actions.get(action_id)
        if rec is None or rec.user_id != user_id:
            return None
        return rec

    async def transition_pending_status(
        self,
        action_id: str,
        user_id: str,
        new_status: Literal["approved", "rejected", "expired"],
        now: datetime,
    ) -> tuple[Literal["OK", "NOT_FOUND", "EXPIRED"], PendingActionRecord | None]:
        """Chuyển trạng thái pending nguyên tử; hết hạn trả EXPIRED, đã xử lý trả NOT_FOUND."""
        rec = self._pending_actions.get(action_id)
        if rec is None or rec.user_id != user_id:
            return "NOT_FOUND", None
        if rec.status == "expired":
            return "EXPIRED", rec
        if rec.status != "pending":
            return "NOT_FOUND", rec
        if now > rec.expires_at:
            rec.status = "expired"
            return "EXPIRED", rec
        rec.status = new_status
        return "OK", rec

    async def update_conversation_summary(
        self, user_id: str, conversation_id: str, summary: str
    ) -> None:
        """Cập nhật tóm tắt hội thoại khi vượt 10 lượt (QĐ-HARNESS-014)."""
        self._summaries[(user_id, conversation_id)] = summary

    def list_turn_messages(self, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
        """Lấy lịch sử thô để trích các lượt cũ cần tóm tắt."""
        return list(self._messages.get((user_id, conversation_id), []))

    def get_cached_autonomy_mode(
        self, user_id: str, now_monotonic: float, ttl_s: int
    ) -> Literal["ask_always", "by_risk", "auto"] | None:
        """Đọc cache autonomyMode nếu còn hạn."""
        entry = self._settings_cache.get(user_id)
        if entry is None:
            return None
        if now_monotonic - entry.cached_at > ttl_s:
            return None
        return entry.autonomy_mode

    def set_cached_autonomy_mode(
        self,
        user_id: str,
        mode: Literal["ask_always", "by_risk", "auto"],
        now_monotonic: float,
    ) -> None:
        """Cập nhật cache autonomyMode cho user."""
        self._settings_cache[user_id] = UserSettingsCacheEntry(
            autonomy_mode=mode,
            cached_at=now_monotonic,
        )

    def get_last_write_turn_id(self, user_id: str, conversation_id: str) -> str | None:
        """Lấy turnId của thao tác ghi gần nhất trong hội thoại."""
        return self._last_write_turn.get((user_id, conversation_id))

    def set_last_write_turn_id(self, user_id: str, conversation_id: str, turn_id: str) -> None:
        """Lưu turnId của thao tác ghi gần nhất để hỗ trợ undo_last_action."""
        self._last_write_turn[(user_id, conversation_id)] = turn_id
