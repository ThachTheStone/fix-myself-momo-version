---
type: index
title: "Feature Index: AI Harness — Tay chân của Trợ lý AI cá nhân"
id: "FSP-HARNESS-INDEX"
status: draft
tags: [spec-index, ai-harness, fsp, modules]
---

# Feature Index: AI Harness — Tay chân của Trợ lý AI cá nhân

Tệp đích `specs/ai-harness/index.md`; luật phân vùng: [`../CLAUDE.md`](../CLAUDE.md). Tài liệu ý đồ: [`README.md`](README.md) (cập nhật: 2026-11-26).

## 1. Tiến độ 6 chặng

| Chặng | Tệp | Trạng thái | Mục tiêu |
|:---:|---|:---:|---|
| 1 | [`01-research.md`](01-research.md) | draft | Ràng buộc cuộc thi, hiện trạng repo, tool calling, model nhỏ vs cloud, rủi ro |
| 2 | [`02-rfc.md`](02-rfc.md) | draft | Thao tác qua tool hay UI · nơi đặt AI service · model · mức tự chủ · câu hỏi mở |
| 3 | [`03-decisions.md`](03-decisions.md) | draft | `QĐ-HARNESS-001` … `017` |
| 4 | [`04-plan.md`](04-plan.md) | draft | 6 giai đoạn 26/11 → 02/12 (model nhỏ local trước), ngày 03/12 dự phòng |
| 5 | [`05-spec.md`](05-spec.md) | draft | R1–R10, 11 bất biến, luồng agent, hợp đồng SSE/REST/tool |
| 6 | [`06-verification.md`](06-verification.md) | draft | DoD, bộ eval 80 câu, test scoped, kịch bản giám khảo |
| 7 | [`07-guide.md`](07-guide.md) | draft | Hướng dẫn dùng thử 1 trang cho giám khảo (nguồn cho PDF nộp bài) |

## 2. Mô-đun chuyên sâu (`modules/`)

| Tệp | Quyết định neo | Trạng thái | Nhiệm vụ |
|---|:---:|:---:|---|
| [`modules/01-agent-loop.md`](modules/01-agent-loop.md) | `QĐ-HARNESS-001`, `010`, `014` | draft | Vòng lặp agent, ngữ cảnh gửi model, sự kiện SSE, giới hạn bước |
| [`modules/02-tool-registry.md`](modules/02-tool-registry.md) | `QĐ-HARNESS-001`, `009`, `015` | draft | 17 tool: schema, mô tả, rủi ro, nơi chạy, ánh xạ route BE |
| [`modules/03-permission-undo.md`](modules/03-permission-undo.md) | `QĐ-HARNESS-004`, `005`, `006` | draft | Ma trận quyền, `pending_action`, `action_log`, hoàn tác |
| [`modules/04-model-router.md`](modules/04-model-router.md) | `QĐ-HARNESS-007`, `008` | draft | Chuỗi Qwen3 8B (Ollama) → cloud → cloud dự phòng, semaphore, health check, cổng fine-tune |
| [`modules/05-doc-to-task-tree.md`](modules/05-doc-to-task-tree.md) | `QĐ-HARNESS-012` | draft | Tài liệu → cây task, chống prompt injection |
| [`modules/06-proactive.md`](modules/06-proactive.md) | `QĐ-HARNESS-013` | draft | Gợi ý buổi sáng, trễ deadline, deadline < 24 giờ |

## 3. Giao diện (`ui/`)

| Phân loại | Tệp | Nội dung |
|---|---|---|
| Điều phối | [`ui/README.md`](ui/README.md) | Nguyên tắc hiển thị hành động của AI, bất biến UI |
| Thành phần | [`ui/components/01-chat-panel.md`](ui/components/01-chat-panel.md) | Khung chat stream, dòng "đã làm gì", nút mic, upload |
| Thành phần | [`ui/components/02-confirm-card.md`](ui/components/02-confirm-card.md) | Thẻ xác nhận Duyệt / Sửa / Bỏ, xem trước cây task |
| Thành phần | [`ui/components/03-undo-toast.md`](ui/components/03-undo-toast.md) | Thông báo nhỏ kèm Hoàn tác |
| Thành phần | [`ui/components/04-autonomy-settings.md`](ui/components/04-autonomy-settings.md) | Chọn 1 trong 3 chế độ tự chủ, giờ gợi ý buổi sáng |
| Luồng | [`ui/flows/01-chat-command.md`](ui/flows/01-chat-command.md) | Gõ/nói lệnh → tool → kết quả → hoàn tác |
| Luồng | [`ui/flows/02-doc-to-tree.md`](ui/flows/02-doc-to-tree.md) | Upload tài liệu → xem trước cây → duyệt |
| Luồng | [`ui/flows/03-proactive-suggestion.md`](ui/flows/03-proactive-suggestion.md) | Gợi ý chủ động → thẻ xác nhận |

## 4. Điều hướng

- Sổ `QĐ-HARNESS-xxx`: [`03-decisions.md`](03-decisions.md)
- [`README.md`](README.md) · [`../CLAUDE.md`](../CLAUDE.md)

## 5. Cổng (mở rộng WEC)

| Cổng | Ngày | Người duyệt | Kết quả | Bằng chứng |
|---|---|---|---|---|
| Cổng 2 BA (R1–R10) | 2026-11-26 | 👤 Trưởng ban AI | chờ duyệt | `05-spec.md` mục *Yêu cầu* |
| Cổng 5 Task Contract | — | 👤 cả đội | chưa tới | — |

## 6. Sai lệch quy trình (mở rộng WEC)

| Bước bỏ qua | Ai cho phép | Nợ |
|---|---|---|
| Pha 3a UX chỉ viết đặc tả thành phần, không vẽ mockup | 👤 Trưởng ban AI (hạn chót 02/12) | FE tự dựng giao diện theo `ui/` |
| Pha 9 UAT và Pha 10 Release gộp vào ngày nộp bài | 👤 Trưởng ban AI | Kịch bản giám khảo ở `06-verification.md` mục 3 thay UAT |
