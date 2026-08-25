# QiQi Multi-repository Workspace Template

Template này đặt tại root của local workspace chứa nhiều Git repository độc lập.
QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

Bốn nguồn truth được tách rõ:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Global Work Item và Shared Knowledge đều **không nằm trong workspace template**.
Chúng là user-scoped services để fresh QiQi session và Herdr-launched child agents
ở các repository khác nhau cùng thấy canonical state độc lập CWD.

## Thành phần

```text
AGENTS.md                         # QiQi orchestration + Work Item + knowledge policy
identity.md                       # danh tính và hard boundaries
repos.yaml                        # registry exact Git roots
SYSTEM_MAP.md                     # live topology/ownership/dependency
instructions/agent-routing.yaml   # canonical runtime route registry v2
instructions/model-routing.md     # QiQi route-selection policy
.codex/config.toml                # project-scoped qiqi_delegate only
mcp/qiqi_delegate/
├── core.py                       # TaskPacket + hook identity + SQLite runtime state
├── result_hook.py                # static native Stop-hook capture helper
├── server.py                     # Herdr execution boundary
├── pyproject.toml
└── tests/
.qiqi/
└── .gitignore                    # ignores runtime state + legacy runs
scripts/workspace-check.sh
docs/WORKSPACE_SETUP.md
```

Workspace cố ý không có `.qiqi/tasks/`, `work-items.sqlite3` hoặc `knowledge/` để
tránh tạo truth store thứ hai cạnh user-scoped MCP services.

## Ba MCP/service concern độc lập

```text
qiqi_delegate
= repo execution / native session / native result handoff

work_item
= canonical mutable product-task state

knowledge
= reusable durable knowledge retrieval / persistence
```

`.codex/config.toml` tại workspace chỉ đăng ký `qiqi_delegate`. `work_item` và
`knowledge` được đăng ký user/global scope, không duplicate vào project config.

## Execution model

```text
QiQi
  ↓ understand user intent
  ↓ work_item_get/create nếu turn thuộc product task
  ↓ conditional knowledge_read nếu reusable context có thể đổi orchestration
  ↓ SYSTEM_MAP / current Work Item / reconciled external evidence
  ↓ structured TaskPacket
qiqi_delegate
  ↓ register private active-capture descriptor
  ↓ inject static QiQi result hook
  ↓ Herdr START/RESUME tại exact Git root
Execution agent
  ↓ work_item_get canonical task state
  ↓ repo-local investigation / implementation / verification
  ↓ work_item_update repo evidence + blocker/question/handoff/checkpoint
  ↓ conditional Shared Knowledge read/write
  ↓ native final assistant response
static native Stop hook
  ↓ exact message + native session identity
qiqi_delegate
  ↓ persist runtime session/turn ownership in SQLite
QiQi
  ↓ read full agent_response
  ↓ work_item_get latest revision
  ↓ reconcile global phase/status/next action
```

Không dùng Markdown result/task artifact làm semantic transport/history cho turn mới.

## Global Work Item lifecycle

Work Item là canonical product-task state xuyên nhiều session, phase và repository.
Ví dụ identity:

```text
redmine:116655
redmine:151921
```

Một Work Item giữ:

```text
status / phase / summary
current_requirements
questions
decisions
changes
repos
blockers
handoffs
next_actions
checkpoints
revision
```

`phase` không phải hard state machine. QiQi có thể điều phối loop:

```text
investigation -> planning -> implementation -> unit_test -> it -> uat
                                           ^                 |
                                           └------ fix ------┘
```

Q&A/customer decision và requirement evolution được persist trong cùng canonical
Work Item, không nhét vào conversation memory hoặc `.qiqi/tasks`.

### Trước delegation

Nếu turn thuộc Work Item, QiQi:

1. `work_item_get` revision mới nhất;
2. reconcile current requirements, questions/decisions/changes, blockers,
   repo states, handoffs và next actions;
3. chọn repository/wave;
4. truyền canonical Work Item identity + revision trong `required_context`;
5. chỉ inline thêm external fact ngoài Work Item mà child không thể lấy từ current
   repo/allowed MCP.

Child đọc same Work Item trực tiếp; QiQi không copy toàn bộ task history vào packet.

### Sau delegation

QiQi đọc full native `agent_response`, rồi reread Work Item để reconcile những update
mà repo agent đã persist. QiQi sở hữu overall status/phase/summary, repo assignment,
global next action và final completion.

Revision conflict không được overwrite. Reread → reconcile → retry.

## Structured TaskPacket

Public tool:

```text
delegate_repo_task(
  repository,
  route,
  user_request,
  objective,
  scope,
  out_of_scope,
  required_context,
  constraints,
  acceptance_criteria,
  verification,
  known_unknowns,
  session_id?
)
```

- `scope` và `acceptance_criteria` phải non-empty;
- `required_context` item có đúng `fact`, `source`, `certainty`;
- certainty là `verified`, `user-provided` hoặc `authoritative-decision`;
- Work Item delegation phải identify canonical Work Item + revision trong
  `required_context`;
- không có `session_id` → START native session mới;
- có `session_id` → RESUME exact native conversation;
- cross-agent/repository resume bị từ chối.

### Closed-world context

Child không chia sẻ hidden conversation, hidden reasoning, workspace control context
hoặc sibling source/runtime state của QiQi.

Canonical Work Item được identify trong TaskPacket là exception có chủ đích: child
được query trực tiếp qua user-scoped Work Item MCP. Shared Knowledge cũng được query
khi repo policy yêu cầu. External live fact ngoài hai MCP/current repo vẫn phải nằm
trong TaskPacket.

## Native Result Handoff

### Settled / failed

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Agent tự chọn response structure; không fixed headings. MCP capture native
`last_assistant_message` qua Stop hook, không scrape viewport/scrollback/transcript.

### Blocked continuity

Nếu Herdr trả blocked trước native final response:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

MCP persist native session ownership trước blocked/result capture. QiQi chỉ RESUME
exact session sau khi external blocker được giải quyết; không invent blocker question
từ terminal screen.

## Static hook identity + dynamic capture state

Hook command của QiQi là static. Dynamic sink/nonce nằm trong private descriptor:

```text
.qiqi/state/active-captures/<sha256(adapter + repo-root)>.json
```

MCP-owned runtime state:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

Đây chỉ là runtime/session truth, không phải product task state.

`.qiqi/runs/` chỉ có thể tồn tại như legacy ownership-import bridge cho native
session cũ. New turn không dùng runs làm history/source of truth.

## Hook trust isolation

### Codex

QiQi chỉ trust exact static Stop hook bằng computed `trusted_hash`. Không dùng
`--dangerously-bypass-hook-trust`, trust-all hoặc mutate unrelated user hooks.

### Claude

QiQi inject `--settings` chỉ với static `Stop`/`StopFailure` hook của result handoff.
Không thay trust/permission state của unrelated hooks.

## Cross-repo orchestration

Work Item có thể chứa handoff cross-repo, nhưng child không tự sửa/delegate sibling:

```text
repo A agent
→ Work Item handoff A -> B + evidence
→ native response
→ QiQi reread/reconcile
→ delegate repo B
→ repo B agent đọc cùng Work Item
```

QiQi là broker của cross-repo execution. Work Item MCP là canonical task-state
broker. Knowledge MCP là reusable-knowledge broker.

## Shared Knowledge lifecycle

Sau khi hiểu concern, agent áp dụng decision rule:

- **MUST read** khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** khi durable context không thể đổi hành động hợp lý.

Substantive work có khả năng tạo/xác nhận reusable conclusion phải review/write.
Task-specific status/Q&A/change/blocker không tự động trở thành Knowledge.

Shared knowledge không mạnh hơn current owner source/test. Khi conflict, live owner
evidence thắng cho implementation task; verified reusable conclusion mới được
persist khi phù hợp.

## Herdr runtime

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected integration `current`, tạo workspace tại exact Git root,
launch native interactive TUI, wait terminal state, lấy native session identity rồi
cleanup.

## Verification

Static/unit checks:

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau đó chạy acceptance smoke trên installed Claude/Codex CLI thật cho adapter family
thực sự dùng. Unit test không thay native CLI smoke.

Smoke `qiqi_delegate` phải cover ít nhất:

1. Codex selective trust, không global hook-trust bypass;
2. START response Unicode dài vượt viewport giữ marker đầu/cuối;
3. exact-session RESUME;
4. native hook capture fail-closed, không screen/transcript fallback;
5. blocked continuity nếu môi trường có deterministic fixture.

Work Item rollout phải smoke riêng bằng fresh sessions:

1. QiQi `work_item_create/get`;
2. child repo session đọc cùng Work Item;
3. child update current-repo evidence;
4. QiQi reread thấy revision/state mới;
5. stale revision bị reject.

## Setup

Cài user-scoped Work Item MCP và Shared Knowledge MCP trước, mở fresh agent session,
sau đó:

```bash
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Không coi workspace production-ready chỉ vì checker pass; native CLI + shared MCP
fresh-session smoke vẫn là acceptance gate.
