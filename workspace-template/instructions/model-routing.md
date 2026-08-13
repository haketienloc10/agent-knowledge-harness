# Model Routing cho QiQi

Tệp này là policy để QiQi **chọn route**. Chi tiết machine-readable về agent,
model, START/RESUME argv và native flags nằm trong
`instructions/agent-routing.yaml`.

QiQi không tự ghép executable, model ID hoặc CLI flags. Khi cần thay agent/model
hoặc flag, sửa route registry rồi giữ tên route ổn định nếu semantics vẫn phù
hợp.

## Profiles

Trong setup, thay placeholder bằng route thực sự tồn tại trong
`instructions/agent-routing.yaml`. Một route có thể dùng Codex, Claude Code hoặc
agent adapter khác được MCP hỗ trợ.

| Profile | Route | Dùng khi | Evidence khả dụng |
|---|---|---|---|
| `fast` | `{{FAST_ROUTE}}` | Task cơ học, phạm vi nhỏ, yêu cầu rõ, verification trực tiếp. | `{{FAST_EVIDENCE}}` |
| `balanced` | `{{BALANCED_ROUTE}}` | Implementation thông thường, bug vừa phải, test hoặc tài liệu kỹ thuật. | `{{BALANCED_EVIDENCE}}` |
| `deep` | `{{DEEP_ROUTE}}` | Kiến trúc, migration, contract phức tạp hoặc bug khó. | `{{DEEP_EVIDENCE}}` |
| `verifier` | `{{VERIFIER_ROUTE}}` | Review độc lập, đối chiếu spec, rủi ro và chất lượng evidence. | `{{VERIFIER_EVIDENCE}}` |

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

## Resume

Native session ID được giữ nguyên, không bọc bằng continuation token:

- Codex: thread/session ID lấy từ JSON event của `codex exec --json`;
- Claude Code: `session_id` lấy từ `--output-format json`.

MCP chỉ coi resume thành công khi invocation trả lại đúng native session ID đã
yêu cầu. Nếu CLI fallback sang session mới hoặc không tìm thấy session, tool phải
fail thay vì âm thầm coi là resume thành công.

Policy vẫn chỉ cho một active `delegate_repo_task` tại một thời điểm và không có
status/polling workflow.
