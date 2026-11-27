---
type: spec-component
title: "Thành phần: Khung Chat Trợ lý"
id: "FSP-HARNESS-UI-CMP-CHAT"
status: draft
tags: [spec-component, ai-harness, chat, sse, fsp]
---

# Thành phần: Khung Chat Trợ lý

Tệp đích `specs/ai-harness/ui/components/01-chat-panel.md`; quy chuẩn UI: [`../README.md`](../README.md); hợp đồng SSE: [`../../05-spec.md`](../../05-spec.md) mục 4.1; chỉ mục: [`../../index.md`](../../index.md).

## 1. Bố cục

```text
+------------------------------------------------------+
| Trợ lý                                      [⚙]       |
+------------------------------------------------------+
| [Thẻ gợi ý chủ động, nếu có]                          |
|                                                      |
|                 Thêm task nộp báo cáo thứ 6 (bạn) ▸  |
| ◂ Đã thêm task cho bạn.                               |
|   ✓ Đã tạo 'Nộp báo cáo' · hạn Th 6 27/11  [Hoàn tác] |
|                                                      |
| ◂ Mình cần bạn duyệt việc này:                        |
|   [Thẻ xác nhận — xem 02-confirm-card]               |
+------------------------------------------------------+
| [📎] [ Nhập yêu cầu…                      ] [🎤] [➤]  |
+------------------------------------------------------+
```

## 2. Hành vi theo sự kiện SSE

| Sự kiện | Hiển thị |
|---|---|
| (đang gửi) | Bong bóng trợ lý với 3 chấm |
| `text` | Nối `delta` vào bong bóng hiện tại |
| `tool_done` | Thêm dòng ✓ + `summary` + nút Hoàn tác nếu `undoable`; làm mới dữ liệu task |
| `pending_action` | Chèn thẻ xác nhận |
| `client_action` | Gọi dịch vụ nền tảng (thông báo, focus); không hiện gì thêm |
| `error` | Bong bóng đỏ nhạt với `message`; `QUOTA_EXCEEDED` khoá ô nhập tới hết ngày |
| `done` | Mở lại ô nhập |

## 3. Nút

- **🎤**: giữ hoặc chạm để nói; STT `vi-VN` trên máy; điền text vào ô nhập để sửa, không tự gửi (`QĐ-HARNESS-011`). Không có quyền micro ⇒ ẩn nút.
- **📎**: chọn `.md/.txt/.pdf` ≤ 2 MB ⇒ `POST /ai/documents` (luồng [`../flows/02-doc-to-tree.md`](../flows/02-doc-to-tree.md)).
- **⚙**: mở [`04-autonomy-settings.md`](04-autonomy-settings.md).
