# <Tên task>

## Yêu cầu người dùng

Giữ wording/constraint quan trọng từ original user request.

## Kết quả mong muốn

## Phạm vi

- Repository liên quan:
- Ngoài phạm vi:

## Bối cảnh và quyết định đã chốt

Chỉ ghi thông tin cần để tiếp tục task mà không phải điều tra lại phần đã hoàn
tất. Fact nào sẽ trở thành required premise cho delegation phải có provenance rõ.

## Dependency và contract

## Tiến độ

Chỉ ghi milestone hoặc terminal outcome có giá trị qua nhiều lượt. Không ghi
working transcript, live child state hoặc progress polling.

## Delegation đã hoàn tất

| Repository | Agent | Route | Native session ID | Turn ID | State | Verification chính |
|---|---|---|---|---|---|---|

Chỉ ghi delegation sau khi `delegate_repo_task` đã return thành công và QiQi đã đọc
toàn bộ `agent_response`.

- `Native session ID` là ID thật do Codex/Claude trả về và chỉ dùng làm argument
  `session_id` cho RESUME thật sự của cùng native conversation.
- `Turn ID` là audit pointer do qiqi_delegate tạo; không phải path result.
- Native `agent_response` là terminal semantic handoff nhưng không copy toàn bộ vào
  task file này. Chỉ chắt lọc durable workspace facts cần cho continuation.
- Không RESUME chỉ để yêu cầu agent lặp lại/cung cấp report đã có trong response.
- Không ghi Herdr pane/workspace, process state, transcript, screen capture hoặc
  `.qiqi/state/` database content.

Nếu chuyển sang agent khác, tạo START mới và ghi row mới; không tái sử dụng native
session ID của agent cũ.

## Handoff liên repository

Chỉ ghi **live fact/evidence** QiQi đã reconcile và còn giá trị cho downstream work.

| Từ repository | Fact/evidence + provenance cần truyền | Repository nhận | Trạng thái |
|---|---|---|---|

Không yêu cầu downstream agent tự đọc sibling source/runtime state. QiQi phải đưa
live context cần dùng trực tiếp vào `required_context`. Nếu QiQi đã dùng một Shared
Knowledge fact để quyết định semantics, fact đó cũng phải inline kèm Knowledge ID/
revision hoặc provenance phù hợp; child knowledge query không thay thế required
input.

## Blocker hoặc câu hỏi mở

## Verification evidence

## Cross-repo impact còn phải xử lý

Chỉ ghi impact còn cần downstream task, user decision hoặc workspace update. Nếu
impact đã được truyền/xử lý xong thì đánh dấu rõ để không xử lý lặp lại.

## Kết quả cuối

## Shared knowledge updates

Nếu task file tùy chọn này cần ghi audit pointer, chỉ ghi stable Knowledge MCP IDs
đã create/update hoặc persistence failure. Không copy knowledge content và không
ghi external store path.

- Knowledge IDs:
- Không có, nếu `knowledge_write(entries=[])` hoặc không có persisted change.
