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

## Handoff liên repository

Chỉ ghi fact/evidence QiQi đã reconcile và còn giá trị cho downstream work.

| Từ repository | Fact/evidence cần truyền | Repository nhận | Trạng thái |
|---|---|---|---|

Không yêu cầu downstream agent tự đọc result artifact hoặc workspace knowledge;
QiQi phải đưa context cần dùng trực tiếp vào task prompt.

## Blocker hoặc câu hỏi mở

## Verification evidence

## Cross-repo impact còn phải xử lý

Chỉ ghi impact còn cần downstream task, user decision hoặc workspace update. Nếu
impact đã được truyền/lưu xong thì đánh dấu rõ để không xử lý lặp lại.

## Kết quả cuối

## Durable knowledge đã cập nhật

- `SYSTEM_MAP.md`:
- `knowledge/...`:
- `knowledge/INDEX.md`:
- Không có, nếu task không tạo tri thức cross-repo có khả năng dùng lại.
