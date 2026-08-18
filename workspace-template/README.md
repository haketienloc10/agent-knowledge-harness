# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc
lập. QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

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
.qiqi/tasks/                      # Optional workspace-specific task state
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
  ↓ terminal Result vào .qiqi/runs/...md
MCP
  ↓ validate result + native identity
  ↓ return {session_id, result_path}
QiQi
  ↓ read result_path
  ↓ reconcile outcome / blocker / Cross-repo Impact
  ↓ downstream task prompt hoặc workspace action
```

Mỗi call synchronous: chỉ resolve sau khi interactive turn settle (`idle`, `done`
hoặc `blocked`) hoặc fail. Không có public `status`, `wait`, `read`, separate
`resume`, `list-runs` hay transcript tool.

## Workspace ↔ Repository Handoff

QiQi là handoff broker duy nhất giữa các repository.

### Workspace → Repository

Trước delegation, QiQi:

1. Xác định repo/dependency và producer/consumer nếu có.
2. Đọc `SYSTEM_MAP.md` khi task chạm boundary cross-repo.
3. Nếu có upstream delegation, đọc producer `result_path` và lấy fact/evidence cần
   cho downstream work.
4. Đưa context cần dùng trực tiếp vào task prompt.
5. Gọi `delegate_repo_task`.

Execution agent không tự đọc sibling result artifact hoặc repository anh em để lấy
live cross-repo evidence.

### Repository → Workspace

Execution agent ghi terminal handoff qua result artifact. `### Cross-repo Impact`
đưa fact/evidence cần QiQi chuyển tới repository khác hoặc xử lý ở workspace.

QiQi đọc result rồi truyền relevant impact vào downstream prompt hoặc thực hiện
workspace action thuộc scope task hiện tại.

Luồng điển hình:

```text
workspace context
→ repo A
→ repo A result
→ QiQi reconcile
→ relevant fact/evidence trong prompt repo B
→ repo B result
→ QiQi reconcile
```

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

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Nếu relevant
artifact đã chứa đủ evidence cho yêu cầu hiện tại, QiQi đọc/reconcile artifact và
trả lời trực tiếp; không START hoặc RESUME chỉ để lấy lại, kiểm tra lại hoặc trình
bày lại information đã có.

## Prompt Ownership

Task prompt do QiQi quyết định. MCP không thêm operating policy về scope,
implementation, verification hoặc repo behavior. MCP chỉ append một
**result-handoff protocol footer** để agent biết exact result artifact, pending
marker, required headings và `Outcome = completed|blocked`.

Prompt phải self-contained. Upstream live result cần thiết phải được QiQi đưa trực
tiếp vào prompt; không giao sibling result/source path cho child như required input.

Với START, dòng không rỗng đầu tiên của `task` phải là một English task title ngắn,
ưu tiên ASCII và khoảng 3–8 từ. MCP dùng chính dòng này để derive
`<english-task-slug>` theo kebab-case, tối đa 48 ký tự. RESUME giữ nguyên
artifact/path đã được START tạo.

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

QiQi được đọc `.qiqi/runs/` vì đây là workspace-level terminal handoff. Child agent
khác không tự dùng artifact này như cross-repo input; QiQi broker live result qua
prompt.

## Herdr Runtime

Herdr là internal runtime của MCP. Chuẩn bị integration cho agent sẽ dùng:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected adapter integration ở trạng thái `current`, tự ensure named
Herdr session/server, tạo workspace tại exact Git root, launch real interactive
Codex/Claude TUI, prompt/wait, lấy native identity và đóng workspace sau turn.

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

QiQi chỉ chọn exact route; không truyền raw model/CLI flags qua MCP public API.

## Concurrency

Trong cùng `qiqi_delegate` server process:

```text
same resolved Git root → reject concurrent call
same native session_id → reject concurrent call
```

Khác Git root và khác native session có thể chạy đồng thời nếu không
dependency/shared-resource conflict. Consumer phụ thuộc producer phải ở wave sau.

## Delegation Silence

Khi delegation wave in-flight, QiQi không phát user-visible progress commentary và
không poll child state. Sau terminal tool success, QiQi đọc result artifact; sau
khi đủ result của wave mới reconcile và giao tiếp tiếp.

## Ranh giới

- Workspace root giữ orchestration, routing và result handoff.
- Repository con giữ architecture/domain/implementation/verification nội bộ.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Execution agent chỉ được đọc/sửa ngoài Git root đối với exact result artifact mà
  MCP handoff cho turn đó.
- Execution agent không tự đọc sibling result/repository source.
- MCP failure không fallback sang shell-based child agent.
- Herdr là implementation detail của MCP, không phải public orchestration API.

## Sử dụng

1. Sao chép template vào workspace root.
2. Điền `repos.yaml`, `SYSTEM_MAP.md` và routing.
3. Cài/kiểm tra Herdr integrations cho agent sẽ dùng.
4. Chạy `uv sync --project mcp/qiqi_delegate`.
5. Chạy `bash scripts/workspace-check.sh`.
6. Khởi động Codex tại workspace root; `.codex/config.toml` chỉ enable
   `delegate_repo_task`.
7. Làm theo `docs/WORKSPACE_SETUP.md` để smoke test START/RESUME, result artifact
   continuity, concurrency guard và repo-A → QiQi → repo-B handoff.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để suy
luận trạng thái repo con.
