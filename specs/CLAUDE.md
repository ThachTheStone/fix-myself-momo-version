---
type: policy
title: "specs/CLAUDE.md — Đặc tả tính năng Trợ lý AI cá nhân"
id: "POLICY-SPECS-ASSISTANT"
status: active
tags: [policy, specs, fsp]
---

# specs/ — Đặc tả tính năng

Gói `specs/<slug>/` của dự án — gói có `status` khác `draft` là **luật tối thượng**, tuân tuyệt đối; đổi chỉ khi 👤 duyệt (`wec/rules/spec-authority.md`). Theo luật FSP: [`../wec/templates/spec-package/FSP-RULES.md`](../wec/templates/spec-package/FSP-RULES.md).

| Gói | Chủ | Trạng thái |
|---|---|---|
| [`ai-harness/`](ai-harness/README.md) | Ban AI | draft |
| `task-core/` (đề xuất) | Ban BE | chưa tạo |
| `app-shell/` (đề xuất) | Ban FE | chưa tạo |

Luật riêng của `specs/` dự án này:
- Gói được thêm `modules/`, `ui/`, `07-guide.md`; giữ `05-spec.md` ≤ ~300 dòng.
- Thay đổi hợp đồng ở `ai-harness/05-spec.md` mục 4 phải báo cả ba ban trước khi sửa code.

@../wec/templates/spec-package/FSP-RULES.md
