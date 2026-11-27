---
type: spec-flow
title: "Luồng: Gợi ý chủ động"
id: "FSP-HARNESS-UI-FLW-PROACTIVE"
status: draft
tags: [spec-flow, ai-harness, proactive, fsp]
---

# Luồng: Gợi ý chủ động

Tệp đích `specs/ai-harness/ui/flows/03-proactive-suggestion.md`; quy chuẩn UI: [`../README.md`](../README.md); mô-đun: [`../../modules/06-proactive.md`](../../modules/06-proactive.md); chỉ mục: [`../../index.md`](../../index.md).

## 1. Sơ đồ

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant App
    participant AI as ai-service

    App->>AI: GET /ai/events (SSE, mở khi app chạy)
    Note over AI: 07:30 — trigger morning_plan
    AI->>AI: handle_turn(source="proactive")
    AI-->>App: text "Hôm nay nên làm 3 việc…"
    AI-->>App: pending_action {kind:"diff"} (đổi ưu tiên)
    App-->>U: Thẻ gợi ý ở đầu khung chat + thông báo nhẹ
    U->>App: Duyệt
    App->>AI: POST /ai/actions/{id}/approve
    AI-->>App: tool_done [Hoàn tác]
```

## 2. Điểm FE phải làm

- Thẻ gợi ý có nhãn "Trợ lý gợi ý" để phân biệt với trả lời cho lệnh của người dùng.
- Nút **Chạy thử gợi ý buổi sáng** (tài khoản demo) gọi `POST /ai/proactive/run?trigger=morning_plan` và hiển thị như trên.
