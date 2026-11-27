---
type: spec-module
title: "Mô-đun: Định tuyến Model lai"
id: "FSP-HARNESS-MOD-ROUTER"
status: draft
tags: [spec-module, ai-harness, llm, litellm, ollama, fallback, fsp]
---

# Mô-đun: Định tuyến Model lai

Tệp đích `specs/ai-harness/modules/04-model-router.md`; đặc tả khung: [`../05-spec.md`](../05-spec.md) mục 3.4, 4.4; sổ quyết định: [`../03-decisions.md`](../03-decisions.md) (`QĐ-HARNESS-007`, `008`); chỉ mục: [`../index.md`](../index.md). Mã: `ai-service/app/llm/`.

## 1. Chuỗi model

| Vai | Model | Chạy ở | Việc chính |
|---|---|---|---|
| `small` (chính cho chat) | **Qwen3 8B** qua Ollama (`qwen3:8b`, bản lượng tử q4) | Dev: máy của ban AI · Prod: server GPU (Giai đoạn 5) | Lệnh ngắn: thêm/sửa/hoàn thành/tìm task, ưu tiên 1 task, nhắc nhở, hỏi lịch |
| `small` dự bị | Qwen3 14B (nếu máy đủ VRAM) hoặc bản LoRA fine-tune | Như trên | Chỉ khi 8B không qua cổng |
| `cloud` | Model **Flash/mini** giá rẻ có function calling (vd dòng Gemini Flash) | API | Tài liệu → cây task, kế hoạch buổi sáng, sắp xếp > 5 task, sinh dữ liệu fine-tune; nhận tải khi `small` lỗi/quá tải |
| `cloud_backup` | Model mini của **nhà cung cấp khác** (vd OpenAI) | API | Khi `cloud` lỗi, timeout hoặc 429 |

Tên model cloud cụ thể chốt ở `02-rfc.md` câu hỏi mở 1; tra tên và hạn mức hiện hành trên trang giá của nhà cung cấp trước khi điền `CLOUD_MODEL`.

## 2. Thành phần

- **`router.complete(msgs, tools, task_kind)`**: chọn đích theo bảng `05-spec.md` mục 3.4, gọi `litellm.acompletion`, ghi `last_target` vào `done.model`.
- **Semaphore `small`**: `asyncio.Semaphore(SMALL_MAX_CONCURRENCY)`; không lấy được ngay ⇒ đi `cloud` (không xếp hàng — giám khảo không phải chờ).
- **`health.py`**: mỗi 30 giây gọi `GET {SMALL_MODEL_BASE_URL}/models`; 2 lỗi liên tiếp ⇒ `small_down = True`; 3 lần thành công ⇒ `False`.
- **`task_kind`**: `chat` · `document` · `batch` (> 5 task) · `morning_plan` · `datagen`.

## 3. Fallback trong một lượt

1. `chat` ⇒ thử `small` (timeout `SMALL_TIMEOUT_S`).
2. Timeout, lỗi HTTP, hết slot semaphore, hoặc 2 lần tool sai schema ⇒ `force_cloud` cho phần còn lại của lượt.
3. `cloud` lỗi/429 ⇒ `cloud_backup` một lần ⇒ vẫn lỗi ⇒ SSE `error` `MODEL_UNAVAILABLE`, không ghi gì.
4. `ROUTER_MODE=small_only` ⇒ bỏ bước 2–3; việc cần cloud trả `CLOUD_DISABLED` (chỉ dùng khi dev chưa có key).

## 4. Chạy local (Giai đoạn 1)

```sh
ollama pull qwen3:8b        # xác nhận tag trên ollama.com/library/qwen3
ollama serve                # endpoint OpenAI-compatible tại http://localhost:11434/v1
# .env của ai-service:
ROUTER_MODE=small_only
SMALL_MODEL_BASE_URL=http://localhost:11434/v1
SMALL_MODEL_NAME=qwen3:8b
```

Qwen3 có chế độ "thinking": tắt cho chat (thêm `/no_think` vào system prompt hoặc tham số tương ứng của Ollama) để giảm độ trễ; ghi cách đã dùng vào `ai-service/CLAUDE.md` mục 6.

## 5. Cổng ngày 29/11 (`QĐ-HARNESS-008`)

| Độ chọn đúng tool của `small` (60 câu đơn giản) | Hành động |
|---|---|
| ≥ 90% | Giữ `hybrid`, `small` làm chính cho chat |
| 75–90% | Fine-tune LoRA ngày 30/11; đo lại; < 90% ⇒ chat sang `cloud` |
| < 75% | Thử Qwen3 14B; vẫn < 90% ⇒ `cloud_only` |

Ghi kết quả bằng QĐ mới trong `03-decisions.md`, kèm `eval/report-small.json`.

## 6. Đưa `small` lên production (Giai đoạn 5)

Giám khảo không truy cập được máy dev, nên bản nộp cần `small` trên một server có HTTPS chạy tới hết 11/12:
- **Cách A**: thuê GPU (vd 1 card 24 GB), chạy Ollama hoặc vLLM; tính chi phí 16 ngày vào `DEBUG.md` trước khi thuê.
- **Cách B**: không thuê được ⇒ prod chạy `cloud_only`; slide trình bày kiến trúc lai + số eval của `small` đo trên máy dev.

Cả hai cách, `cloud` + `cloud_backup` luôn bật trên prod để `[INV-HARNESS-10]` đứng vững.

## 7. Dữ liệu fine-tune (chỉ khi cổng yêu cầu)

- 500–1.000 cặp (tin nhắn → tool call) sinh bằng `cloud` từ ~100 mẫu câu × biến thể (không dấu, viết tắt, ngày tương đối); lọc tay.
- **Không** dùng câu trong `eval/cases.jsonl` để train.
- README khai: model gốc + giấy phép, dữ liệu tự sinh, không có dữ liệu cá nhân thật.
