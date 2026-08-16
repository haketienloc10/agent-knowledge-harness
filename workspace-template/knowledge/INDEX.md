# Knowledge Index

Đây là mục lục để QiQi biết **knowledge nào cần đọc cho task hiện tại**. Luôn bắt
đầu từ file này thay vì quét toàn bộ `knowledge/`.

Dựa vào `Summary`, `Khi nào cần đọc` và `Phạm vi`, chỉ mở exact document có liên
quan. Quy tắc tạo/cập nhật knowledge nằm trong `README.md`.

## Mục lục

| Tài liệu | Summary | Khi nào cần đọc | Phạm vi |
|---|---|---|---|
| `contracts/example.md` | Ví dụ contract giữa producer và consumer. | Khi task thay đổi API/event/schema tương ứng. | `producer → consumer` |

Xóa dòng ví dụ khi thêm knowledge document thật đầu tiên.

## Quy tắc cập nhật

- Mỗi durable knowledge document có đúng một dòng trong mục lục.
- `Summary` phải cho biết document chứa kết luận gì, không chỉ lặp lại tên file.
- `Khi nào cần đọc` phải giúp QiQi quyết định document có liên quan task hay không.
- `Phạm vi` phải nêu repository, boundary hoặc flow mà knowledge áp dụng.
- Khi tạo, đổi phạm vi, rename hoặc xóa knowledge document, cập nhật mục lục trong
  cùng thay đổi.
- Không đưa task context, result artifact hoặc repo-local document vào đây.
