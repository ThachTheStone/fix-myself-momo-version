from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from app.store.memory import PendingActionRecord


class PostgresStore:
    """Store Supabase Postgres chỉ dùng schema ai bằng role ai_service (QĐ-HARNESS-017)."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def check_and_increment_quota(
        self, user_id: str, date_str: str, limit: int
    ) -> tuple[bool, int]:
        """Kiểm tra và tăng số tin nhắn ngày trong ai.usage_daily."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO ai.usage_daily (user_id, date, messages)
            VALUES ($1, $2::date, 1)
            ON CONFLICT (user_id, date)
            DO UPDATE SET messages = ai.usage_daily.messages + 1
            WHERE ai.usage_daily.messages < $3
            RETURNING messages
            """,
            user_id,
            date_str,
            limit,
        )
        if row is None:
            current = await self._pool.fetchval(
                "SELECT messages FROM ai.usage_daily WHERE user_id = $1 AND date = $2::date",
                user_id,
                date_str,
            )
            return False, int(current or limit)
        return True, int(row["messages"])

    async def get_context(
        self, user_id: str, conversation_id: str, limit_turns: int = 10
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Đọc tóm tắt hội thoại và 10 lượt gần nhất từ schema ai."""
        summary = await self._pool.fetchval(
            """
            SELECT summary FROM ai.conversation_summary
            WHERE conversation_id = $1 AND user_id = $2
            """,
            conversation_id,
            user_id,
        )
        rows = await self._pool.fetch(
            """
            SELECT turn_id, role, content FROM ai.messages
            WHERE conversation_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            conversation_id,
            user_id,
            limit_turns * 4,
        )
        seen_turns: list[str] = []
        ordered = list(reversed(rows))
        for r in reversed(ordered):
            tid = str(r["turn_id"])
            if tid not in seen_turns:
                seen_turns.append(tid)
                if len(seen_turns) >= limit_turns:
                    break
        allowed = set(seen_turns)
        messages: list[dict[str, Any]] = []
        for r in ordered:
            if str(r["turn_id"]) in allowed:
                payload = r["content"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                messages.append(payload)
        return summary, messages

    async def append_turn_messages(
        self,
        user_id: str,
        conversation_id: str,
        turn_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Ghi messages của lượt chat vào ai.messages."""
        async with self._pool.acquire() as conn:
            for msg in messages:
                await conn.execute(
                    """
                    INSERT INTO ai.messages (user_id, conversation_id, turn_id, role, content)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    """,
                    user_id,
                    conversation_id,
                    turn_id,
                    str(msg.get("role", "assistant")),
                    json.dumps(msg, ensure_ascii=False),
                )

    async def save_pending_action(self, record: PendingActionRecord) -> PendingActionRecord:
        """Lưu pending_action vào ai.pending_action (QĐ-HARNESS-005)."""
        await self._pool.execute(
            """
            INSERT INTO ai.pending_action (
                id, user_id, turn_id, tool, args, risk,
                source, preview, status, expires_at, created_at
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, $9, $10, $11)
            """,
            record.id,
            record.user_id,
            record.turn_id,
            record.tool,
            json.dumps(record.args, ensure_ascii=False),
            record.risk,
            record.source,
            json.dumps(record.preview, ensure_ascii=False),
            record.status,
            record.expires_at,
            record.created_at,
        )
        return record

    async def get_pending_action(self, action_id: str, user_id: str) -> PendingActionRecord | None:
        """Lấy pending_action thuộc user_id."""
        row = await self._pool.fetchrow(
            "SELECT * FROM ai.pending_action WHERE id = $1 AND user_id = $2",
            action_id,
            user_id,
        )
        if row is None:
            return None
        args_val = json.loads(row["args"]) if isinstance(row["args"], str) else row["args"]
        prev_val = json.loads(row["preview"]) if isinstance(row["preview"], str) else row["preview"]
        expires_at = row["expires_at"]
        created_at = row["created_at"]
        assert isinstance(expires_at, datetime) and isinstance(created_at, datetime)
        return PendingActionRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            turn_id=str(row["turn_id"]),
            tool=str(row["tool"]),
            args=args_val,
            risk=row["risk"],
            source=row["source"],
            preview=prev_val,
            status=row["status"],
            expires_at=expires_at,
            created_at=created_at,
        )

    async def transition_pending_status(
        self,
        action_id: str,
        user_id: str,
        new_status: Literal["approved", "rejected", "expired"],
        now: datetime,
    ) -> tuple[Literal["OK", "NOT_FOUND", "EXPIRED"], PendingActionRecord | None]:
        """Chuyển trạng thái pending bằng UPDATE có điều kiện trên Postgres."""
        row = await self._pool.fetchrow(
            """
            UPDATE ai.pending_action
            SET status = $3
            WHERE id = $1 AND user_id = $2 AND status = 'pending' AND expires_at > $4
            RETURNING *
            """,
            action_id,
            user_id,
            new_status,
            now,
        )
        if row is not None:
            rec = await self.get_pending_action(action_id, user_id)
            return "OK", rec

        existing = await self.get_pending_action(action_id, user_id)
        if existing is None:
            return "NOT_FOUND", None
        if existing.status == "expired" or (
            existing.status == "pending" and now > existing.expires_at
        ):
            await self._pool.execute(
                """
                UPDATE ai.pending_action SET status = 'expired'
                WHERE id = $1 AND user_id = $2 AND status = 'pending'
                """,
                action_id,
                user_id,
            )
            existing.status = "expired"
            return "EXPIRED", existing
        return "NOT_FOUND", existing

    async def update_conversation_summary(
        self, user_id: str, conversation_id: str, summary: str
    ) -> None:
        """Lưu/cập nhật tóm tắt hội thoại trong ai.conversation_summary."""
        await self._pool.execute(
            """
            INSERT INTO ai.conversation_summary (conversation_id, user_id, summary, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (user_id, conversation_id)
            DO UPDATE SET summary = EXCLUDED.summary, updated_at = now()
            """,
            conversation_id,
            user_id,
            summary,
        )
