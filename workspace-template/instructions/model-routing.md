# Model Routing cho QiQi

Tệp này là policy để QiQi **chọn route**. Machine-readable agent/model/native
argv nằm trong `instructions/agent-routing.yaml`.

QiQi không tự ghép executable, model ID hoặc CLI flags. Khi cần đổi model/flag,
sửa route registry; public MCP schema giữ nguyên.

## Profiles

| Profile | Route | Dùng khi | Route hiện tại |
|---|---|---|---|
| `fast` | `claude-haiku` | Task cơ học, nhỏ, yêu cầu rõ, verification trực tiếp. | Claude `haiku`, `--permission-mode acceptEdits`, `--effort medium`. |
| `balanced` | `claude-balanced` | Implementation thông thường, bug vừa, test/docs kỹ thuật. | Claude `sonnet`, `--permission-mode auto`, `--effort medium`. |
| `deep` | `claude-deep` | Kiến trúc, migration, contract phức tạp hoặc bug khó. | Claude `sonnet`, `--permission-mode auto`, `--effort high`. |
| `verifier` | `claude-verifier` | Review độc lập, đối chiếu spec/rủi ro/evidence. | Claude `sonnet`, `--permission-mode auto`, `--effort xhigh`. |

`codex-balanced` tồn tại trong machine registry và có thể được QiQi chọn khi
policy/task yêu cầu Codex; nó dùng `gpt-5.4` với reasoning effort medium.

## Quy tắc Chọn

1. Xác định loại task và mức rủi ro.
2. Chọn profile thấp nhất vẫn đủ tin cậy.
3. Resolve route từ policy và registry.
4. Truyền đúng tên route vào `delegate_repo_task`.
5. START mới: bỏ `session_id`.
6. Tiếp tục native conversation: truyền native `session_id` đã được tool trả về và
   dùng route thuộc cùng agent family.
7. Muốn chuyển agent family: START session mới và handoff context; không resume
   chéo ID.
8. Không truyền raw CLI arguments, executable, model ID hoặc permission mode qua
   task/tool arguments.

Không đổi route chỉ vì environment failure, dependency thiếu hoặc product
requirement chưa rõ.

## Agent Routing Registry

`instructions/agent-routing.yaml` là source of truth thực thi.

Mỗi `agent` định nghĩa:

- `command`;
- `adapter` (`codex` hoặc `claude`);
- `start_args`;
- `resume_args`.

Mỗi `route` định nghĩa:

- `agent`;
- `model`;
- route-specific `args`.

Runtime placeholders MCP hỗ trợ:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

`{route_args}` là list splice. Các placeholder scalar còn lại được MCP expand
trực tiếp vào argv. `start_args` không được chứa `{session_id}`;
`resume_args` bắt buộc chứa `{session_id}`.

Registry mô tả **interactive** Codex/Claude argv chạy bên trong Herdr. Execution
transport không dùng non-interactive JSON/output-schema flow.

`{result_dir}` trỏ tới workspace `.qiqi/runs` để interactive agent có quyền truy
cập exact result artifact mà MCP handoff.

## Native Session Identity

QiQi không parse stdout hoặc output envelope để lấy session ID. MCP nhận native
identity từ Herdr agent integration sau khi interactive turn thực sự bắt đầu.

MCP chỉ coi RESUME thành công khi native identity báo lại đúng `session_id` được
yêu cầu. Fallback sang session mới là lỗi.

Native ID được coi là opaque. Không suy luận agent/session semantics từ format ID.

## Result Handoff không thuộc Model Routing

Route chỉ quyết định **agent/model/flags**. Route không quyết định result format.

MCP append cùng một result-handoff protocol cho mọi route và success return:

```json
{
  "session_id": "<native-id>",
  "result_path": ".qiqi/runs/<session-artifact>.md"
}
```

QiQi đọc `result_path` để reconcile newest Result section. Không dùng RESUME chỉ
để lấy lại report.

## Concurrency không thuộc Model Routing

Route không quyết định task có chạy đồng thời hay không.

QiQi có thể đặt task vào cùng delegation wave khi:

- khác resolved Git root;
- không phụ thuộc output/decision chưa có;
- không cùng shared mutable resource;
- không dùng cùng native `session_id`.

Trong cùng `qiqi_delegate` server process, MCP reject concurrent call trên cùng
resolved Git root hoặc cùng native session. Khi dependency/conflict không rõ,
QiQi chạy tuần tự.

Trong wave, QiQi áp dụng Delegation Silence và không poll child state.
