---
type: spec-flow
title: "Luồng: Tài liệu → Cây task"
id: "FSP-HARNESS-UI-FLW-DOC"
status: draft
tags: [spec-flow, ai-harness, document, fsp]
---

# Luồng: Tài liệu → Cây task

Tệp đích `specs/ai-harness/ui/flows/02-doc-to-tree.md`; quy chuẩn UI: [`../README.md`](../README.md); mô-đun: [`../../modules/05-doc-to-task-tree.md`](../../modules/05-doc-to-task-tree.md); chỉ mục: [`../../index.md`](../../index.md).

## 1. Sơ đồ

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant App
    participant AI as ai-service
    participant BE

    U->>App: Bấm 📎, chọn srs-thanh-toan.md
    App->>AI: POST /ai/documents (multipart)
    alt Sai loại / quá 2 MB / không có chữ
        AI-->>App: 415 / 413 / 422
        App-->>U: Thông báo lỗi cụ thể
    else Hợp lệ
        AI-->>App: text "Mình chia thành 3 phần, 14 việc…"
        AI-->>App: pending_action {kind:"tree"}
        U->>App: Bỏ chọn 1 nút, bấm "Tạo 13 task"
        App->>AI: approve {editedArgs.root}
        AI->>BE: POST /api/tasks/tree
        BE-->>AI: {data, actionId}
        AI-->>App: tool_done "Đã tạo 13 task" [Hoàn tác]
    end
```

## 2. Điểm FE phải làm

- Dựng cây có checkbox từ `preview.items`; bỏ chọn nút cha ⇒ bỏ cả con.
- Hiện tổng số task và tổng giờ ước lượng cập nhật theo lựa chọn.
