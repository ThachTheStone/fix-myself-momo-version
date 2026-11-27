---
type: spec-module
title: "Mô-đun: Quyền, Duyệt & Hoàn tác"
id: "FSP-HARNESS-MOD-POLICY"
status: draft
tags: [spec-module, ai-harness, permission, undo, fsp]
---

# Mô-đun: Quyền, Duyệt & Hoàn tác

Tệp đích `specs/ai-harness/modules/03-permission-undo.md`; đặc tả khung: [`../05-spec.md`](../05-spec.md) mục 3.2, 3.3, 4.5; sổ quyết định: [`../03-decisions.md`](../03-decisions.md); chỉ mục: [`../index.md`](../index.md). Mã: `ai-service/app/policy/`; phía BE: bảng `action_log`.

## 1. `permission.check()`

```python
def check(tool: Tool, mode: Mode, source: Source) -> Literal["run", "ask"]:
    if tool.risk == "read": return "run"
    if source == "proactive": return "ask"            # INV-HARNESS-03
    if tool.name == "create_task_tree": return "ask"  # QĐ-HARNESS-012
    if tool.risk == "high": return "ask"              # INV-HARNESS-02
    if mode == "ask_always": return "ask"
    if mode == "by_risk": return "ask" if tool.risk == "medium" else "run"
    return "run"                                      # auto
```

## 2. Vòng đời `pending_action`

| Từ | Sự kiện | Tới | Ghi |
|---|---|---|---|
| — | `check()` trả `ask` | `pending` | `expiresAt = now + PENDING_TTL_MIN` |
| `pending` | `approve` trong hạn, đúng user | `approved` | Chạy tool với `turnId` gốc, `editedArgs` (nếu có) phải qua lại validator |
| `pending` | `reject` | `rejected` | 204 |
| `pending` | quá `expiresAt` | `expired` | Lần approve sau trả 410 |
| `approved`/`rejected`/`expired` | `approve` lần nữa | (giữ) | 404 `PENDING_NOT_FOUND` |

Chuyển `pending → approved` bằng `UPDATE … WHERE status='pending'` để hai lần bấm Duyệt chỉ một lần chạy.

## 3. Preview

| Tool | `preview.kind` | `items` |
|---|---|---|
| `delete_task` | `list` | `[{ title, deadline, childCount }]` |
| `reprioritize_tasks`, `reschedule_tasks` | `diff` | `[{ title, field, from, to }]` |
| `create_task_tree` | `tree` | `TaskNode` |
| tool `low` ở `ask_always` | `list` | `[{ label: summary dự kiến }]` |

Preview cần dữ liệu hiện tại (vd tên task) ⇒ AI service gọi tool đọc trước khi tạo pending.

## 4. Hoàn tác (`QĐ-HARNESS-006`)

- BE ghi `action_log` trong cùng transaction với thay đổi; `before` = ảnh chụp các trường bị đổi (hoặc `null` với tạo mới), `after` = sau khi đổi.
- Undo `create` ⇒ xoá mềm bản ghi tạo ra · undo `update`/`batch` ⇒ ghi lại `before` · undo `delete` ⇒ bỏ `deletedAt` (cả con).
- Từ chối khi bất kỳ bản ghi nào có `updatedAt > action.createdAt` ⇒ 409 `UNDO_CONFLICT`; đã undo ⇒ 409 `ALREADY_UNDONE`.
- Nút Hoàn tác trên app sống 10 phút sau `tool_done`; sau đó vẫn hoàn tác được bằng lệnh chat "hoàn tác…".
