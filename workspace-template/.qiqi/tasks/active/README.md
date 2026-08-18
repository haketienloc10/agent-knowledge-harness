# Active Tasks

Thư mục này hiện **không thuộc workflow bắt buộc của QiQi**.

QiQi không cần tạo task file trước investigation, implementation, verification hoặc
delegation. Native `session_id`, `result_path` và terminal result artifact là đủ cho
normal execution/continuation flow.

Chỉ dùng thư mục này nếu một workspace cụ thể chủ động bổ sung một cơ chế task-state
riêng ngoài contract mặc định của template. Không được xem sự tồn tại của file dưới
`active/` là prerequisite để START, RESUME, reconcile hoặc hoàn tất user task.
