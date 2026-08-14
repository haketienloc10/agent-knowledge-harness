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
working transcript, live child state hoặc progress polling.

## Delegation đã hoàn tất

| Repository | Agent | Route | Native session ID | Result artifact | Outcome | Verification chính |
|---|---|---|---|---|---|---|

Chỉ ghi delegation sau khi `delegate_repo_task` đã return thành công và QiQi đã
đọc `result_path`.

- `Native session ID` là ID thật do Codex/Claude trả về và chỉ dùng làm argument
  `session_id` cho RESUME thật sự của cùng native conversation.
- `Result artifact` là workspace-relative `result_path` dưới `.qiqi/runs/`; đây là
  handoff history của session và phải được đọc trước khi quyết định bước tiếp.
- Không RESUME chỉ để yêu cầu agent lặp lại/cung cấp report đã có trong artifact.
- Không ghi Herdr pane/workspace, process state, transcript hoặc progress.

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
