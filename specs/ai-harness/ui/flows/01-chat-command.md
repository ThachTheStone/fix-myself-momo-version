---
type: spec-flow
title: "Luồng: Ra lệnh bằng chat hoặc giọng nói"
id: "FSP-HARNESS-UI-FLW-CHAT"
status: draft
tags: [spec-flow, ai-harness, chat, voice, fsp]
---

# Luồng: Ra lệnh bằng chat hoặc giọng nói

Tệp đích `specs/ai-harness/ui/flows/01-chat-command.md`; quy chuẩn UI: [`../README.md`](../README.md); đặc tả khung: [`../../05-spec.md`](../../05-spec.md) mục 3.1–3.3; chỉ mục: [`../../index.md`](../../index.md).

## 1. Sơ đồ

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant App
    participant AI as ai-service
    participant BE

    U->>App: Nói "nhắc tôi gọi mẹ lúc 8 giờ tối nay"
    App->>App: STT vi-VN trên máy → điền ô nhập
    U->>App: Sửa (nếu cần), bấm Gửi
    App->>AI: POST /ai/chat {message, inputMode:"voice"}
    AI->>BE: POST /api/reminders (JWT, Idempotency-Key)
    BE-->>AI: {data, actionId}
    AI-->>App: tool_done "Đã đặt nhắc 20:00 hôm nay"
    AI-->>App: client_action schedule_notification {at: 20:00}
    App->>App: Đặt thông báo cục bộ
    AI-->>App: text + done
    opt Người dùng bấm Hoàn tác
        App->>BE: POST /api/actions/{actionId}/undo
        App->>App: Huỷ thông báo cục bộ theo reminderId
    end
```

## 2. Điểm FE phải làm

- Hoàn tác `create_reminder` ⇒ huỷ thông báo cục bộ có cùng `reminderId`.
- Mất mạng khi đang stream ⇒ hiện "Mất kết nối", nút Thử lại gửi lại **cùng nội dung**; AI service chống trùng nhờ `Idempotency-Key`.
