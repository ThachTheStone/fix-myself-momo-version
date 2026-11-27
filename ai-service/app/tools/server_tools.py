from __future__ import annotations

from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.tools.be_client import BEResponse
from app.tools.registry import Tool, ToolContext, ToolRegistry
from app.tools.schemas import (
    CompleteTaskArgs,
    CreateReminderArgs,
    CreateTaskArgs,
    DeleteTaskArgs,
    GetScheduleArgs,
    GetTaskArgs,
    ListTasksArgs,
    ReprioritizeTasksArgs,
    SearchTasksArgs,
    SetPriorityArgs,
    UndoLastActionArgs,
    UpdateTaskArgs,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_WEEKDAY_VI = {
    0: "Th 2",
    1: "Th 3",
    2: "Th 4",
    3: "Th 5",
    4: "Th 6",
    5: "Th 7",
    6: "CN",
}


def format_vn_datetime(value: str | None) -> str:
    """Định dạng ISO datetime sang chuỗi ngắn theo giờ Asia/Ho_Chi_Minh ([INV-HARNESS-11])."""
    if not value:
        return ""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    else:
        dt = dt.astimezone(VN_TZ)
    wd = _WEEKDAY_VI[dt.weekday()]
    return f"{wd} {dt.day:02d}/{dt.month:02d} {dt.hour:02d}:{dt.minute:02d}"


async def _call_list_tasks(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(ListTasksArgs, args)
    params = parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
    return await ctx.be.get("/api/tasks", jwt=ctx.jwt, turn_id=ctx.turn_id, params=params)


async def _call_search_tasks(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(SearchTasksArgs, args)
    return await ctx.be.get(
        "/api/tasks",
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        params={"q": parsed.query},
    )


async def _call_get_task(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(GetTaskArgs, args)
    return await ctx.be.get(
        f"/api/tasks/{parsed.taskId}",
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        params={"includeChildren": "true"},
    )


async def _call_get_schedule(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(GetScheduleArgs, args)
    params = parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
    return await ctx.be.get("/api/schedule", jwt=ctx.jwt, turn_id=ctx.turn_id, params=params)


async def _call_create_task(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(CreateTaskArgs, args)
    return await ctx.be.post(
        "/api/tasks",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="create_task",
        write=True,
    )


def _summarize_create_task(res: BEResponse) -> str:
    data = res.data if isinstance(res.data, dict) else {}
    title = data.get("title", "")
    deadline = data.get("deadline")
    if deadline:
        return f"Đã tạo task '{title}' · hạn {format_vn_datetime(str(deadline))}"
    return f"Đã tạo task '{title}'"


def build_phase1_registry() -> ToolRegistry:
    """Đăng ký 4 tool đọc + create_task cho Giai đoạn 1 (QĐ-HARNESS-001)."""
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="list_tasks",
            description=(
                "Liệt kê danh sách công việc (task) của người dùng theo bộ lọc trạng thái, "
                "độ ưu tiên hoặc khoảng hạn chót. Ví dụ: 'xem các việc chưa xong' → "
                "status='todo'; 'task ưu tiên 1' → priority=1."
            ),
            args_model=ListTasksArgs,
            risk="read",
            runs_on="server",
            call=_call_list_tasks,
            summarize=lambda r: f"Đã lấy {len(r.data) if isinstance(r.data, list) else 0} task",
        )
    )

    registry.register(
        Tool(
            name="search_tasks",
            description=(
                "Tìm kiếm task theo từ khoá tiêu đề (hỗ trợ không dấu). Dùng khi người dùng "
                "muốn tìm việc cụ thể như 'tìm task báo cáo' → query='báo cáo'. "
                "Không dùng khi người dùng muốn xem toàn bộ danh sách theo trạng thái."
            ),
            args_model=SearchTasksArgs,
            risk="read",
            runs_on="server",
            call=_call_search_tasks,
            summarize=lambda r: f"Tìm thấy {len(r.data) if isinstance(r.data, list) else 0} task",
        )
    )

    registry.register(
        Tool(
            name="get_task",
            description=(
                "Lấy thông tin chi tiết một task theo mã taskId (kèm task con nếu có). "
                "Ví dụ: 'xem chi tiết task 123' → taskId='123'."
            ),
            args_model=GetTaskArgs,
            risk="read",
            runs_on="server",
            call=_call_get_task,
            summarize=lambda r: "Đã lấy chi tiết task",
        )
    )

    registry.register(
        Tool(
            name="get_schedule",
            description=(
                "Xem lịch làm việc gồm các task có hạn, nhắc nhở và phiên focus trong khoảng "
                "thời gian from đến to (ISO 8601 +07:00). Ví dụ: 'lịch hôm nay' → "
                "from=<đầu ngày +07:00>, to=<cuối ngày +07:00>."
            ),
            args_model=GetScheduleArgs,
            risk="read",
            runs_on="server",
            call=_call_get_schedule,
            summarize=lambda r: "Đã lấy lịch làm việc",
        )
    )

    registry.register(
        Tool(
            name="create_task",
            description=(
                "Tạo một task mới từ yêu cầu người dùng. Dùng khi người dùng muốn thêm hoặc ghi "
                "việc cần làm (kể cả tiếng Việt không dấu như 'them task...', 'tao viec...'). "
                "Trích đúng title từ câu người dùng; chỉ đặt deadline/priority/estimateMin khi "
                "người dùng có nhắc tới. Không dùng khi người dùng chỉ hỏi danh sách hay tìm kiếm."
            ),
            args_model=CreateTaskArgs,
            risk="low",
            runs_on="server",
            call=_call_create_task,
            summarize=_summarize_create_task,
        )
    )

    return registry


async def _call_update_task(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(UpdateTaskArgs, args)
    payload = parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload.pop("taskId", None)
    return await ctx.be.patch(
        f"/api/tasks/{parsed.taskId}",
        payload,
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="update_task",
    )


async def _call_set_priority(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(SetPriorityArgs, args)
    return await ctx.be.patch(
        f"/api/tasks/{parsed.taskId}",
        {"priority": parsed.priority},
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="set_priority",
    )


async def _call_complete_task(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(CompleteTaskArgs, args)
    return await ctx.be.post(
        f"/api/tasks/{parsed.taskId}/complete",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="complete_task",
        write=True,
    )


async def _call_delete_task(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(DeleteTaskArgs, args)
    return await ctx.be.delete(
        f"/api/tasks/{parsed.taskId}",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="delete_task",
    )


async def _call_reprioritize_tasks(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(ReprioritizeTasksArgs, args)
    return await ctx.be.post(
        "/api/tasks/batch-priority",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="reprioritize_tasks",
        write=True,
    )


async def _call_create_reminder(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(CreateReminderArgs, args)
    return await ctx.be.post(
        "/api/reminders",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="create_reminder",
        write=True,
    )


async def _call_undo_last_action(args: BaseModel, ctx: ToolContext) -> BEResponse:
    parsed = cast(UndoLastActionArgs, args)
    target_turn = ctx.last_write_turn_id or ctx.turn_id
    return await ctx.be.post(
        f"/api/actions/undo-turn/{target_turn}",
        parsed,
        jwt=ctx.jwt,
        turn_id=ctx.turn_id,
        tool_name="undo_last_action",
        write=True,
    )


def build_p0_registry() -> ToolRegistry:
    """Đăng ký đủ 12 tool P0 cho Giai đoạn 2 (QĐ-HARNESS-001, QĐ-HARNESS-006)."""
    registry = build_phase1_registry()

    registry.register(
        Tool(
            name="update_task",
            description=(
                "Cập nhật tiêu đề, mô tả, deadline, ưu tiên, ước lượng hoặc trạng thái của task "
                "đã có theo taskId. Không dùng để xoá task."
            ),
            args_model=UpdateTaskArgs,
            risk="low",
            runs_on="server",
            call=_call_update_task,
            summarize=lambda r: (
                f"Đã cập nhật task '{r.data.get('title', '')}'"
                if isinstance(r.data, dict)
                else "Đã cập nhật task"
            ),
        )
    )

    registry.register(
        Tool(
            name="set_priority",
            description=(
                "Đặt mức ưu tiên (1 = cao nhất, 4 = thấp nhất) cho một task theo taskId kèm lý do. "
                "Chỉ dùng khi đổi 1 task; đổi nhiều task dùng reprioritize_tasks."
            ),
            args_model=SetPriorityArgs,
            risk="low",
            runs_on="server",
            call=_call_set_priority,
            summarize=lambda r: (
                f"Đã đặt ưu tiên {r.data.get('priority', '')} cho '{r.data.get('title', '')}'"
                if isinstance(r.data, dict)
                else "Đã đổi ưu tiên"
            ),
        )
    )

    registry.register(
        Tool(
            name="complete_task",
            description=(
                "Đánh dấu một task đã hoàn thành theo taskId. Dùng khi người dùng nói đã làm xong, "
                "hoàn tất, check off một việc; không dùng delete_task cho việc đã xong."
            ),
            args_model=CompleteTaskArgs,
            risk="low",
            runs_on="server",
            call=_call_complete_task,
            summarize=lambda r: (
                f"Đã hoàn thành task '{r.data.get('title', '')}'"
                if isinstance(r.data, dict)
                else "Đã hoàn thành task"
            ),
        )
    )

    registry.register(
        Tool(
            name="delete_task",
            description=(
                "Xoá mềm một task theo taskId (luôn yêu cầu người dùng xác nhận). "
                "Chỉ dùng khi người dùng nói rõ xoá hoặc bỏ; khi đã làm xong dùng complete_task."
            ),
            args_model=DeleteTaskArgs,
            risk="high",
            runs_on="server",
            call=_call_delete_task,
            summarize=lambda r: "Đã xoá task",
        )
    )

    registry.register(
        Tool(
            name="reprioritize_tasks",
            description=(
                "Đổi mức ưu tiên hàng loạt cho nhiều task cùng lúc kèm lý do. "
                "Dùng khi người dùng yêu cầu sắp xếp lại ưu tiên nhiều công việc."
            ),
            args_model=ReprioritizeTasksArgs,
            risk="medium",
            runs_on="server",
            call=_call_reprioritize_tasks,
            summarize=lambda r: "Đã sắp xếp lại ưu tiên các task",
        )
    )

    registry.register(
        Tool(
            name="create_reminder",
            description=(
                "Đặt nhắc nhở kèm thông báo trên thiết bị vào thời điểm remindAt (ISO 8601 +07:00) "
                "với nội dung message. Dùng khi người dùng nói 'nhắc tôi...', 'hẹn giờ nhắc...'."
            ),
            args_model=CreateReminderArgs,
            risk="low",
            runs_on="server_client",
            call=_call_create_reminder,
            summarize=lambda r: (
                f"Đã đặt nhắc nhở '{r.data.get('message', '')}'"
                if isinstance(r.data, dict)
                else "Đã đặt nhắc nhở"
            ),
        )
    )

    registry.register(
        Tool(
            name="undo_last_action",
            description=(
                "Hoàn tác lượt thao tác ghi gần nhất khi người dùng nói 'hoàn tác', "
                "'quay lại', 'undo cái vừa rồi'."
            ),
            args_model=UndoLastActionArgs,
            risk="low",
            runs_on="server",
            call=_call_undo_last_action,
            summarize=lambda r: "Đã hoàn tác thao tác gần nhất",
        )
    )

    return registry
