# Verification

Tài liệu này là source of truth cho cách bootstrap và xác minh repository. Chỉ
ghi command đã được kiểm tra từ code, manifest, CI hoặc lần chạy thực tế.

## Prerequisites

- Runtime: `{{RUNTIME}}`
- Dependency ngoài: `{{EXTERNAL_DEPENDENCIES}}`
- Environment variable bắt buộc: `{{REQUIRED_ENVIRONMENT}}`

## Bootstrap

```bash
{{BOOTSTRAP_COMMAND}}
```

## Kiểm tra nhanh

Dùng cho feedback loop trong khi sửa phạm vi nhỏ.

```bash
{{FOCUSED_CHECK_COMMAND}}
```

## Test liên quan

```bash
{{TEST_COMMAND}}
```

## Build hoặc kiểm tra đầy đủ

```bash
{{FULL_VERIFY_COMMAND}}
```

## Side effects

- Database hoặc dữ liệu: `{{DATABASE_SIDE_EFFECTS}}`
- Network hoặc service ngoài: `{{NETWORK_SIDE_EFFECTS}}`
- File hoặc generated output: `{{FILE_SIDE_EFFECTS}}`
- Thời gian chạy dự kiến: `{{EXPECTED_DURATION}}`

## Known baseline failures

Chỉ ghi failure đã được xác minh có trước thay đổi hiện tại, kèm command và
evidence. Không dùng mục này để hợp thức hóa regression mới.

- `{{BASELINE_FAILURE_OR_NONE}}`

## Khi không thể chạy verification

Báo rõ command chưa chạy, lý do cụ thể, evidence thay thế đã dùng và rủi ro còn
lại. Không ghi `pass` khi command bắt buộc chưa chạy.
