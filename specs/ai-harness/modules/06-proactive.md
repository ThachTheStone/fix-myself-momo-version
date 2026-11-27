---
type: spec-module
title: "Mô-đun: Gợi ý Chủ động"
id: "FSP-HARNESS-MOD-PROACTIVE"
status: draft
tags: [spec-module, ai-harness, proactive, scheduler, fsp]
---

# Mô-đun: Gợi ý Chủ động

Tệp đích `specs/ai-harness/modules/06-proactive.md`; đặc tả khung: [`../05-spec.md`](../05-spec.md) mục 3.7; sổ quyết định: [`../03-decisions.md`](../03-decisions.md); chỉ mục: [`../index.md`](../index.md). Mã: `ai-service/app/proactive/`.

## 1. Trigger

| Trigger | Lịch | Điều kiện chạy | Prompt cho agent |
|---|---|---|---|
| `morning_plan` | `morningPlanTime` của người dùng (mặc định 07:30) | Có ≥ 1 task chưa xong | "Đề xuất 3 việc quan trọng nhất hôm nay và thứ tự làm; có thể đề xuất đổi ưu tiên." |
| `overdue` | Mỗi 30 phút | Có task quá hạn chưa được gợi ý trong 24 giờ | "Task X đã trễ. Đề xuất dời hạn hợp lý hoặc tách nhỏ." |
| `due_soon` | Mỗi 30 phút | Task hạn < 24 giờ, chưa gợi ý | "Nhắc và đề xuất mở focus session cho task X." |

## 2. Luật

- Chạy `handle_turn(user, prompt, source="proactive")` ⇒ mọi tool ghi thành `pending_action` (`[INV-HARNESS-03]`).
- Tối đa `PROACTIVE_DAILY_LIMIT` = 3 lần/người/ngày; một task chỉ được nhắc 1 lần mỗi trigger mỗi 24 giờ.
- Scheduler cần danh sách người dùng + JWT: dùng **refresh token** người dùng đã cấp khi bật gợi ý, hoặc đơn giản hơn cho bản nộp — **chỉ chạy khi app đang mở** (kênh `GET /ai/events` có JWT) và nút "Chạy thử". Quyết định cuối ghi QĐ mới ngày 01/12.
- Kết quả: đẩy qua `GET /ai/events` nếu đang mở; nếu không, lưu `pending_action` và hiện ở đầu khung chat lần mở sau.

## 3. Demo cho giám khảo

`POST /ai/proactive/run?trigger=morning_plan` gắn nút **Chạy thử gợi ý buổi sáng** trong Settings của tài khoản demo; không tính vào giới hạn 3 lần/ngày.
