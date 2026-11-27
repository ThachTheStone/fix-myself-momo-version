---
type: spec-component
title: "Thành phần: Thẻ Xác nhận Hành động"
id: "FSP-HARNESS-UI-CMP-CONFIRM"
status: draft
tags: [spec-component, ai-harness, pending-action, fsp]
---

# Thành phần: Thẻ Xác nhận Hành động

Tệp đích `specs/ai-harness/ui/components/02-confirm-card.md`; quy chuẩn UI: [`../README.md`](../README.md); hợp đồng: [`../../05-spec.md`](../../05-spec.md) mục 4.1–4.2; mô-đun: [`../../modules/03-permission-undo.md`](../../modules/03-permission-undo.md); chỉ mục: [`../../index.md`](../../index.md).

## 1. Ba dạng preview

```text
kind = "list" (vd delete_task, risk high)          kind = "diff" (reprioritize/reschedule)
+--------------------------------------+          +----------------------------------------+
| ⚠ Xoá 1 task                         |          | Sắp xếp lại 4 task                     |
| • Họp nhóm · hạn 28/11 · 2 task con  |          | Nộp báo cáo   ưu tiên 3 → 1            |
| [ Xoá 1 task ]  [ Bỏ ]   còn 29 phút |          | Học tiếng Anh hạn 27/11 → 29/11        |
+--------------------------------------+          | [ Duyệt ] [ Sửa ] [ Bỏ ]               |
                                                  +----------------------------------------+
kind = "tree" (create_task_tree)
+--------------------------------------------------+
| Tạo cây 14 task từ "SRS thanh toán" (~22 giờ)     |
| ☑ Module thanh toán                               |
|   ☑ Function query database (4h)                  |
|     ☑ Xác định biến… (1h)                         |
|   ☐ Function CheckExist (2h)   ← người dùng bỏ   |
| [ Tạo 13 task ]  [ Bỏ ]                           |
+--------------------------------------------------+
```

## 2. Hành vi

| Thao tác | Gọi | Kết quả trên thẻ |
|---|---|---|
| Duyệt | `POST /ai/actions/{id}/approve` (+ `editedArgs` nếu đã sửa) | Chuyển "Đã duyệt", dòng `tool_done` hiện bên dưới |
| Sửa (`diff`) | Mở hộp sửa từng dòng; lưu vào `editedArgs` | Nút Duyệt đổi chữ "Duyệt bản đã sửa" |
| Bỏ chọn nút (`tree`) | Cập nhật `editedArgs.root` | Số task trên nút thay đổi |
| Bỏ | `POST /ai/actions/{id}/reject` | "Đã bỏ", xám |
| 410 | — | "Đã hết hạn" (`[INV-HARNESS-UI-03]`) |
| 404 | — | "Đã xử lý" |

Bấm Duyệt ⇒ vô hiệu nút ngay để tránh bấm hai lần.
