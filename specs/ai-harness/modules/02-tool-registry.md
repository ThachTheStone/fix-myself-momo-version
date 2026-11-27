---
type: spec-module
title: "Mô-đun: Danh mục Tool"
id: "FSP-HARNESS-MOD-TOOLS"
status: draft
tags: [spec-module, ai-harness, tools, schema, fsp]
---

# Mô-đun: Danh mục Tool

Tệp đích `specs/ai-harness/modules/02-tool-registry.md`; đặc tả khung: [`../05-spec.md`](../05-spec.md) mục 4.3; sổ quyết định: [`../03-decisions.md`](../03-decisions.md); chỉ mục: [`../index.md`](../index.md). Mã: `ai-service/app/tools/`.

## 1. Bảng tool (17)

| Tool | Tham số chính | `risk` | Chạy ở | Ưu tiên |
|---|---|:---:|---|:---:|
| `list_tasks` | `status?, priority?, dueFrom?, dueTo?, parentId?` | read | server | P0 |
| `search_tasks` | `query` | read | server | P0 |
| `get_task` | `taskId` | read | server | P0 |
| `get_schedule` | `from, to` | read | server | P0 |
| `create_task` | `title, description?, deadline?, priority?, parentId?, estimateMin?` | low | server | P0 |
| `update_task` | `taskId` + trường cần đổi | low | server | P0 |
| `set_priority` | `taskId, priority, reason` | low | server | P0 |
| `complete_task` | `taskId` | low | server | P0 |
| `create_reminder` | `remindAt, message, taskId?` | low | server + client | P0 |
| `undo_last_action` | — | low | server | P0 |
| `reprioritize_tasks` | `items[{taskId, priority}], reason` | medium | server | P0 |
| `delete_task` | `taskId` | high | server | P0 |
| `reschedule_tasks` | `items[{taskId, deadline}], reason` | medium | server | P1 |
| `create_task_tree` | `root: TaskNode` | medium (luôn hỏi) | server | P1 |
| `start_focus_session` | `durationMin, taskId?` | low | server + client | P1 |
| `add_to_device_calendar` | `title, start, end` | medium | client | P2 |
| `update_block_rule` | `apps[], schedule` | high | server + client | P2 |

## 2. Khuôn định nghĩa một tool

```python
class CreateTaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    deadline: AwareDatetime | None = None          # validator: không ở quá khứ (QĐ-HARNESS-009)
    priority: int = Field(3, ge=1, le=4)
    parentId: UUID | None = None
    estimateMin: int | None = Field(None, ge=5, le=2400)

register(Tool(
    name="create_task",
    description=(
        "Tạo một task mới cho người dùng. Dùng khi người dùng muốn thêm việc cần làm. "
        "Ví dụ: 'thêm task nộp báo cáo thứ 6' → title='Nộp báo cáo', deadline=<thứ 6 23:59>. "
        "'việc gấp: gọi khách' → priority=1."
    ),
    args=CreateTaskArgs, risk="low", runs_on="server",
    call=lambda a, ctx: ctx.be.post("/api/tasks", a, write=True),
    summarize=lambda r: f"Đã tạo task '{r.data.title}'" + (f" · hạn {fmt(r.data.deadline)}" if r.data.deadline else ""),
))
```

Luật viết mô tả: tiếng Việt · câu đầu nói **khi nào dùng** · 1–2 ví dụ câu lệnh → tham số · nêu rõ khi **không** dùng (vd `delete_task`: "chỉ khi người dùng nói xoá/bỏ; 'xong' thì dùng `complete_task`").

## 3. Tool client

Tool `runs_on` chứa `client` phát SSE `client_action` sau khi phần server chạy xong:

| Tool | `client_action.type` | Payload |
|---|---|---|
| `create_reminder` | `schedule_notification` | `{ reminderId, at, title: "Nhắc nhở", body: message }` |
| `start_focus_session` | `start_focus` | `{ sessionId, durationMin, taskTitle? }` |
| `add_to_device_calendar` | `add_calendar_event` | `{ title, start, end }` |

App không hỗ trợ `type` nào ⇒ bỏ qua và ghi log, không báo lỗi người dùng.

## 4. Idempotency (`QĐ-HARNESS-015`)

`key = sha256(turnId + tool + json.dumps(args, sort_keys=True))`, gửi header `Idempotency-Key` cho mọi tool có `risk ≠ read`.
