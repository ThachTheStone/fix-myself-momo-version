from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.agent.loop import handle_turn, run_tool
from app.config import Settings
from app.llm.router import LLMResponse, ModelRouter, RouterError, ToolCallSpec
from app.main import create_app
from app.policy import permission
from app.store.memory import InMemoryStore
from app.tools.be_client import BEClient
from app.tools.registry import ToolContext
from app.tools.server_tools import build_phase1_registry
from tests.fake_be import FakeBEState, create_fake_be_app
from tests.fake_llm import FakeLLM

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_NOW = datetime(2026, 11, 27, 10, 0, 0, tzinfo=VN_TZ)


def _parse_sse_frames(body: str) -> list[tuple[str, dict[str, Any]]]:
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


async def test_health_endpoint() -> None:
    settings = Settings(router_mode="small_only")
    be_app, _ = create_fake_be_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as client:
        app = create_app(settings=settings, llm_client=FakeLLM(), http_client=client)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as api_client:
                resp = await api_client.get("/ai/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cloud"] == "off"


async def test_chat_requires_bearer_jwt() -> None:
    app = create_app(settings=Settings(router_mode="small_only"), llm_client=FakeLLM())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as api_client:
            resp = await api_client.post("/ai/chat", json={"message": "xin chào"})
    assert resp.status_code == 401


async def test_chat_mock_emits_all_six_sse_events() -> None:
    app = create_app(settings=Settings(router_mode="small_only"), llm_client=FakeLLM())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as api_client:
            resp = await api_client.post(
                "/ai/chat?mock=1",
                json={"message": "demo"},
                headers={"Authorization": "Bearer demo-jwt"},
            )
    assert resp.status_code == 200
    events = _parse_sse_frames(resp.text)
    event_names = [name for name, _ in events]
    assert event_names == [
        "text",
        "tool_done",
        "pending_action",
        "client_action",
        "error",
        "done",
    ]


async def test_create_and_read_tools_forward_jwt_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    be_app, be_state = create_fake_be_app()
    check_calls = 0
    original_check = permission.check

    def counted_check(tool: Any, mode: Any, source: Any) -> Any:
        nonlocal check_calls
        check_calls += 1
        return original_check(tool, mode, source)

    monkeypatch.setattr(permission, "check", counted_check)

    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="c1",
                        name="create_task",
                        arguments={
                            "title": "Nộp báo cáo",
                            "deadline": "2026-11-28T23:59:00",
                            "priority": 1,
                        },
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="c2",
                        name="search_tasks",
                        arguments={"query": "báo cáo"},
                    )
                ]
            ),
            LLMResponse(content="Đã tạo task Nộp báo cáo và tìm thấy 1 task."),
        ]
    )

    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_phase1_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="user-1",
                jwt="jwt-secret-user-1",
                message="thêm task nộp báo cáo mai ưu tiên 1",
                conversation_id="conv-1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    # Kiểm INV-HARNESS-01: mọi tool call đi qua permission.check()
    assert check_calls == 2
    assert len(be_state.tasks) == 1
    saved_task = next(iter(be_state.tasks.values()))
    assert saved_task["title"] == "Nộp báo cáo"
    # Kiểm INV-HARNESS-11: deadline thiếu offset được gắn +07:00
    assert saved_task["deadline"].endswith("+07:00")
    # Kiểm INV-HARNESS-04 & INV-HARNESS-09: forward JWT + X-Turn-Id + Idempotency-Key
    write_headers = [h for h in be_state.captured_headers if h.get("idempotency_key")]
    assert len(write_headers) == 1
    assert write_headers[0]["authorization"] == "Bearer jwt-secret-user-1"
    assert write_headers[0]["x_turn_id"]

    event_names = [e.event for e in events]
    assert "tool_done" in event_names
    assert event_names[-1] == "done"
    assert events[-1].data["toolCalls"] == 2


async def test_idempotency_prevents_duplicate_task_in_same_turn() -> None:
    be_app, be_state = create_fake_be_app()
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_phase1_registry()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        ctx = ToolContext(user_id="u1", jwt="tok-1", turn_id="turn-fixed", be=be_client)
        args = {"title": "Mua sữa", "priority": 2}
        await run_tool(
            registry=registry,
            store=store,
            settings=settings,
            tool_name="create_task",
            raw_args=args,
            ctx=ctx,
            mode="by_risk",
            source="chat",
            now=FIXED_NOW,
        )
        await run_tool(
            registry=registry,
            store=store,
            settings=settings,
            tool_name="create_task",
            raw_args=args,
            ctx=ctx,
            mode="by_risk",
            source="chat",
            now=FIXED_NOW,
        )

    assert len(be_state.tasks) == 1


async def test_schema_validation_retries_max_two_times() -> None:
    be_app, be_state = create_fake_be_app()
    # Model gửi priority=7 (sai), rồi deadline quá khứ (sai), rồi sửa đúng ở lần 3
    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="1", name="create_task", arguments={"title": "A", "priority": 7}
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="2",
                        name="create_task",
                        arguments={"title": "A", "deadline": "2026-11-27T08:00:00+07:00"},
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="3", name="create_task", arguments={"title": "A", "priority": 1}
                    )
                ]
            ),
            LLMResponse(content="Đã tạo task A."),
        ]
    )
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_phase1_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="tạo task A",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert len(be_state.tasks) == 1
    assert any(e.event == "tool_done" for e in events)


async def test_max_six_tool_steps_stops_loop() -> None:
    be_app, _ = create_fake_be_app()

    def endless_handler(_msgs: Any, _tools: Any, target: Any) -> LLMResponse:
        return LLMResponse(
            tool_calls=[ToolCallSpec(id="x", name="list_tasks", arguments={"status": "todo"})],
            model_target=target,
        )

    fake_llm = FakeLLM(handler=endless_handler)
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be", max_tool_steps=6)
    store = InMemoryStore()
    registry = build_phase1_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="liệt kê nhiều lần",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert events[-1].event == "done"
    assert events[-1].data["toolCalls"] == 6
    assert any(e.event == "text" and "6 bước" in e.data["delta"] for e in events)


async def test_quota_exceeded_blocks_llm_call() -> None:
    be_app, _ = create_fake_be_app()
    fake_llm = FakeLLM()
    settings = Settings(
        router_mode="small_only",
        be_base_url="http://fake-be",
        daily_message_limit=1,
    )
    store = InMemoryStore()
    registry = build_phase1_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        _ = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="tin 1",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]
        events_2 = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="tin 2",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert len(fake_llm.calls) == 1
    assert events_2[0].event == "error"
    assert events_2[0].data["code"] == "QUOTA_EXCEEDED"


async def test_router_modes_and_hybrid_fallback() -> None:
    settings_small = Settings(router_mode="small_only")
    router_small = ModelRouter(settings_small, client=FakeLLM())
    with pytest.raises(RouterError) as exc_info:
        await router_small.complete([], [], task_kind="document")
    assert exc_info.value.code == "CLOUD_DISABLED"

    settings_hybrid = Settings(
        router_mode="hybrid",
        cloud_model="gemini/gemini-2.5-flash",
        cloud_api_key="dummy-key",
    )
    fake_llm = FakeLLM(
        responses=[
            TimeoutError("small timeout"),
            LLMResponse(content="Cloud OK", model_target="cloud"),
        ]
    )
    router_hybrid = ModelRouter(settings_hybrid, client=fake_llm)
    resp = await router_hybrid.complete([], [], task_kind="chat")
    assert resp.content == "Cloud OK"
    assert router_hybrid.last_target == "cloud"


async def test_get_task_and_get_schedule_routes() -> None:
    be_state = FakeBEState()
    be_state.tasks["t-1"] = {
        "id": "t-1",
        "owner": "tok-1",
        "title": "Họp sprint",
        "deadline": "2026-11-27T15:00:00+07:00",
        "priority": 2,
        "status": "todo",
    }
    be_app, _ = create_fake_be_app(be_state)
    fake_llm = FakeLLM(
        responses=[
            LLMResponse(
                tool_calls=[ToolCallSpec(id="g1", name="get_task", arguments={"taskId": "t-1"})]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCallSpec(
                        id="g2",
                        name="get_schedule",
                        arguments={
                            "from": "2026-11-27T00:00:00+07:00",
                            "to": "2026-11-27T23:59:00+07:00",
                        },
                    )
                ]
            ),
            LLMResponse(content="Hôm nay có 1 lịch họp sprint."),
        ]
    )
    settings = Settings(router_mode="small_only", be_base_url="http://fake-be")
    store = InMemoryStore()
    registry = build_phase1_registry()
    router = ModelRouter(settings, client=fake_llm)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=be_app)) as http_client:
        be_client = BEClient(http_client, base_url="http://fake-be")
        events = [
            ev
            async for ev in handle_turn(
                user_id="u1",
                jwt="tok-1",
                message="xem chi tiết task t-1 và lịch hôm nay",
                conversation_id="c1",
                settings=settings,
                store=store,
                router=router,
                registry=registry,
                be=be_client,
                now=FIXED_NOW,
            )
        ]

    assert events[-1].data["toolCalls"] == 2
    assert any(e.event == "text" for e in events)
