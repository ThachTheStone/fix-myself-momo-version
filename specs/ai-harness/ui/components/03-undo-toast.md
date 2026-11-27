---
type: spec-component
title: "Thành phần: Dòng hành động & Hoàn tác"
id: "FSP-HARNESS-UI-CMP-UNDO"
status: draft
tags: [spec-component, ai-harness, undo, fsp]
---

# Thành phần: Dòng hành động & Hoàn tác

Tệp đích `specs/ai-harness/ui/components/03-undo-toast.md`; quy chuẩn UI: [`../README.md`](../README.md); mô-đun: [`../../modules/03-permission-undo.md`](../../modules/03-permission-undo.md); chỉ mục: [`../../index.md`](../../index.md).

## 1. Hai nơi hiện

- **Trong chat**: dòng `✓ <summary> [Hoàn tác]` dưới câu trả lời.
- **Ngoài chat** (người dùng đang ở màn danh sách khi AI chạy xong): toast đáy màn hình 6 giây cùng nội dung.

## 2. Hành vi

| Thao tác | Gọi BE | Hiển thị |
|---|---|---|
| Hoàn tác | `POST /api/actions/{actionId}/undo` | Dòng đổi thành `↺ Đã hoàn tác`; làm mới danh sách |
| 409 `UNDO_CONFLICT` | — | "Task đã đổi sau đó, không hoàn tác được" |
| 409 `ALREADY_UNDONE` | — | `↺ Đã hoàn tác` |
| Quá 10 phút | — | Ẩn nút, giữ dòng ✓ (`[INV-HARNESS-UI-01]`) |
