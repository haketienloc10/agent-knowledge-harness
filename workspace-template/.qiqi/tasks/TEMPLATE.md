# <Tên task>

## Yêu cầu

## Kết quả mong muốn

## Phạm vi

- Repository liên quan:
- Ngoài phạm vi:

## Bối cảnh và quyết định đã chốt

Chỉ ghi thông tin cần để tiếp tục task mà không phải điều tra lại phần đã hoàn
tất.

## Dependency và contract

## Tiến độ

Chỉ ghi milestone hoặc terminal outcome có giá trị qua nhiều lượt. Không ghi
working transcript hoặc progress polling.

## Delegation đã hoàn tất

| Repository | Agent | Route | Native session ID | Outcome | Verification chính |
|---|---|---|---|---|---|

Chỉ ghi delegation sau khi MCP tool đã return terminal result. `Native session
ID` là ID thật do Codex/Claude Code trả về và chỉ dùng làm argument `session_id`
cho một RESUME sau đó. Không ghi waiter, process state, transcript hoặc progress.

Nếu chuyển sang agent khác, tạo START mới và ghi row mới; không tái sử dụng native
session ID của agent cũ.

## Blocker hoặc câu hỏi mở

## Verification evidence

## Ứng viên tri thức lâu bền

Chỉ ghi phát hiện có khả năng dùng lại. Nếu cần giữ, tạo proposal trong
`knowledge/proposals/`; không chép thẳng toàn bộ task sang durable knowledge.

## Kết quả cuối

## Durable knowledge đã cập nhật

- Proposal hoặc tài liệu:
- Không có, nếu task không tạo tri thức dùng lại.
