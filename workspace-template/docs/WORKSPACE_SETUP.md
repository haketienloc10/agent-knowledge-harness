# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào một workspace thực tế. Mục
tiêu là để QiQi giữ vai trò Chief of Staff tại workspace root và giao mọi
repo-local work qua MCP tool `delegate_repo_task`.

## Kết quả cần đạt

Sau setup:

- `repos.yaml` trỏ đúng exact Git root local và không có alias trùng Git root;
- `SYSTEM_MAP.md` mô tả dependency/contract liên repo;
- `knowledge/INDEX.md` giúp QiQi biết knowledge nào cần đọc mà không scan cả thư viện;
- `knowledge/README.md` hướng dẫn cách lưu/cập nhật durable cross-repo knowledge;
- QiQi là handoff broker duy nhất giữa repositories: upstream result được đọc và
  chắt lọc vào downstream task prompt;
- execution agent không tự đọc workspace knowledge, sibling repository hoặc sibling
  result artifact để lấy cross-repo context;
- `instructions/agent-routing.yaml` là canonical runtime registry cho
  interactive agent/model/flags + START/RESUME argv;
- `instructions/model-routing.md` chỉ hướng dẫn QiQi chọn exact route;
- `docs/examples/agent-routing.*.yaml` chỉ là documentation-only examples và
  không được MCP load;
- `.codex/config.toml` chỉ expose MCP tool `delegate_repo_task`;
- Herdr CLI có sẵn và integration cho agent đã cấu hình ở trạng thái `current`;
- MCP START/RESUME chạy real interactive Codex/Claude qua Herdr;
- success return chỉ có native `session_id` + workspace-relative `result_path`;
- START result path dùng readable English task slug do QiQi title quyết định;
- QiQi đọc result artifact trước khi quyết định task tiếp theo;
- concurrent call cùng Git root hoặc cùng native session bị reject trong cùng
  MCP server process;
- `bash scripts/workspace-check.sh` trả `PASS`.

## Runtime yêu cầu

Tối thiểu:

```bash
command -v codex && codex --version
command -v claude && claude --version
command -v herdr && herdr --version
command -v uv && uv --version
command -v python3
command -v git
command -v rg
command -v yq
```

MCP Python SDK và PyYAML nằm trong `mcp/qiqi_delegate/pyproject.toml`; Herdr là
external CLI runtime của MCP.

## Bước 1: Điền Repository Registry

Xác nhận từng repo:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng path tương đối từ workspace root. Mỗi `path` phải trỏ đúng
Git root, không phải parent/subdirectory. Không tạo hai entry cùng resolve về một
Git root vì MCP conflict guard sở hữu resource theo Git root thực tế.

## Bước 2: System Map và Knowledge

Điền `SYSTEM_MAP.md` bằng evidence thực tế cho topology/dependency/contract và
ownership liên repo.

Workspace knowledge dùng mô hình MVP:

```text
knowledge/INDEX.md   → summary index để quyết định knowledge nào cần đọc
knowledge/README.md  → quy tắc tạo/cập nhật knowledge và index
knowledge/...        → durable cross-repo knowledge có khả năng dùng lại
```

Khi cần knowledge, QiQi đọc `knowledge/INDEX.md` trước rồi chỉ mở exact document có
summary/phạm vi phù hợp. Không scan toàn bộ `knowledge/`.

Khi result artifact cho thấy reusable cross-repo knowledge mới hoặc thay đổi, làm
theo `knowledge/README.md` và cập nhật `knowledge/INDEX.md` trong cùng thay đổi.
Chi tiết nội bộ một repository vẫn thuộc repository đó.

Execution agent không tự đọc workspace knowledge; QiQi phải đưa phần context cần
dùng trực tiếp vào task prompt.

## Bước 3: Cài Herdr Integrations

Cài integration cho agent sẽ dùng:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

`herdr integration status` phải báo adapter được cấu hình là `current`.

MCP không tự install integration vì thao tác này thay đổi config của Codex/Claude.
MCP chỉ preflight và fail rõ nếu integration không current.

MCP dùng named Herdr session mặc định:

```text
qiqi-delegate
```

Có thể override binary/session bằng environment của MCP khi thật sự cần:

```text
QIQI_HERDR_BIN
QIQI_HERDR_SESSION
```

Không cần khởi động Herdr server thủ công trong normal workflow; MCP tự ensure
named server. Khi debug có thể attach named session bằng Herdr CLI, nhưng đây
không phải progress API của QiQi.

## Bước 4: Điền Agent Routing

`instructions/agent-routing.yaml` là **canonical machine-readable interactive
execution registry** và là file routing duy nhất MCP load.

Mỗi agent entry sở hữu:

```text
command
adapter
start_args
resume_args
```

Mỗi route sở hữu:

```text
agent
model
args
```

Runtime placeholders:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

Quy tắc:

- `start_args` không chứa `{session_id}`;
- `resume_args` phải chứa `{session_id}`;
- `{route_args}` là list splice;
- `{result_dir}` trỏ tới workspace `.qiqi/runs`;
- route/model/native flags chỉ nằm trong registry, không truyền qua public MCP API;
- interactive agent phải giữ TUI sống trong turn để Herdr quan sát native state.

Registry mặc định hiện gồm:

- `codex-balanced`: Codex `gpt-5.4`, reasoning effort medium;
- `claude-haiku`: Claude `haiku`, permission mode `acceptEdits`, effort medium;
- `claude-balanced`: Sonnet, permission mode `auto`, effort medium;
- `claude-deep`: Sonnet, permission mode `auto`, effort high;
- `claude-verifier`: Sonnet, permission mode `auto`, effort xhigh.

Codex hiện không ép hook-trust bypass; trust behavior thuộc local Codex config/TUI.

Hai file dưới `docs/examples/` chỉ minh họa cách cấu hình registry theo một agent
family. MCP không đọc các file này. Muốn dùng route từ example, copy/adapt route đó
vào `instructions/agent-routing.yaml` rồi chạy checker.

## Bước 5: Điền Route Selection Policy

`instructions/model-routing.md` chỉ giúp QiQi quyết định **exact route name** cho
một task. File này không giữ model ID, permission mode, effort hoặc CLI flags.

QiQi truyền exact route vào tool; MCP resolve agent/model/native flags từ
`instructions/agent-routing.yaml`. Nếu một route chỉ xuất hiện trong tài liệu hoặc
`docs/examples/` mà không tồn tại trong canonical registry, route đó không khả dụng.

## Bước 6: Chuẩn bị MCP Environment

Từ workspace root:

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile mcp/qiqi_delegate/server.py
```

`.codex/config.toml` đăng ký STDIO server `qiqi_delegate`. `tool_timeout_sec` phải
đủ dài cho một interactive coding turn hoàn thành trong cùng MCP call.

## Bước 7: Hiểu Public Execution Boundary

QiQi chỉ gọi:

```text
delegate_repo_task(repository, task, route, session_id?)
```

### START

```text
session_id absent
→ resolve exact repository + route
→ ensure Herdr server + current adapter integration
→ claim resolved Git root
→ create Herdr workspace at exact repo root
→ start real interactive agent using start_args + route args
→ derive English task slug từ dòng không rỗng đầu tiên của QiQi task
→ create pending result artifact
→ append Task 1 / Result 1 marker
→ send actual QiQi task + MCP result-handoff footer
→ wait for turn settle
→ obtain native session identity
→ validate Result 1
→ promote pending artifact to final session artifact
→ return {session_id, result_path}
→ close Herdr workspace + release Git root
```

### RESUME

```text
session_id present
→ resolve exact repository + route
→ ensure Herdr server + current adapter integration
→ claim resolved Git root + native session_id
→ resolve exact existing result artifact
→ create Herdr workspace
→ start interactive agent using resume_args + exact session_id
→ append Task N / Result N marker
→ send follow-up QiQi task + result-handoff footer
→ wait for settle
→ require reported native identity == requested session_id
→ validate newest Result N
→ return same {session_id, result_path}
→ cleanup + release resources
```

MCP không infer resume từ repository và không fallback sang session mới.

## Bước 8: Prompt Ownership và Context Handoff

QiQi sở hữu task semantics. Prompt phải tự chứa outcome, scope, context,
dependency, decisions/evidence và verification cần thiết.

Khi task phụ thuộc workspace knowledge hoặc result của repo khác:

1. QiQi đọc `knowledge/INDEX.md`/exact knowledge document hoặc upstream
   `result_path`.
2. QiQi lấy đúng fact/evidence cần thiết.
3. QiQi đưa nội dung đó trực tiếp vào task prompt.
4. Không yêu cầu execution agent tự mở workspace knowledge, sibling repository hoặc
   sibling result artifact.

Ví dụ context downstream:

```text
Upstream result đã xác nhận:
- payment thêm PaymentStatus=pending_review.
- producer tests pass.
- checkout là consumer cần hỗ trợ value này.
```

Với START, dòng không rỗng đầu tiên của `task` phải là một **English task title**
ngắn, ưu tiên ASCII, khoảng 3–8 từ. Đặt một dòng trống sau title rồi mới viết
instruction chi tiết. MCP dùng title này để derive `<english-task-slug>` theo
kebab-case ASCII, tối đa 48 ký tự. Phần instruction còn lại có thể dùng tiếng Việt
hoặc ngôn ngữ khác nếu phù hợp hơn.

Ví dụ:

```text
Update checkout validation

Kiểm tra và sửa validation của checkout flow. Chạy test liên quan trước khi kết thúc.
```

cho result path dạng:

```text
.qiqi/runs/<repo>-update-checkout-validation-<native-session-id>.md
```

RESUME không đổi filename; nó luôn dùng exact artifact đã tạo trong START.

MCP không thêm policy về cách implementation. MCP chỉ append protocol footer để
agent biết exact result artifact + pending marker + required headings.

## Bước 9: Result Handoff và Reconcile

Success return:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<repo>-<english-task-slug>-<session-id>.md"
}
```

Sau tool success, QiQi **phải đọc `result_path`**. Newest `## Result N` chứa:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Outcome` là `completed` hoặc `blocked`.

`Repo-local Knowledge` cho biết repo đã cập nhật source of truth nội bộ nào.
`Cross-repo Impact` là outbound handoff về QiQi và nên cho biết điều gì thay đổi,
affected repository/boundary, evidence chính và next action nếu rõ.

Sau khi đọc result, QiQi quyết định:

- impact cần cho downstream task → đưa fact/evidence vào downstream prompt;
- topology/ownership reusable → cập nhật `SYSTEM_MAP.md`;
- contract/flow/decision reusable → cập nhật `knowledge/` + `knowledge/INDEX.md`;
- chỉ có giá trị cho task hiện tại → không tạo durable knowledge.

Không RESUME chỉ để yêu cầu agent cung cấp lại terminal report. Nếu tool đã trả
success nhưng QiQi chưa có report trong context, hành động đúng là đọc artifact.

Mỗi native session giữ một result artifact; RESUME append vào cùng file. `.pending-*`
chỉ là START staging artifact và không được dùng để resolve RESUME.

## Bước 10: Dependency và Delegation Waves

Task có thể cùng wave khi:

- khác resolved Git root;
- không phụ thuộc output/decision chưa có;
- không cùng external/shared mutable resource;
- không dùng cùng native `session_id`;
- prompt/completion criteria độc lập.

Trong cùng `qiqi_delegate` server process:

- cùng resolved Git root → reject concurrent call;
- cùng native `session_id` → reject concurrent call.

Consumer cần producer result phải ở wave sau:

```text
producer delegation
→ QiQi đọc producer result
→ QiQi chắt lọc fact/evidence
→ consumer task prompt
→ consumer delegation
```

Consumer không tự đọc producer artifact. Dependency/shared resource vẫn do QiQi
lập kế hoạch. Khi không chắc conflict, chạy tuần tự.

## Bước 11: Delegation Silence

Khi wave in-flight, QiQi không phát progress commentary, không poll status/PID/
transcript/session state và không chạy downstream task dựa trên partial state.

Sau mỗi terminal success, QiQi đọc result artifact; sau khi đủ kết quả của wave,
reconcile rồi mới giao tiếp hoặc dispatch wave sau.

## Bước 12: Internal Herdr Recovery

Hai recovery là implementation detail của MCP:

- fresh Herdr root pane có thể chưa được nhận diện là shell; MCP retry bounded
  `agent_pane_busy` trước khi fail;
- Claude có thể để large pasted prompt trong composer mà chưa submit; khi Herdr
  báo `agent_prompt_stalled`, MCP kiểm tra state rồi gửi **một Enter** duy nhất nếu
  agent vẫn idle. MCP không paste prompt lần hai.

QiQi không điều khiển các recovery này.

## Bước 13: Xác minh Workspace

Chạy:

```bash
bash scripts/workspace-check.sh
```

Checker xác minh:

- required workspace artifacts;
- không còn duplicate `KNOWLEDGE.md` hoặc proposal lifecycle;
- `knowledge/README.md` + `knowledge/INDEX.md` đúng MVP read/write contract;
- QiQi policy có bidirectional handoff và context broker invariant;
- exact Git-root registry + duplicate-root guard;
- MCP Python/runtime contract;
- Herdr CLI + current integrations cho configured adapters;
- interactive routing grammar + placeholders;
- không còn legacy non-interactive/result-schema transport;
- exactly one public MCP tool;
- result artifact/identity validation;
- repo/native-session concurrency guard;
- Claude stalled-prompt recovery;
- QiQi policy về `result_path` và no-report-only RESUME.

Checker không gọi model API và không chạy test của repository con. Các file trong
`docs/examples/` cũng không phải runtime input và không được checker xem như active
routing registry.

## Bước 14: Fresh-session Smoke Test

Tối thiểu:

1. START route Codex bằng task có English title ở dòng đầu → nhận `session_id` +
   `result_path`; xác nhận filename chứa readable English slug.
2. Đọc artifact → xác nhận Task 1 / Result 1 và required headings.
3. RESUME cùng Codex ID với **task follow-up thật** → cùng `session_id` và cùng
   `result_path`, artifact append Task 2 / Result 2.
4. START route Claude bằng task có English title → nhận `session_id` + `result_path`.
5. Đọc artifact → xác nhận result hợp lệ và filename dùng English slug.
6. RESUME Claude với follow-up thật → same ID/path và append turn.
7. Hai task read-only trên Git root khác nhau có thể active cùng wave nếu host
   dispatch concurrent calls.
8. Hai call cùng Git root bị reject khi call đầu còn active.
9. Hai RESUME cùng native `session_id` bị reject khi call đầu còn active.
10. Không có user-visible progress commentary trong wave.
11. Không có second RESUME chỉ để lấy report; report được đọc trực tiếp từ
    `result_path`.

## Bước 15: Smoke Test Workflow Hai chiều

Dùng hai repository test có dependency producer → consumer.

### Repo A — producer

1. QiQi đọc `SYSTEM_MAP.md` và `knowledge/INDEX.md` nếu liên quan.
2. QiQi delegate một investigation/change task cho repo A.
3. Repo A result phải có `### Cross-repo Impact` nêu một fact consumer cần biết,
   affected boundary và evidence.
4. QiQi đọc `result_path`; không mở RESUME chỉ để hỏi lại report.

### Repo B — consumer

5. QiQi tạo task mới cho repo B và **inline** relevant fact/evidence từ repo A vào
   prompt.
6. Repo B hoàn thành task mà không cần đọc repo A, workspace knowledge hoặc repo A
   result artifact.
7. QiQi đọc repo B result và reconcile outcome.

### Knowledge write

8. Nếu fact từ repo A/B có khả năng dùng lại, QiQi tạo/cập nhật đúng document dưới
   `knowledge/` và cập nhật `knowledge/INDEX.md` trong cùng thay đổi.
9. Nếu fact chỉ phục vụ task hiện tại, không tạo durable knowledge.

Workflow chỉ đạt khi đường truyền thực tế là:

```text
workspace
→ repo A
→ QiQi result reconcile
→ repo B prompt
→ repo B
→ QiQi
→ optional workspace knowledge
```

Không chấp nhận shortcut child-to-child qua filesystem.

Chỉ coi workspace sẵn sàng khi checker pass, START/RESUME smoke test của các agent
được cấu hình đã thành công và workflow hai chiều producer → QiQi → consumer đã
được xác nhận.
