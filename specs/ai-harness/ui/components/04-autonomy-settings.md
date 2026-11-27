---
type: spec-component
title: "Thành phần: Cài đặt Mức tự chủ của Trợ lý"
id: "FSP-HARNESS-UI-CMP-SETTINGS"
status: draft
tags: [spec-component, ai-harness, settings, autonomy, fsp]
---

# Thành phần: Cài đặt Mức tự chủ của Trợ lý

Tệp đích `specs/ai-harness/ui/components/04-autonomy-settings.md`; quy chuẩn UI: [`../README.md`](../README.md); quyết định: `QĐ-HARNESS-004`, `QĐ-HARNESS-013` ([`../../03-decisions.md`](../../03-decisions.md)); chỉ mục: [`../../index.md`](../../index.md).

## 1. Bố cục

```text
Mức tự chủ của trợ lý
( ) Luôn hỏi trước — trợ lý đề xuất, bạn duyệt mọi thay đổi
(•) Theo mức rủi ro (khuyên dùng) — việc nhỏ làm ngay và có Hoàn tác; thay đổi nhiều task thì hỏi
( ) Tự động hoàn toàn — làm ngay mọi việc, vẫn có Hoàn tác
    Xoá dữ liệu luôn được hỏi lại ở mọi mức.

Gợi ý buổi sáng      [ 07:30 ▾ ]   [ Bật ]
[ Chạy thử gợi ý buổi sáng ]        (chỉ hiện ở tài khoản demo)
```

## 2. Hợp đồng

- Đọc/ghi `GET/PATCH /api/users/me/settings` `{ autonomyMode: "ask_always" | "by_risk" | "auto", morningPlanTime: "07:30", proactiveEnabled: true }`.
- Đổi chế độ có hiệu lực từ lượt chat kế tiếp (AI service cache 60 giây — ghi rõ "có hiệu lực sau ít giây" nếu cần).
