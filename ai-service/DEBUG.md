# Chạy và kiểm tra AI service

Chạy các lệnh trong thư mục `ai-service`. Tạo `.env` từ `.env.example` và cấu hình `BE_BASE_URL`, `ROUTER_MODE` và model tương ứng trước khi chạy. Với Docker Desktop và BE/Ollama chạy trên máy host, dùng `http://host.docker.internal:8001` và `http://host.docker.internal:11434/v1`. Với các container chung mạng, dùng tên dịch vụ và cổng nội bộ.

```sh
docker build -t fix-myself-ai .
docker run --rm --name fix-myself-ai --env-file .env -p 127.0.0.1:8000:8000 fix-myself-ai
```

Mở terminal khác để kiểm tra.

```sh
curl -fsS http://127.0.0.1:8000/ai/health
docker logs --tail 100 fix-myself-ai
```

Trên PowerShell có thể dùng `curl.exe` hoặc `Invoke-RestMethod`. Ở chế độ `small_only`, kết quả mong đợi là `{"status":"ok","small":"up","cloud":"off"}`. Nếu `small` là `down`, kiểm tra `SMALL_MODEL_BASE_URL` từ mạng của container và tên model. Trạng thái `cloud: up` phản ánh cấu hình model và API key. Endpoint này kiểm tra tiến trình và trạng thái model, còn kết nối BE/Postgres cần được kiểm tra qua luồng sử dụng tương ứng.

Khi deploy, cấu hình các biến qua môi trường runtime, đặt reverse proxy HTTPS phía trước cổng 8000 và probe `GET /ai/health` qua URL triển khai.

## Khởi tạo Postgres

Dùng phiên quản trị có quyền tạo role và `SET ROLE ai_service` để áp dụng migration trên Supabase Postgres, ưu tiên môi trường thử nghiệm trước.

```sh
psql "$ADMIN_DATABASE_URL" -X -v ON_ERROR_STOP=1 -f migrations/001_ai_schema.sql
```

Đặt mật khẩu riêng cho `ai_service` bằng `\password ai_service` trong phiên `psql` quản trị. Role dùng `search_path = pg_catalog, ai`. Khi ứng dụng đã kết nối `PostgresStore`, cấp cho store URL dùng tài khoản Postgres `ai_service`. Bản hiện tại khởi động với `InMemoryStore`. Nếu migration báo quyền hiệu lực trên `public`, chuyển thông báo cho chủ schema BE để rà ACL, kể cả grant qua `PUBLIC`.

## Chạy eval

```sh
python eval/run_eval.py --model small --out eval/report-small.json
python eval/run_eval.py --model cloud --out eval/report-cloud.json
```

Các ca `multi_step` dùng phản hồi tool giả lập trong `tool_results`, theo thứ tự trong `expect`. Các ca `refuse_or_ask` yêu cầu phản hồi có nội dung và không gọi tool. Có thể đọc `assistantText` trong báo cáo để kiểm tra nội dung từ chối hoặc câu hỏi làm rõ.
