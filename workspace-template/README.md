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
.qiqi/tasks/                      # Optional workspace-local task artifacts
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
  ↓ downstream task prompt hoặc workspace update khi cần
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
3. Nếu có upstream delegation, đọc producer `result_path` và lấy fact/evidence cần
   cho downstream work.
4. Đưa context cần dùng trực tiếp vào task prompt.

Execution agent không tự đọc result artifact của repository khác hoặc repository
anh em để lấy context.

### Repository → Workspace

Execution agent ghi terminal handoff qua result artifact. `### Cross-repo Impact`
là fact/evidence QiQi cần để điều phối repo khác hoặc workspace.

QiQi đọc result rồi:

- đưa impact cần cho task hiện tại vào downstream prompt;
- cập nhật `SYSTEM_MAP.md` nếu topology/ownership thay đổi;
- nếu impact không cần hành động thêm thì không tạo artifact chỉ để lưu lịch sử.

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

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Nếu relevant artifact
đã chứa đủ evidence cho yêu cầu hiện tại, QiQi đọc/reconcile artifact và trả lời
trực tiếp; không START hoặc RESUME chỉ để lấy lại, kiểm tra lại hoặc trình bày lại
information đã có.

## Prompt Ownership

Task prompt do QiQi quyết định. MCP không thêm operating policy về scope,
implementation, verification hoặc repo behavior. MCP chỉ append một
**result-handoff protocol footer** để agent biết exact result artifact, pending
marker, required headings và `Outcome = completed|blocked`.

Prompt phải self-contained. Workspace context hoặc upstream result cần thiết phải
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
