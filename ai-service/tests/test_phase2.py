from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.agent.loop import handle_turn, run_tool
from app.config import Settings
from app.llm.router import LLMResponse, ModelRouter, ToolCallSpec
from app.store.memory import InMemoryStore
from app.tools.be_client import BEClient
from app.tools.registry import ToolContext
from app.tools.server_tools import build_p0_registry
from tests.fake_be import FakeBEState, create_fake_be_app
from tests.fake_llm import FakeLLM

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_NOW = datetime(2026, 11, 27, 10, 0, 0, tzinfo=VN_TZ)


async def test_delete_task_always_pending_even_in_auto_mode() -> None:
    """[INV-HARNESS-02]: tool risk=high luôn sinh pending_action kể cả ở chế độ auto."""
    be_state = FakeBEState()
    be_state.autonomy_modes["tok-1"] = "auto"
    be_state.tasks["t-del"] = {
        "id": "t-del",
        "owner": "tok-1",
        "title": "Họp nhóm cũ",
        "priority": 3,
        "status": "todo",
    }
    be_app, _ = create_fake_be_app(be_state)
    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(id="d1", name="delete_task", arguments={"taskId": "t-del"})
                ]
            ),
            LLMResponse(content="Thao tác xoá đang chờ bạn xác nhận."),
        ]
    )
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_p0_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="xoá task t-del",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert any(e.event == "pending_action" and e.data["tool"] == "delete_task" for e in events)
    assert "deletedAt" not in be_state.tasks["t-del"]


async def test_proactive_write_tool_always_pending_in_auto_mode() -> None:
    """[INV-HARNESS-03]: source=proactive không bao giờ tự ghi trực tiếp."""
    be_app, be_state = create_fake_be_app()
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_p0_registry()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        ctx = ToolContext(user_id="u1", jwt="tok-1", turn_id="turn-pro", be=be_client)
        res = await run_tool(
            registry=registry,
            store=store,
            settings=settings,
            tool_name="create_task",
            raw_args={"title": "Lập kế hoạch sáng"},
            ctx=ctx,
            mode="auto",
            source="proactive",
            now=FIXED_NOW,
        )

    assert len(res.events) == 1
    assert res.events[0].event == "pending_action"
    assert len(be_state.tasks) == 0


async def test_create_reminder_emits_tool_done_and_client_action() -> None:
    """QĐ-HARNESS-001: create_reminder phát SSE tool_done và client_action schedule_notification."""
    be_app, _ = create_fake_be_app()
    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="r1",
                        name="create_reminder",
                        arguments={"remindAt": "2026-11-27T20:00:00", "message": "Gọi mẹ"},
                    )
                ]
            ),
            LLMResponse(content="Đã đặt nhắc nhở lúc 20:00."),
        ]
    )
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_p0_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="nhắc tôi gọi mẹ lúc 8 giờ tối nay",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    event_names = [e.event for e in events]
    assert "tool_done" in event_names
    assert "client_action" in event_names
    ca = next(e for e in events if e.event == "client_action")
    assert ca.data["type"] == "schedule_notification"
    assert ca.data["payload"]["body"] == "Gọi mẹ"
    assert ca.data["payload"]["at"].endswith("+07:00")


async def test_p0_update_priority_complete_batch_and_undo() -> None:
    """Kiểm đủ luồng P0: update_task, set_priority, complete_task, reprioritize_tasks, undo."""
    be_state = FakeBEState()
    be_state.autonomy_modes["tok-1"] = "auto"
    be_state.tasks["t1"] = {
        "id": "t1",
        "owner": "tok-1",
        "title": "Viết spec",
        "priority": 3,
        "status": "todo",
    }
    be_state.tasks["t2"] = {
        "id": "t2",
        "owner": "tok-1",
        "title": "Test API",
        "priority": 3,
        "status": "todo",
    }
    be_app, _ = create_fake_be_app(be_state)
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_p0_registry()

    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="u1",
                        name="update_task",
                        arguments={"taskId": "t1", "title": "Viết spec v2"},
                    ),
                    ToolCallSpec(
                        id="p1",
                        name="set_priority",
                        arguments={"taskId": "t1", "priority": 1, "reason": "gấp"},
                    ),
                    ToolCallSpec(
                        id="b1",
                        name="reprioritize_tasks",
                        arguments={
                            "items": [{"taskId": "t2", "priority": 2}],
                            "reason": "cân bằng tải",
                        },
                    ),
                    ToolCallSpec(id="c1", name="complete_task", arguments={"taskId": "t2"}),
                ]
            ),
            LLMResponse(content="Đã cập nhật và hoàn thành."),
            LLMResponse(tool_calls=[ToolCallSpec(id="un1", name="undo_last_action", arguments={})]),
            LLMResponse(content="Đã hoàn tác lượt vừa rồi."),
        ]
    )
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        _ = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="cập nhật và hoàn thành task",
                conversation_id="c-undo",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]
        assert be_state.tasks["t1"]["title"] == "Viết spec v2"
        assert be_state.tasks["t1"]["priority"] == 1
        assert be_state.tasks["t2"]["priority"] == 2
        assert be_state.tasks["t2"]["status"] == "done"

        events_undo = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="hoàn tác cái vừa rồi",
                conversation_id="c-undo",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert any(e.event == "tool_done" and e.data["tool"] == "undo_last_action" for e in events_undo)
    assert be_state.tasks["t1"]["title"] == "Viết spec"
    assert be_state.tasks["t1"]["priority"] == 3
    assert be_state.tasks["t2"]["status"] == "todo"


async def test_router_concurrency_overflow_routes_to_cloud() -> None:
    """Ca 9b: vượt SMALL_MAX_CONCURRENCY chuyển ngay sang cloud, không xếp hàng chờ."""

    class SlowFakeLLM:
        def __init__(self) -> None:
            self.targets: list[str] = []

        async def complete(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            *,
            target: Any,
            timeout_s: float,
            max_tokens: int,
        ) -> LLMResponse:
            self.targets.append(str(target))
            if target == "small":
                await asyncio.sleep(0.15)
            return LLMResponse(content=f"ok-{target}", model_target=target)

    settings = Settings(
        router_mode="hybrid",
        small_max_concurrency=1,
        cloud_model="gemini/gemini-2.5-flash",
        cloud_api_key="dummy-key",
    )
    client = SlowFakeLLM()
    router = ModelRouter(settings, client=client)  # type: ignore[arg-type]

    r1, r2 = await asyncio.gather(
        router.complete([], [], task_kind="chat"),
        router.complete([], [], task_kind="chat"),
    )
    assert {r1.model_target, r2.model_target} == {"small", "cloud"}
