---
type: spec-ui
title: "AI Harness — Quy chuẩn Giao diện Trợ lý"
id: "FSP-HARNESS-UI-ROOT"
status: draft
tags: [spec-ui, ai-harness, fsp]
---

# AI Harness — Quy chuẩn Giao diện Trợ lý

Tệp đích `specs/ai-harness/ui/README.md`; đặc tả khung: [`../05-spec.md`](../05-spec.md); chỉ mục: [`../index.md`](../index.md). Chỉ quy định phần giao diện của trợ lý; màu sắc, font, khung app theo design của bạn FE.

## 1. Nguyên tắc

- **Thấy AI làm gì**: mỗi thao tác AI đã chạy hiện thành một dòng nhỏ dưới câu trả lời (biểu tượng + tóm tắt + Hoàn tác), không giấu trong đoạn văn.
- **Duyệt trong một chạm**: thẻ xác nhận có nút Duyệt nổi bật, Bỏ phụ; nội dung đủ để quyết định mà không mở màn khác.
- **Không chặn người dùng**: đang chờ AI vẫn cuộn, xem danh sách task được; dữ liệu task tự làm mới sau mỗi `tool_done`.

## 2. Bất biến giao diện

- `[INV-HARNESS-UI-01]` Mọi `tool_done` có `undoable: true` hiện nút **Hoàn tác** ít nhất 10 phút.
- `[INV-HARNESS-UI-02]` `pending_action` có `risk: high` dùng màu cảnh báo và động từ cụ thể trên nút ("Xoá 3 task", không chỉ "Duyệt").
- `[INV-HARNESS-UI-03]` Thẻ hết hạn chuyển xám, nút bị vô hiệu, ghi "Đã hết hạn".
- `[INV-HARNESS-UI-04]` Sau `tool_done`, danh sách task trên màn chính phản ánh thay đổi trong ≤ 1 giây (tải lại hoặc cập nhật cục bộ).

## 3. Danh bạ

- Thành phần: [`components/01-chat-panel.md`](components/01-chat-panel.md) · [`components/02-confirm-card.md`](components/02-confirm-card.md) · [`components/03-undo-toast.md`](components/03-undo-toast.md) · [`components/04-autonomy-settings.md`](components/04-autonomy-settings.md)
- Luồng: [`flows/01-chat-command.md`](flows/01-chat-command.md) · [`flows/02-doc-to-tree.md`](flows/02-doc-to-tree.md) · [`flows/03-proactive-suggestion.md`](flows/03-proactive-suggestion.md)
