# AI service — ngữ cảnh làm việc

Node `ai-service/`. Cha: [`../CLAUDE.md`](../CLAUDE.md). **Đọc tệp này và spec dưới đây trước khi sửa bất kỳ tệp nào trong node.**

## 1. Node này làm gì

Vòng lặp agent của trợ lý: nhận lệnh tiếng Việt từ `app/`, gọi model qua LiteLLM, chạy tool (REST của `backend/` bằng JWT người dùng, hoặc `client_action` cho app), kiểm quyền, giữ `pending_action`, stream kết quả bằng SSE. **Không** giữ dữ liệu nghiệp vụ (task, nhắc nhở) — việc đó của `backend/`. **Không** vẽ giao diện — việc của `app/`.

## 2. Bản đồ

| Thư mục / tệp | Vai trò |
|---|---|
| `app/main.py` | FastAPI app, lifespan (httpx client, scheduler) |
| `app/api/` | Route `/ai/chat`, `/ai/actions`, `/ai/documents`, `/ai/events`, `/ai/proactive`, `/ai/health` |
| `app/agent/` | `loop.py` (vòng lặp, `run_tool`), `prompt.py`, `context.py` |
| `app/tools/` | `registry.py`, `schemas.py`, `server_tools.py`, `client_tools.py`, `be_client.py` |
| `app/policy/` | `permission.py`, `pending.py` |
| `app/llm/` | `router.py` (chuỗi small → cloud → cloud_backup, semaphore), `health.py` |
| `app/store/` | Truy cập schema `ai` trên Supabase (`asyncpg`) |
| `migrations/` | SQL tạo schema `ai` + role `ai_service` |
| `app/docs/` | `extract.py`, `planner.py` |
| `app/proactive/` | `scheduler.py`, `triggers.py` |
| `eval/` | `cases.jsonl` (80 câu), `run_eval.py`, báo cáo |
| `tests/` | pytest, `fake_be.py`, `FakeLLM` |

Node con có ngữ cảnh riêng: Không có.

## 3. Spec quản node

| Gói | Bất biến phải giữ | Quyết định chính |
|---|---|---|
| [`../specs/ai-harness/`](../specs/ai-harness/README.md) | `[INV-HARNESS-01]`..`11` — mọi tool ghi qua `permission.check()`; tool `high` luôn hỏi; proactive không tự ghi; chỉ dùng JWT người dùng | `QĐ-HARNESS-001`…`017` |

**Gói trên là luật tối thượng của node.** Trước khi đổi hành vi: đọc `05-spec.md` mục 1 + 4, `03-decisions.md` và module liên quan trong `modules/`. Chạm bất biến/hợp đồng/QĐ/R ⇒ dừng, báo 👤.

## 4. Luật riêng của node

- Chỉ `agent/loop.py::run_tool` được gọi `tool.call`; route, scheduler, approve đều đi qua nó.
- Thêm tool ⇒ thêm vào `registry.py` + schema + ít nhất 3 câu vào `eval/cases.jsonl` + cập nhật bảng `specs/ai-harness/modules/02-tool-registry.md` (qua duyệt).
- Không gọi model thật trong `tests/`; dùng `FakeLLM`.
- Không log JWT, API key, nội dung tài liệu người dùng.
- Model chính thay cho cặp Qwen3: **`qwen2.5:7b`** (Apache 2.0, thuần Instruct không `<think>`, đạt 40/40 tool và 33/40 tham số trên 40 câu Giai đoạn 1); bản nhẹ chạy nhanh trên máy dev CPU là **`qwen2.5:3b`** (`p50=3.86s`, 40/40 tool). Dev chưa có key cloud thì `ROUTER_MODE=small_only`. Prod luôn bật `cloud` + `cloud_backup`.
- Chỉ đọc/ghi schema `ai` trên Supabase bằng role `ai_service`; không bao giờ dùng `service_role` key, không query bảng `public` (`QĐ-HARNESS-017`).
- Theo gói stack `wec/stacks/python-fastapi/README.md`.

## 5. Lệnh

| Việc | Lệnh (chạy tại `ai-service/`) |
|---|---|
| Cài | `uv sync` (hoặc `pip install -e .[dev]`) |
| Model local | `ollama pull qwen3:8b && ollama serve` |
| Chạy local | `uvicorn app.main:app --reload --port 8000` |
| Tạo schema `ai` | `psql "$SUPABASE_ADMIN_URL" -f migrations/001_ai_schema.sql` (chạy một lần, bằng tài khoản admin, không lưu URL admin vào `.env` của service) |
| Endpoint giả cho FE | `POST /ai/chat?mock=1` |
| Test | `pytest tests -q` |
| Lint | `ruff check . && ruff format --check .` |
| Eval | `python eval/run_eval.py --model cloud --out eval/report-cloud.json` |

## 6. Cạm bẫy đã gặp

- **Tắt thinking của Qwen3 trên Ollama (`QĐ-HARNESS-007`)**:
  1. Qua endpoint OpenAI-compatible `/v1/chat/completions` (`openai/qwen3:8b` trên LiteLLM), Ollama không nhận top-level `think: false` như `/api/chat` và đặt `/no_think` trong `system` vẫn bị model suy luận dài. Cần tự động nối `/no_think` vào cuối tin nhắn `user` gần nhất (khi gọi `target == "small"` trong `app/llm/router.py`), đồng thời giữ `LITELLM_LOCAL_MODEL_COST_MAP=True` để tránh LiteLLM treo/lỗi SSL khi tải cost map từ GitHub; không dùng provider `ollama_chat/` vì bị `tiktoken` tải encoding qua HTTPS lỗi SSL trên máy có proxy.
  2. `qwen3:4b` bản đang cài trên máy (context 262144, `thinking levels: true`) là biến thể thinking-only, luôn sinh chuỗi suy luận kết thúc bằng `</think>` trước `<tool_call>` kể cả khi có `/no_think` (mất ~79s/lượt trên CPU i5-7500 khi có 5 tool). Chỉ `qwen3:8b` và `qwen3:1.7b` hỗ trợ `thinking levels: false, true`.
