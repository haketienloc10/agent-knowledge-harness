# Model Routing cho QiQi

Tệp này là policy để QiQi **chọn route**. Chi tiết machine-readable về agent,
model, START/RESUME argv và native flags nằm trong
`instructions/agent-routing.yaml`.

QiQi không tự ghép executable, model ID hoặc CLI flags. Khi cần thay agent/model
hoặc flag, sửa route registry rồi giữ tên route ổn định nếu semantics vẫn phù
hợp.

## Profiles

Một route có thể dùng Codex, Claude Code hoặc agent adapter khác được MCP hỗ trợ.

| Profile | Route | Dùng khi | Evidence khả dụng |
|---|---|---|---|
| `fast` | `claude-haiku` | Task cơ học, phạm vi nhỏ, yêu cầu rõ, verification trực tiếp. | Dùng Claude Code model `haiku`. |
| `balanced` | `claude-balanced` | Implementation thông thường, bug vừa phải, test hoặc tài liệu kỹ thuật. | Dùng Claude Code model `sonnet` với `--effort medium`. |
| `deep` | `claude-deep` | Kiến trúc, migration, contract phức tạp hoặc bug khó. | Dùng Claude Code model `sonnet` với `--effort high` và `--permission-mode auto`. |
| `verifier` | `claude-verifier` | Review độc lập, đối chiếu spec, rủi ro và chất lượng evidence. | Dùng Claude Code model `sonnet` với `--effort xhigh`. |

## Quy tắc Chọn

1. Xác định loại task và mức rủi ro.
2. Chọn profile thấp nhất vẫn đủ tin cậy.
3. Resolve `Route` từ bảng trên.
4. Truyền đúng tên route vào `delegate_repo_task`.
5. Nếu START mới, bỏ `session_id`.
6. Nếu tiếp tục native conversation, truyền `session_id` đã được terminal result
   trước trả về và chọn route của **cùng agent**. Có thể đổi model/flags trong
   cùng agent nếu CLI đó hỗ trợ resume với config mới.
7. Muốn chuyển agent, START session mới và truyền context cần thiết; không dùng
   native session ID của agent khác.
8. Không truyền raw CLI arguments, executable, model ID hoặc permission mode qua
   prompt/tool arguments; các giá trị đó thuộc `agent-routing.yaml`.

Không đổi route chỉ vì thiếu dependency, quyền truy cập, environment failure hoặc
product requirement chưa rõ.

## Agent Routing Registry

`instructions/agent-routing.yaml` là source of truth thực thi. Mỗi `agent` định
nghĩa:

- executable;
- adapter (`codex` hoặc `claude` ở phiên bản hiện tại);
- prompt transport;
- `start_args`;
- `resume_args` có `{session_id}`.

Mỗi `route` định nghĩa:

- agent;
- model;
- route-specific `args`.

`{route_args}` trong agent argv template là vị trí MCP chèn flags của route.
Các placeholder runtime khác được MCP sở hữu: `{model}`, `{session_id}`,
`{schema_path}`, `{result_path}`.

Không dùng shell interpolation; MCP build argv trực tiếp và không chạy
`shell=True`.

Flag phụ thuộc model phải nằm ở route tương ứng. Ví dụ Claude model không hỗ trợ
`--permission-mode auto` dùng route không có flag đó; model đã xác nhận hỗ trợ có
thể dùng route thêm flag trong `args`.

## Resume

Native session ID được giữ nguyên, không bọc bằng continuation token:

- Codex: thread/session ID lấy từ JSON event của `codex exec --json`;
- Claude Code: `session_id` lấy từ `--output-format json`.

MCP chỉ coi resume thành công khi invocation trả lại đúng native session ID đã
yêu cầu. Nếu CLI fallback sang session mới hoặc không tìm thấy session, tool phải
fail thay vì âm thầm coi là resume thành công.

Không chạy đồng thời hai RESUME dùng cùng native `session_id`.

## Concurrency không thuộc Model Routing

Route chỉ trả lời **dùng agent/model/flags nào**. Route không quyết định task có
được chạy đồng thời hay không.

QiQi có thể đặt các task vào cùng delegation wave khi chúng:

- thuộc các resolved Git root khác nhau;
- không phụ thuộc output/decision chưa có của nhau;
- không cùng thao tác shared mutable resource;
- không dùng cùng native `session_id`.

Trong cùng `qiqi_delegate` server process, MCP hard-reject concurrent calls trên
cùng resolved Git root hoặc cùng native session. Khi dependency/conflict không rõ,
QiQi chạy tuần tự.

Trong lúc một delegation wave đang in-flight, QiQi áp dụng **Delegation Silence**:
không phát user-visible progress commentary và không poll trạng thái child.
