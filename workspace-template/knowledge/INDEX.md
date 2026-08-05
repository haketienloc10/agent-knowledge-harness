# Knowledge Index

Đây là điểm vào của thư viện tri thức workspace. Agent phải tìm tài liệu từ
index này thay vì quét toàn bộ thư mục.

## Registry

| ID | Loại | Phạm vi/repository | Trạng thái | Cập nhật | Tài liệu |
|---|---|---|---|---|---|
| `example-contract` | contract | `producer → consumer` | proposed | YYYY-MM-DD | `contracts/example.md` |

Xóa dòng ví dụ khi thêm tài liệu thật đầu tiên.

## Trạng thái

- `proposed`: đang chờ xác minh hoặc duyệt.
- `verified`: có evidence và được phép dùng làm context.
- `superseded`: đã bị thay thế; phải liên kết đến tài liệu mới.
- `deprecated`: còn tồn tại để tương thích nhưng không dùng cho thay đổi mới.

## Quy tắc cập nhật

- Mỗi durable document phải có đúng một dòng trong registry.
- `Phạm vi/repository` phải đủ cụ thể để agent biết khi nào cần đọc.
- Không đưa task document hoặc proposal chưa được duyệt vào registry durable.
- Khi thay thế tài liệu, không xóa lịch sử im lặng; đổi trạng thái và liên kết đến
  nguồn mới.
