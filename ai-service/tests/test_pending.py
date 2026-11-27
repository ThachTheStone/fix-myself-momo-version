from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.agent.loop import handle_turn
from app.config import Settings
from app.llm.router import LLMResponse, ModelRouter
from app.main import create_app
from app.store.memory import InMemoryStore, PendingActionRecord
from app.tools.be_client import BEClient
from app.tools.server_tools import build_p0_registry
from tests.fake_be import FakeBEState, create_fake_be_app
from tests.fake_llm import FakeLLM

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_NOW = datetime(2026, 11, 27, 10, 0, 0, tzinfo=VN_TZ)


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    current_event = "message"
    for line in body.splitlines():
        line = line.rstrip("\r")
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            raw = line[len("data:") :].strip()
            if raw:
                events.append((current_event, json.loads(raw)))
    return events


async def _seed_pending(
    app: Any,
    *,
    action_id: str = "pend-1",
    user_id: str = "user-a",
    tool: str = "delete_task",
    args: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
) -> None:
    record = PendingActionRecord(
        id=action_id,
        user_id=user_id,
        turn_id="turn-orig",
        tool=tool,
        args=args or {"taskId": "t1"},
        risk="high" if tool == "delete_task" else "medium",
        source="chat",
        preview={"kind": "list", "items": [{"taskId": "t1"}]},
        status="pending",
        expires_at=expires_at or (FIXED_NOW + timedelta(minutes=30)),
        created_at=FIXED_NOW,
    )
    await app.state.store.save_pending_action(record)


def _jwt_for(sub: str) -> str:
    import base64

    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


async def test_approve_executes_tool_and_blocks_double_approve() -> None:
    """Ca biên 6: approve lần 1 chạy tool trên BE giả; lần 2 trả 404 PENDING_NOT_FOUND."""
    be_state = FakeBEState()
    jwt_a = _jwt_for("user-a")
    be_state.tasks["t1"] = {
        "id": "t1",
        "owner": jwt_a,
        "title": "Họp nhóm",
        "priority": 3,
        "status": "todo",
    }
    be_app, _ = create_fake_be_app(be_state)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as be_http:
        app = create_app(
            settings=Settings(router_mode="small_only", be_base_url="http://fake-be"),
            llm_client=FakeLLM(),
            http_client=be_http,
        )
        async with app.router.lifespan_context(app):
            app.state.clock_now = lambda: FIXED_NOW
            await _seed_pending(app, action_id="p-del", user_id="user-a")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as api:
                r1 = await api.post(
                    "/ai/actions/p-del/approve",
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )
                r2 = await api.post(
                    "/ai/actions/p-del/approve",
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )

    assert r1.status_code == 200
    events = _parse_sse(r1.text)
    assert events[0][0] == "tool_done"
    assert events[0][1]["turnId"] == "turn-orig"
    assert events[-1][0] == "done"
    assert "deletedAt" in be_state.tasks["t1"]
    assert len(be_state.action_logs) == 1
    assert r2.status_code == 404
    assert r2.json()["detail"]["code"] == "PENDING_NOT_FOUND"


async def test_approve_with_edited_args_and_invalid_args() -> None:
    """approve với editedArgs sai schema trả 422 và giữ pending; hợp lệ chạy với args mới."""
    be_state = FakeBEState()
    jwt_a = _jwt_for("user-a")
    be_state.tasks["t1"] = {
        "id": "t1",
        "owner": jwt_a,
        "title": "Task A",
        "priority": 3,
        "status": "todo",
    }
    be_app, _ = create_fake_be_app(be_state)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as be_http:
        app = create_app(
            settings=Settings(router_mode="small_only", be_base_url="http://fake-be"),
            llm_client=FakeLLM(),
            http_client=be_http,
        )
        async with app.router.lifespan_context(app):
            app.state.clock_now = lambda: FIXED_NOW
            await _seed_pending(
                app,
                action_id="p-prio",
                user_id="user-a",
                tool="reprioritize_tasks",
                args={"items": [{"taskId": "t1", "priority": 2}], "reason": "gấp"},
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as api:
                bad = await api.post(
                    "/ai/actions/p-prio/approve",
                    json={"editedArgs": {"items": [{"taskId": "t1", "priority": 9}]}},
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )
                good = await api.post(
                    "/ai/actions/p-prio/approve",
                    json={
                        "editedArgs": {
                            "items": [{"taskId": "t1", "priority": 1}],
                            "reason": "rất gấp",
                        }
                    },
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )

    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "TOOL_ARGS_INVALID"
    assert good.status_code == 200
    assert be_state.tasks["t1"]["priority"] == 1


async def test_approve_expired_returns_410_and_does_not_write() -> None:
    """Ca biên 5: duyệt pending_action sau 31 phút trả 410 PENDING_EXPIRED, không gọi BE."""
    be_state = FakeBEState()
    jwt_a = _jwt_for("user-a")
    be_state.tasks["t1"] = {"id": "t1", "owner": jwt_a, "title": "Task", "priority": 3}
    be_app, _ = create_fake_be_app(be_state)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as be_http:
        app = create_app(
            settings=Settings(router_mode="small_only", be_base_url="http://fake-be"),
            llm_client=FakeLLM(),
            http_client=be_http,
        )
        async with app.router.lifespan_context(app):
            await _seed_pending(
                app,
                action_id="p-exp",
                user_id="user-a",
                expires_at=FIXED_NOW + timedelta(minutes=30),
            )
            app.state.clock_now = lambda: FIXED_NOW + timedelta(minutes=31)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as api:
                resp = await api.post(
                    "/ai/actions/p-exp/approve",
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )

    assert resp.status_code == 410
    assert resp.json()["detail"]["code"] == "PENDING_EXPIRED"
    assert len(be_state.action_logs) == 0


async def test_reject_and_cross_user_isolation() -> None:
    """reject trả 204; user khác không được approve/reject pending_action của user-a."""
    be_app, _ = create_fake_be_app()
    jwt_a = _jwt_for("user-a")
    jwt_b = _jwt_for("user-b")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as be_http:
        app = create_app(
            settings=Settings(router_mode="small_only", be_base_url="http://fake-be"),
            llm_client=FakeLLM(),
            http_client=be_http,
        )
        async with app.router.lifespan_context(app):
            app.state.clock_now = lambda: FIXED_NOW
            await _seed_pending(app, action_id="p-rej", user_id="user-a")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as api:
                cross = await api.post(
                    "/ai/actions/p-rej/approve",
                    headers={"Authorization": f"Bearer {jwt_b}"},
                )
                rej = await api.post(
                    "/ai/actions/p-rej/reject",
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )
                after_rej = await api.post(
                    "/ai/actions/p-rej/approve",
                    headers={"Authorization": f"Bearer {jwt_a}"},
                )

    assert cross.status_code == 404
    assert rej.status_code == 204
    assert after_rej.status_code == 404


async def test_conversation_summary_updates_after_10_turns() -> None:
    """QĐ-HARNESS-014: hội thoại > 10 lượt tự cập nhật summary và chỉ giữ 10 lượt gần nhất."""
    be_app, _ = create_fake_be_app()
    fake_llm = FakeLLM(responses=[LLMResponse(content=f"Trả lời {i}") for i in range(12)])
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_p0_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as be_http:
        be_client = BEClient(be_http, base_url="http://fake-be")
        for idx in range(12):
            _ = [
                ev
                async for ev in handle_turn(
                    user_id="user-sum",
                    jwt="tok-sum",
                    message=f"Tin nhắn số {idx}",
                    conversation_id="conv-sum",
                    settings=settings,
                    store=store,
                    router=router,
                    registry=registry,
                    be=be_client,
                    now=FIXED_NOW,
                )
            ]

    summary, recent = await store.get_context("user-sum", "conv-sum", limit_turns=10)
    assert summary is not None
    assert "Tin nhắn số 0" in summary
    assert "Tin nhắn số 1" in summary
    # 10 lượt gần nhất (từ lượt 2..11), mỗi lượt gồm user + assistant = 20 messages
    assert len(recent) == 20
    assert recent[0]["content"] == "Tin nhắn số 2"
