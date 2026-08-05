# Cross-repository Decisions

Thư mục này lưu quyết định ảnh hưởng từ hai repository trở lên hoặc thay đổi
ranh giới ownership. Quyết định nội bộ chỉ thuộc một repo phải nằm trong repo đó.

Mỗi tài liệu nên có cấu trúc:

```markdown
---
id: decision-<name>
status: verified
repos:
  - <repository>
decided: YYYY-MM-DD
---

# <Tên quyết định>

## Bối cảnh

## Quyết định

## Lý do

## Hệ quả

## Phương án đã loại bỏ

## Evidence hoặc approval

## Điều kiện xem xét lại
```

Không dùng decision document để ghi log thảo luận. Chỉ giữ kết luận, lý do cần
thiết để agent không thiết kế lại cùng vấn đề khi chưa có bằng chứng mới.
