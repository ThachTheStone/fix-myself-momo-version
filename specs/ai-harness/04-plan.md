---
type: plan
stage: 04
title: "AI Harness — Kế hoạch Triển khai"
id: "FSP-HARNESS-04"
status: draft
tags: [plan, ai-harness, fsp, stage-04]
---

# AI Harness — Kế hoạch Triển khai

Tệp đích `specs/ai-harness/04-plan.md`; luật phân vùng: [`../CLAUDE.md`](../CLAUDE.md). Đặc tả: [`05-spec.md`](05-spec.md). Đường dẫn tính từ gốc repo. Mốc cứng: **cổng model nhỏ tối 29/11 · P0 chạy online tối 29/11 · đóng băng 18:00 ngày 01/12 · nộp bản chính trước 20:00 ngày 02/12 · 03/12 dự phòng**.

## 1. Lộ trình phân kỳ

P1 Khung + Ollama local + hợp đồng (26/11) ➜ P2 Tool P0 + Supabase + cloud fallback + deploy (27/11) ➜ P3 Quyền + hoàn tác + SSE (28/11) ➜ P4 Tài liệu, giọng nói, thông báo + cổng model nhỏ (29/11) ➜ P5 Đưa model nhỏ lên prod / fine-tune (30/11) ➜ P6 Chủ động + đóng băng (01/12) ➜ Nộp (02/12) ➜ Dự phòng (03/12).

## 2. Phân rã công việc

### Giai đoạn 1: Khung + Ollama local + hợp đồng — 26/11 (`QĐ-HARNESS-001`, `002`, `007`, `010`)
- [ ] **1.1** Họp 1 giờ với FE, BE: chốt `05-spec.md` mục 4.1, 4.3 và trả lời `02-rfc.md` câu hỏi mở 1, 2, 5
- [x] **1.2** Dựng FastAPI + LiteLLM, `ROUTER_MODE=small_only` với model local trên Ollama (không cần key) — `ai-service/app/main.py`, `ai-service/app/llm/router.py`, `ai-service/pyproject.toml`; cách chạy ở `modules/04-model-router.md` mục 4
- [x] **1.3** Vòng lặp agent với 4 tool đọc + `create_task` trên BE giả — `ai-service/app/agent/loop.py`, `ai-service/app/tools/`, `ai-service/tests/fake_be.py`
- [x] **1.4** Endpoint giả `POST /ai/chat?mock=1` phát đủ 6 loại SSE cho FE dựng giao diện — `ai-service/app/api/chat.py`
- [x] **1.5** 40 câu eval đầu — `ai-service/eval/cases.jsonl`, `ai-service/eval/run_eval.py`

### Giai đoạn 2: Tool P0 + Supabase + cloud fallback + deploy — 27/11 (`QĐ-HARNESS-003`, `007`, `009`, `015`, `017`)
- [x] **2.1** Đủ tool P0 nối BE thật (forward JWT, `X-Turn-Id`, `Idempotency-Key`) — `ai-service/app/tools/server_tools.py`, `ai-service/app/tools/be_client.py`
- [x] **2.2** Schema Pydantic + validator ngày giờ + tự sửa 2 lần — `ai-service/app/tools/schemas.py`, `ai-service/app/agent/prompt.py`
- [x] **2.3** Schema `ai` trên Supabase + role `ai_service` (chỉ schema `ai`) — `ai-service/migrations/001_ai_schema.sql`, `ai-service/app/store/`
- [x] **2.4** Lấy key `cloud` + `cloud_backup`, bật `ROUTER_MODE=hybrid`, semaphore + fallback — `ai-service/app/llm/router.py`, `ai-service/tests/test_router.py`
- [ ] **2.5** Deploy AI service lên server công khai, HTTPS (đã có `ai-service/Dockerfile`, `DEBUG.md`; chờ đẩy lên server công khai)
- [x] **2.6** Đủ 80 câu eval, chạy lần 1 cho `small` và `cloud`, ghi số vào `06-verification.md` mục 2
- [ ] **2.7** Trưởng nhóm gửi câu hỏi làm rõ cho BTC trước 23:59

### Giai đoạn 3: Quyền + hoàn tác + stream — 28/11 (`QĐ-HARNESS-004`, `005`, `006`, `014`)
- [x] **3.1** Ma trận quyền + `pending_action` + approve/reject — `ai-service/app/policy/permission.py`, `ai-service/app/policy/pending.py`, `ai-service/app/api/actions.py`
- [x] **3.2** Tool `undo_last_action`; phối hợp BE `action_log` + undo (đã nối hợp đồng + `tests/fake_be.py`, chờ kiểm với BE thật)
- [x] **3.3** Giới hạn quota, số bước, cắt ngữ cảnh — `ai-service/app/agent/context.py`
- [ ] **3.4** Ghép với màn chat của FE trên 1 nền tảng
- [x] **3.5** Unit test policy — `ai-service/tests/test_permission.py`, `ai-service/tests/test_pending.py`

### Giai đoạn 4: Tài liệu, giọng nói, thông báo — 29/11 (`QĐ-HARNESS-011`, `012`)
- [ ] **4.1** `POST /ai/documents` + planner cây task — `ai-service/app/docs/extract.py`, `ai-service/app/docs/planner.py`
- [ ] **4.2** `client_action` `schedule_notification`; hỗ trợ FE STT
- [ ] **4.3** Tối: chạy eval `small`, áp cổng `QĐ-HARNESS-008`, ghi kết quả bằng QĐ mới trong `03-decisions.md`
- [ ] **4.4** **Mốc: P0 chạy online trên iOS, Android, Windows (+ web nếu có)**

### Giai đoạn 5: Model nhỏ lên prod — 30/11 (`QĐ-HARNESS-007`, `008`)
- [ ] **5.1** Theo kết quả cổng: thuê GPU + Ollama/vLLM + health check (cách A), hoặc giữ `cloud_only` trên prod (cách B) — `modules/04-model-router.md` mục 6, `ai-service/app/llm/health.py`
- [ ] **5.2** Fine-tune LoRA **chỉ khi** cổng yêu cầu; đo lại
- [ ] **5.3** Test chịu tải: 10 lượt chat đồng thời ⇒ vượt `SMALL_MAX_CONCURRENCY` sang `cloud`, không lỗi; tắt GPU giữa lượt ⇒ vẫn trả lời

### Giai đoạn 6: Chủ động + đóng băng — 01/12 (`QĐ-HARNESS-013`)
- [ ] **6.1** Sáng: scheduler 3 trigger + `POST /ai/proactive/run` — `ai-service/app/proactive/`
- [ ] **6.2** `start_focus_session` + `client_action` `start_focus`
- [ ] **6.3** **18:00 đóng băng tính năng.** Tối: cả đội test chéo theo `06-verification.md` mục 3; seed 3 tài khoản demo

### Nộp — 02/12
- [ ] **7.1** Sáng: sửa lỗi từ buổi test; README phần AI (model + giấy phép, nguồn dữ liệu giả lập, công cụ AI đã dùng, **Tài sản có sẵn**)
- [ ] **7.2** Chiều: video 3 phút, slide 10 trang, PDF hướng dẫn 1 trang từ [`07-guide.md`](07-guide.md)
- [ ] **7.3** **Nộp bản chính trước 20:00**

### Dự phòng — 03/12
- [ ] **8.1** Test lại bản đã nộp bằng tài khoản demo trên 3 nền tảng; chỉ sửa lỗi nặng; có sửa ⇒ nộp lại trọn bộ trước 20:00. Sau 23:59 không động vào code hay server.

## 3. Rủi ro & điểm chặn

| Rủi ro | Mức | Dự phòng |
|---|:---:|---|
| Giám khảo không cài được app iOS | Cao | Bản web (Blazor) nếu FE kịp; tối thiểu APK + bản Windows tải được; hỏi BTC |
| BE chưa có `parentId`, xoá mềm, `action_log` tới 28/11 | Cao | Ban AI chạy trên BE giả; nếu trễ thì `undo` P0 chỉ cho `create_task`/`update_task` |
| Model nhỏ < 75% đúng tool | TB | Thử 14B; không đạt ⇒ `cloud_only`, không ảnh hưởng bản nộp |
| Máy dev không chạy nổi Qwen3 8B | TB | Dùng bản lượng tử nhỏ hơn hoặc Qwen3 4B để dev; đo eval trên server GPU |
| Supabase free tier tạm dừng project khi không dùng | TB | Ping DB định kỳ hoặc nâng gói trong thời gian 27/11–11/12; kiểm hạn mức trên trang Supabase |
| Hết quota / key bị khoá | TB | Key dự phòng, ngưỡng chi tiêu, giới hạn 60 tin/ngày |
| GPU hết tiền trước 11/12 | TB | Tính chi phí 16 ngày trước khi thuê; health check chuyển cloud |
| Lỗi phát hiện sát giờ | TB | Nộp 02/12, 03/12 dự phòng |

## 4. Bảng Giai đoạn (mở rộng WEC)

| Giai đoạn | R | UI | State | Độ khó | Estimate | Trạng thái |
|---|---|:---:|:---:|:---:|---|---|
| P1 Khung + hợp đồng | R1, R9 | không | không | 2 | 7 giờ | chưa làm |
| P2 Tool P0 + deploy | R1, R2, R11 | không | không | 3 | 8 giờ | chưa làm |
| P3 Quyền + hoàn tác | R4, R5, R11 | có | có | 4 | 8 giờ | chưa làm |
| P4 Tài liệu, giọng nói, thông báo | R3, R6, R7 | có | không | 3 | 8 giờ | chưa làm |
| P5 Model nhỏ lên prod | R10 | không | có | 3 | 6 giờ | chưa làm |
| P6 Chủ động + đóng băng | R8 | có | không | 3 | 6 giờ | chưa làm |
