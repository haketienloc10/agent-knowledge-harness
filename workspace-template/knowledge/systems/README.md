# Systems Knowledge

Thư mục này mô tả hành vi hoặc luồng cần góc nhìn từ nhiều repository. Không
chép kiến trúc nội bộ của từng repo vào đây.

Mỗi tài liệu nên có cấu trúc:

```markdown
---
id: system-<name>
status: verified
repos:
  - producer
  - consumer
updated: YYYY-MM-DD
---

# <Tên luồng>

## Mục đích

## Luồng và ownership

## Điểm tích hợp

## Ràng buộc

## Evidence

## Liên kết đến tài liệu repo-local
```

Chỉ tạo tài liệu khi `SYSTEM_MAP.md` không đủ chi tiết để agent thực hiện một
loại task cross-repo lặp lại.
