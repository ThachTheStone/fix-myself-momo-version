from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class FakeCreateTaskBody(BaseModel):
    title: str
    description: str | None = None
    deadline: str | None = None
    priority: int = 3
    parentId: str | None = None
    estimateMin: int | None = None


class FakeUpdateTaskBody(BaseModel):
    title: str | None = None
    description: str | None = None
    deadline: str | None = None
    priority: int | None = None
    estimateMin: int | None = None
    status: str | None = None


class FakeBatchPriorityBody(BaseModel):
    items: list[dict[str, Any]]
    reason: str = ""


class FakeReminderBody(BaseModel):
    remindAt: str
    message: str
    taskId: str | None = None


class FakeBEState:
    """Trạng thái lưu trữ giả lập của BE .NET cho unit/integration test."""

    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self.reminders: dict[str, dict[str, Any]] = {}
        self.action_logs: list[dict[str, Any]] = []
        self.idempotency: dict[tuple[str, str], dict[str, Any]] = {}
        self.autonomy_modes: dict[str, str] = {}
        self.captured_headers: list[dict[str, str]] = []


def _auth_user(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail={"code": "UNAUTHORIZED", "message": "Missing JWT"}
        )
    token = authorization[len("Bearer ") :].strip()
    if not token or token == "expired-jwt":
        raise HTTPException(
            status_code=401, detail={"code": "UNAUTHORIZED", "message": "Expired JWT"}
        )
    return token


def create_fake_be_app(state: FakeBEState | None = None) -> tuple[FastAPI, FakeBEState]:
    """Tạo FastAPI app giả lập hợp đồng BE cho Giai đoạn 1."""
    be_state = state or FakeBEState()
    app = FastAPI(title="Fake BE")

    @app.get("/api/users/me/settings")
    async def get_settings(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        user = _auth_user(authorization)
        mode = be_state.autonomy_modes.get(user, "by_risk")
        return {"data": {"autonomyMode": mode, "morningPlanTime": "07:30"}}

    @app.get("/api/tasks")
    async def list_tasks(
        q: str | None = Query(default=None),
        status: str | None = Query(default=None),
        priority: int | None = Query(default=None),
        limit: int = Query(default=50),
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        be_state.captured_headers.append(
            {"authorization": authorization or "", "x_turn_id": x_turn_id or ""}
        )
        items = [t for t in be_state.tasks.values() if t["owner"] == user]
        if q:
            q_lower = q.lower()
            items = [t for t in items if q_lower in t["title"].lower()]
        if status:
            items = [t for t in items if t["status"] == status]
        if priority is not None:
            items = [t for t in items if t["priority"] == priority]
        return {"data": items[:limit]}

    @app.get("/api/tasks/{task_id}")
    async def get_task(
        task_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        task = be_state.tasks.get(task_id)
        if task is None or task["owner"] != user:
            raise HTTPException(
                status_code=404,
                detail={"code": "TASK_NOT_FOUND", "message": "Không tìm thấy task"},
            )
        return {"data": task}

    @app.get("/api/schedule")
    async def get_schedule(
        from_: str = Query(alias="from"),
        to: str = Query(),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        items = [
            t
            for t in be_state.tasks.values()
            if t["owner"] == user and t.get("deadline") and from_ <= t["deadline"] <= to
        ]
        return {"data": {"tasks": items, "reminders": [], "focusSessions": []}}

    @app.post("/api/tasks")
    async def create_task(
        body: FakeCreateTaskBody,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        be_state.captured_headers.append(
            {
                "authorization": authorization or "",
                "x_turn_id": x_turn_id or "",
                "idempotency_key": idempotency_key or "",
            }
        )
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]

        now_iso = datetime.now(VN_TZ).replace(microsecond=0).isoformat()
        task_id = str(uuid.uuid4())
        action_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "owner": user,
            "title": body.title,
            "description": body.description,
            "deadline": body.deadline,
            "priority": body.priority,
            "parentId": body.parentId,
            "estimateMin": body.estimateMin,
            "status": "todo",
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }
        be_state.tasks[task_id] = task
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "create_task",
                "entityType": "task",
                "entityId": task_id,
                "before": None,
            }
        )
        response = {"data": task, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = response
        return response

    @app.patch("/api/tasks/{task_id}")
    async def update_task(
        task_id: str,
        body: FakeUpdateTaskBody,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]
        task = be_state.tasks.get(task_id)
        if task is None or task["owner"] != user:
            raise HTTPException(
                status_code=404,
                detail={"code": "TASK_NOT_FOUND", "message": "Không tìm thấy task"},
            )
        before = dict(task)
        updates = body.model_dump(exclude_none=True)
        task.update(updates)
        task["updatedAt"] = datetime.now(VN_TZ).replace(microsecond=0).isoformat()
        action_id = str(uuid.uuid4())
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "update_task",
                "entityType": "task",
                "entityId": task_id,
                "before": before,
            }
        )
        resp = {"data": task, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = resp
        return resp

    @app.post("/api/tasks/{task_id}/complete")
    async def complete_task(
        task_id: str,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]
        task = be_state.tasks.get(task_id)
        if task is None or task["owner"] != user:
            raise HTTPException(
                status_code=404,
                detail={"code": "TASK_NOT_FOUND", "message": "Không tìm thấy task"},
            )
        before = dict(task)
        task["status"] = "done"
        task["updatedAt"] = datetime.now(VN_TZ).replace(microsecond=0).isoformat()
        action_id = str(uuid.uuid4())
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "complete_task",
                "entityType": "task",
                "entityId": task_id,
                "before": before,
            }
        )
        resp = {"data": task, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = resp
        return resp

    @app.delete("/api/tasks/{task_id}")
    async def delete_task(
        task_id: str,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]
        task = be_state.tasks.get(task_id)
        if task is None or task["owner"] != user:
            raise HTTPException(
                status_code=404,
                detail={"code": "TASK_NOT_FOUND", "message": "Không tìm thấy task"},
            )
        before = dict(task)
        task["deletedAt"] = datetime.now(VN_TZ).replace(microsecond=0).isoformat()
        action_id = str(uuid.uuid4())
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "delete_task",
                "entityType": "task",
                "entityId": task_id,
                "before": before,
            }
        )
        resp = {"data": task, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = resp
        return resp

    @app.post("/api/tasks/batch-priority")
    async def batch_priority(
        body: FakeBatchPriorityBody,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]
        before_map: dict[str, dict[str, Any]] = {}
        updated: list[dict[str, Any]] = []
        for item in body.items:
            tid = str(item["taskId"])
            task = be_state.tasks.get(tid)
            if task is not None and task["owner"] == user:
                before_map[tid] = dict(task)
                task["priority"] = int(item["priority"])
                updated.append(task)
        action_id = str(uuid.uuid4())
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "reprioritize_tasks",
                "entityType": "batch",
                "beforeMap": before_map,
            }
        )
        resp = {"data": updated, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = resp
        return resp

    @app.post("/api/reminders")
    async def create_reminder(
        body: FakeReminderBody,
        authorization: str | None = Header(default=None),
        x_turn_id: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        if idempotency_key and (user, idempotency_key) in be_state.idempotency:
            return be_state.idempotency[(user, idempotency_key)]
        rem_id = str(uuid.uuid4())
        rem = {
            "id": rem_id,
            "owner": user,
            "taskId": body.taskId,
            "remindAt": body.remindAt,
            "message": body.message,
        }
        be_state.reminders[rem_id] = rem
        action_id = str(uuid.uuid4())
        be_state.action_logs.append(
            {
                "actionId": action_id,
                "turnId": x_turn_id,
                "userId": user,
                "tool": "create_reminder",
                "entityType": "reminder",
                "entityId": rem_id,
                "before": None,
            }
        )
        resp = {"data": rem, "actionId": action_id}
        if idempotency_key:
            be_state.idempotency[(user, idempotency_key)] = resp
        return resp

    @app.post("/api/actions/undo-turn/{turn_id}")
    async def undo_turn(
        turn_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user = _auth_user(authorization)
        logs = [
            log
            for log in be_state.action_logs
            if log.get("turnId") == turn_id and log.get("userId") == user and not log.get("undone")
        ]
        for log in reversed(logs):
            if log.get("entityType") == "batch":
                for tid, prev in log.get("beforeMap", {}).items():
                    be_state.tasks[tid] = dict(prev)
            elif log.get("entityType") == "task":
                tid = log["entityId"]
                if log.get("before") is None:
                    be_state.tasks.pop(tid, None)
                else:
                    be_state.tasks[tid] = dict(log["before"])
            elif log.get("entityType") == "reminder":
                be_state.reminders.pop(log["entityId"], None)
            log["undone"] = True
        return {"data": {"undoneCount": len(logs)}, "actionId": str(uuid.uuid4())}

    return app, be_state
