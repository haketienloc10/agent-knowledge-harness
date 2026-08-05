# Knowledge Index

Đây là điểm vào của thư viện tri thức workspace. Agent phải tìm tài liệu từ
index này thay vì quét toàn bộ thư mục.

Index chỉ chứa durable knowledge đã được promote. Phát hiện chưa xác minh nằm ở
`knowledge/proposals/` và chưa được dùng như context đã xác nhận.

## Registry

| ID | Loại | Phạm vi/repository | Trạng thái | Cập nhật | Tài liệu |
|---|---|---|---|---|---|
| `example-contract` | contract | `producer → consumer` | verified | YYYY-MM-DD | `contracts/example.md` |

Xóa dòng ví dụ khi thêm tài liệu thật đầu tiên.

## Trạng thái

- `verified`: có evidence và được phép dùng làm context.
- `superseded`: đã bị thay thế; phải liên kết đến tài liệu mới.
- `deprecated`: còn tồn tại để tương thích nhưng không dùng cho thay đổi mới.

## Quy tắc cập nhật

- Mỗi durable document phải có đúng một dòng trong registry.
- `Phạm vi/repository` phải đủ cụ thể để agent biết khi nào cần đọc.
- Không đưa task document hoặc proposal chưa được duyệt vào registry.
- Khi thay thế tài liệu, không xóa lịch sử im lặng; đổi trạng thái và liên kết đến
  nguồn mới.
