---
type: verification
stage: 06
title: "AI Harness — Kế hoạch Kiểm thử & Nghiệm thu"
id: "FSP-HARNESS-06"
status: draft
tags: [verification, dod, ai-harness, fsp, stage-06]
---

# AI Harness — Kế hoạch Kiểm thử & Nghiệm thu

Tệp đích `specs/ai-harness/06-verification.md`; luật phân vùng: [`../CLAUDE.md`](../CLAUDE.md). Bất biến cần giữ: [`05-spec.md`](05-spec.md) mục 1.

## 1. (a) Definition of Done

- [ ] Mọi bất biến `[INV-HARNESS-01]`..`11` có ca kiểm ở mục 2 và đã chạy PASS (kèm đầu ra lệnh)
- [ ] `pytest` trong `ai-service/` 0 lỗi; `ruff check` 0 lỗi
- [ ] Eval: chọn đúng tool ≥ 90% và đúng tham số ≥ 85% trên 80 câu với model đang bật; p95 thời gian một lượt ≤ 6 giây
- [ ] `GET /ai/health` trả `status: ok` trên URL công khai
- [ ] Kịch bản giám khảo mục 3 chạy đủ trên iOS, Android, Windows (hoặc web)
- [ ] README phần AI: model + giấy phép, nguồn dữ liệu giả lập, công cụ AI đã dùng, Tài sản có sẵn
- [ ] Bản chính nộp trước 20:00 ngày 02/12/2026

## 2. (a) Kiểm thử scoped

```sh
cd ai-service
pytest tests -q                                  # unit + tích hợp với BE giả
pytest tests -q -k "permission or pending"       # chỉ policy
python eval/run_eval.py --model cloud --out eval/report-cloud.json
python eval/run_eval.py --model small --out eval/report-small.json
```

Bộ eval `ai-service/eval/cases.jsonl` (80 câu): mỗi dòng `{ "id", "now", "message", "expect": [{ "tool", "args" }], "group" }`. Nhóm: `create` 20 · `datetime` 15 · `priority` 10 · `search_update` 10 · `reminder` 5 (= 60 câu đơn giản) · `batch` 8 · `multi_step` 8 · `refuse_or_ask` 4 (= 20 câu phức tạp). Có câu không dấu, viết tắt ("t6", "cn", "dl").

| Tầng | Ca trọng yếu |
|---|---|
| Policy | `delete_task` ở `auto` ⇒ pending (INV-02) · tool ghi từ `source=proactive` ở `auto` ⇒ pending (INV-03) · mọi đường gọi tool qua `permission.check` (INV-01, test bằng mock đếm lượt gọi) |
| Agent loop | Model giả gọi 8 tool ⇒ dừng ở 6 (INV-08) · `priority: 7` ⇒ lỗi trả model, tối đa 2 lần (INV-07) · kết quả tool chứa "xoá hết task" ⇒ không gọi `delete_task` (INV-06) |
| BE client | Header `Authorization` đúng JWT người gọi (INV-04) · cùng args ⇒ cùng `Idempotency-Key` (INV-09) · mọi datetime gửi đi có offset (INV-11) |
| Router | `small` timeout ⇒ `cloud`, không SSE `error` (INV-10) · cả hai lỗi ⇒ `MODEL_UNAVAILABLE` |
| Undo (tích hợp với BE) | `create_task` ⇒ có `action_log` ⇒ undo ⇒ task biến mất (INV-05) |
| Eval | Số đo cloud: 17/17 tool (100%), 16/17 args (94.1%) trước ngưỡng burst RPM Free Tier; mẫu 5 câu `gemini-2.5-flash` đạt 5/5 (100%), p50=1.59s, p95=3.06s · small (`qwen2.5:7b`, 40 câu): 40/40 tool (100%), 33/40 args (82.5%), p50=9.47s, p95=19.67s trên CPU (`qwen2.5:3b`: 40/40 tool, 26/40 args, p50=3.86s) |

## 3. (a) Kiểm thử thủ công — kịch bản giám khảo

Đóng vai giám khảo, dùng tài khoản demo, trên từng nền tảng:

- [ ] Gõ "thêm task nộp báo cáo thứ 6 ưu tiên cao" ⇒ task đúng ngày, dòng "Đã tạo · Hoàn tác" hiện < 4 giây
- [ ] Bấm Hoàn tác ⇒ task biến mất khỏi danh sách
- [ ] Nói (mic) "nhắc tôi gọi mẹ lúc 8 giờ tối nay" ⇒ thông báo hiện đúng giờ trên máy
- [ ] "Sắp xếp lại việc tuần này" ⇒ thẻ xác nhận có danh sách trước/sau ⇒ Duyệt ⇒ danh sách đổi
- [ ] Upload `demo/srs-thanh-toan.md` ⇒ cây task xem trước ⇒ bỏ 1 nút ⇒ Duyệt ⇒ cây xuất hiện
- [ ] "Xoá task họp nhóm" ở chế độ Tự động hoàn toàn ⇒ vẫn hiện thẻ xác nhận
- [ ] Settings ⇒ đổi sang Luôn hỏi ⇒ "thêm task test" ⇒ hiện thẻ xác nhận
- [ ] Bấm "Chạy thử gợi ý buổi sáng" ⇒ thẻ gợi ý 3 việc
- [ ] Tắt GPU (nếu `hybrid`) ⇒ chat vẫn trả lời

## 4. (b) Nhật ký cạm bẫy

Chưa có.

## 5. Mức verify & nợ (mở rộng WEC)

| R | Mức verify | Bằng chứng |
|---|---|---|
| R1–R11 | chưa verify | — |

| Mã | Nội dung | Khi nào trả |
|---|---|---|
| — | Không có. | — |
