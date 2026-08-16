# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc lập. QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool `delegate_repo_task`.

## Thành phần

```text
AGENTS.md                         # Policy orchestration + workspace↔repo handoff
identity.md                       # Danh tính và giới hạn
repos.yaml                        # Registry repository
SYSTEM_MAP.md                     # Quan hệ/contract liên repo
instructions/agent-routing.yaml   # Canonical runtime route registry
instructions/model-routing.md     # QiQi exact-route selection policy
.codex/config.toml                # Project-scoped MCP registration
mcp/qiqi_delegate/
├── pyproject.toml                # MCP runtime dependencies
└── server.py                     # Herdr-backed delegate_repo_task
knowledge/
├── README.md                     # Cách lưu/cập nhật workspace knowledge
├── INDEX.md                      # Summary index để biết knowledge nào cần đọc
├── systems/
├── contracts/
└── decisions/
.qiqi/tasks/                      # Working context + handoff/session pointers
.qiqi/runs/                       # Durable MCP result artifacts (runtime-created)
docs/
├── WORKSPACE_SETUP.md            # Setup/takeover + smoke test
└── examples/                     # Documentation-only routing examples
scripts/qiqi-mcp-server.sh        # MCP STDIO launcher
scripts/workspace-check.sh        # Harness checker
```

`instructions/` chỉ chứa active instructions. Hai file trong `docs/examples/` là
tài liệu tham khảo; `qiqi_delegate` không load chúng. Muốn dùng route/example nào,
copy hoặc adapt nó vào `instructions/agent-routing.yaml`.

## Execution Model

QiQi sở hữu task semantics, route selection và handoff context giữa repositories.
MCP sở hữu Herdr lifecycle, native session identity và result handoff.

```text
QiQi
  ↓ self-contained task prompt + route + optional session_id
MCP delegate_repo_task
  ↓ Herdr workspace + real interactive Codex/Claude
Execution agent
  ↓ investigation / implementation / verification
  ↓ repo-local knowledge update nếu cần
  ↓ terminal Result vào .qiqi/runs/...md
MCP
  ↓ validate result + native identity
  ↓ return {session_id, result_path}
QiQi
  ↓ read result_path
  ↓ reconcile outcome / blocker / Cross-repo Impact
  ↓ downstream task prompt hoặc workspace knowledge update
```

Mỗi call synchronous: chỉ resolve sau khi interactive turn settle (`idle`, `done`
hoặc `blocked`) hoặc fail. Không có public `status`, `wait`, `read`, separate
`resume`, `list-runs` hay transcript tool.

## Workspace ↔ Repository Handoff

QiQi là handoff broker duy nhất giữa các repository.

### Workspace → Repository

Trước delegation, QiQi:

1. Xác định repo/dependency và producer/consumer nếu có.
2. Đọc `SYSTEM_MAP.md` khi concern chạm boundary cross-repo.
3. Đọc `knowledge/INDEX.md` khi task có thể cần reusable cross-repo knowledge, sau
   đó chỉ mở exact document liên quan.
4. Nếu có upstream delegation, đọc producer `result_path` và lấy fact/evidence cần
   cho downstream work.
5. Đưa context cần dùng trực tiếp vào task prompt.

Execution agent không tự đọc workspace `knowledge/`, result artifact của repository
khác hoặc repository anh em để lấy context.

### Repository → Workspace

Execution agent ghi terminal handoff qua result artifact:

- `### Repo-local Knowledge`: source of truth nội bộ đã cập nhật;
- `### Cross-repo Impact`: fact/evidence QiQi cần để điều phối repo khác hoặc
  workspace.

QiQi đọc result rồi:

- đưa impact cần cho task hiện tại vào downstream prompt;
- cập nhật `SYSTEM_MAP.md` nếu topology/ownership thay đổi;
- cập nhật durable `knowledge/` + `knowledge/INDEX.md` nếu thông tin có khả năng
  dùng lại;
- không tạo workspace knowledge cho chi tiết chỉ có giá trị trong task hiện tại.

Luồng điển hình:

```text
workspace context
→ repo A
→ repo A result
→ QiQi reconcile
→ relevant fact/evidence trong prompt repo B
→ repo B result
→ QiQi reconcile
→ durable knowledge nếu thực sự dùng lại
```

## Knowledge MVP

`knowledge/INDEX.md` là mục lục đọc. Mỗi dòng có summary, khi nào cần đọc và phạm
vi để QiQi chọn đúng document mà không scan cả thư viện.

`knowledge/README.md` là hướng dẫn ghi. Nó quy định khi nào lưu cross-repo knowledge,
chọn thư mục nào và yêu cầu cập nhật `INDEX.md` trong cùng thay đổi.

Execution agent không đọc workspace knowledge trực tiếp. QiQi đọc và chắt lọc
phần liên quan vào prompt.

## Public MCP Contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

- không có `session_id` → START native Codex/Claude session mới;
- có `session_id` → RESUME đúng native session đó;
- `session_id` là native ID opaque; MCP không infer RESUME từ repository;
- cross-agent resume bị từ chối.

Success return chỉ gồm:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<repo>-<english-task-slug>-<session-id>.md"
}
```

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Không RESUME chỉ để yêu cầu agent lặp lại report đã nằm trong result artifact.

## Prompt Ownership

Task prompt do QiQi quyết định. MCP không thêm operating policy về scope,
implementation, verification hoặc repo behavior. MCP chỉ append một
**result-handoff protocol footer** để agent biết exact result artifact, pending
marker, required headings và `Outcome = completed|blocked`.

Prompt phải self-contained. Workspace knowledge hoặc upstream result cần thiết phải
được QiQi đưa trực tiếp vào prompt; không giao workspace path cho child như required
input.

Với START, dòng không rỗng đầu tiên của `task` phải là một English task title ngắn,
ưu tiên ASCII và khoảng 3–8 từ. MCP dùng chính dòng này để derive
`<english-task-slug>` theo kebab-case, tối đa 48 ký tự. Đặt một dòng trống sau
title; phần instruction còn lại có thể dùng ngôn ngữ phù hợp nhất. RESUME giữ nguyên
artifact/path đã được START tạo.

Ví dụ:

```text
Update checkout validation

Kiểm tra và sửa validation của checkout flow...
```

sẽ cho filename dạng:

```text
.qiqi/runs/<repo>-update-checkout-validation-<native-session-id>.md
```

## Result Artifact

Mỗi native session có một durable Markdown artifact dưới `.qiqi/runs/`.

START tạo pending artifact trước khi native identity có sẵn, prompt actual task,
sau đó validate và promote atomically sang filename chứa English task slug + native
session ID. RESUME resolve chính xác artifact hiện có bằng repository + native
`session_id`, append `Task N / Result N`, rồi trả lại cùng `result_path`.

Newest result có headings:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

QiQi được đọc `.qiqi/runs/` vì đây là workspace-level terminal handoff, không phải
repo-local source investigation. Child agent khác không tự dùng artifact này như
cross-repo input; QiQi phải broker context qua prompt.

## Herdr Runtime

Herdr là internal runtime của MCP. Chuẩn bị integration cho agent sẽ dùng:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected adapter integration ở trạng thái `current`, tự ensure named
Herdr session/server (mặc định `qiqi-delegate`), tạo workspace tại exact Git root,
launch real interactive Codex/Claude TUI, prompt/wait, lấy native identity và đóng
workspace sau turn.

QiQi không quản lý Herdr pane/workspace/status trong normal workflow.

## Routing

`instructions/model-routing.md` chỉ trả lời câu hỏi **QiQi nên chọn exact route nào**.
Nó không duplicate model ID, permission mode, effort hoặc native CLI flags.

`instructions/agent-routing.yaml` là **canonical machine-readable runtime registry**
và là file routing duy nhất MCP load. Agent entry định nghĩa `command`, `adapter`,
`start_args`, `resume_args`; route entry định nghĩa `agent`, `model`, `args`.

Runtime placeholders:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

`start_args` không chứa `{session_id}`; `resume_args` phải chứa `{session_id}`.
Registry chỉ dùng interactive agent invocation; các transport batch/JSON-output cũ
không còn thuộc execution contract.

QiQi chỉ chọn exact route; không truyền raw model/CLI flags qua MCP public API.

Các file `docs/examples/agent-routing.*.yaml` chỉ minh họa cách customize registry.
Route chỉ khả dụng khi thực sự tồn tại trong `instructions/agent-routing.yaml`.

## Concurrency

Trong cùng `qiqi_delegate` server process:

```text
same resolved Git root → reject concurrent call
same native session_id → reject concurrent call
```

Khác Git root và khác native session có thể chạy đồng thời nếu không
dependency/shared-resource conflict. Dependency và shared external resource do QiQi
lập kế hoạch.

Consumer phụ thuộc producer phải ở wave sau. QiQi đọc producer result và đưa phần
context cần thiết vào consumer prompt trước khi dispatch.

## Delegation Silence

Khi delegation wave in-flight, QiQi không phát user-visible progress commentary và
không poll child state. Sau terminal tool success, QiQi đọc result artifact; sau
khi đủ result của wave mới reconcile và giao tiếp tiếp.

## Ranh giới

- Workspace root giữ orchestration, handoff context và tri thức cross-repo.
- Repository con giữ architecture/domain/implementation/verification và repo-local
  knowledge.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Execution agent chỉ được đọc/sửa ngoài Git root đối với exact result artifact mà
  MCP handoff cho turn đó.
- Execution agent không tự đọc workspace knowledge hoặc sibling result/repository.
- MCP failure không fallback sang shell-based child agent.
- Herdr là implementation detail của MCP, không phải public orchestration API.

## Sử dụng

1. Sao chép template vào workspace root.
2. Điền `repos.yaml`, `SYSTEM_MAP.md`, routing và `knowledge/INDEX.md`; đọc
   `knowledge/README.md` khi thêm workspace knowledge.
3. Cài/kiểm tra Herdr integrations cho agent sẽ dùng.
4. Chạy `uv sync --project mcp/qiqi_delegate`.
5. Chạy `bash scripts/workspace-check.sh`.
6. Khởi động Codex tại workspace root; `.codex/config.toml` chỉ enable
   `delegate_repo_task`.
7. Làm theo `docs/WORKSPACE_SETUP.md` để smoke test START/RESUME, result artifact
   continuity, concurrency guard và repo-A → QiQi → repo-B handoff.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để suy luận trạng thái repo con.
