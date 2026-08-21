# QiQi Multi-repository Workspace Template

Template này đặt tại root của local workspace chứa nhiều Git repository độc lập.
QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

Durable reusable knowledge **không nằm trong workspace template**. QiQi và execution
agents dùng cùng user-scoped Shared Knowledge MCP (`knowledge_read` /
`knowledge_write`) được cài từ `knowledge-template/`.

## Thành phần

```text
AGENTS.md                         # QiQi orchestration + knowledge policy
identity.md                       # danh tính và hard boundaries
repos.yaml                        # registry exact Git roots
SYSTEM_MAP.md                     # live topology/ownership/dependency
instructions/agent-routing.yaml   # canonical runtime route registry v2
instructions/model-routing.md     # QiQi route-selection policy
.codex/config.toml                # project-scoped qiqi_delegate only
mcp/qiqi_delegate/
├── core.py                       # TaskPacket + hook normalization + SQLite state
├── result_hook.py                # native Stop-hook capture helper
├── server.py                     # Herdr execution boundary + human hook approval
├── pyproject.toml
└── tests/
.qiqi/
├── .gitignore                    # ignores runtime state + legacy runs
└── tasks/                        # optional workspace-local task audit
scripts/workspace-check.sh
docs/WORKSPACE_SETUP.md
```

Workspace cố ý không có `knowledge/` directory để tránh tạo truth store thứ hai
cạnh Shared Knowledge Store.

## Hai MCP độc lập

```text
qiqi_delegate
= repo execution / native session / native result handoff

knowledge
= reusable durable knowledge retrieval / persistence
```

`.codex/config.toml` tại workspace chỉ đăng ký `qiqi_delegate`. Knowledge MCP được
đăng ký user/global scope để fresh QiQi session và Herdr-launched child agents ở
các repository khác nhau cùng thấy một service, independent CWD.

## Execution model

```text
QiQi
  ↓ understand user intent
  ↓ conditional knowledge_read nếu durable context có thể đổi orchestration
  ↓ SYSTEM_MAP / reconciled live evidence
  ↓ structured TaskPacket
qiqi_delegate
  ↓ MCP elicitation: operator approve native result hook
  ↓ Herdr START/RESUME tại exact Git root
Execution agent
  ↓ repo-local investigation / implementation / verification
  ↓ conditional Shared Knowledge read/write
  ↓ native final assistant response
native Stop hook
  ↓ exact message + native session identity
qiqi_delegate
  ↓ validate nonce/adapter/session
  ↓ persist session/turn ownership in SQLite
QiQi
  ↓ read full agent_response
  ↓ forward gần nguyên văn hoặc reconcile khi cần
```

Human approval xảy ra **trước mỗi delegation**. Resolver-owned approval không nằm
trong model-visible tool schema, nên QiQi/model không thể tự approve hook. Không dùng
Markdown result artifact làm semantic transport cho turn mới.

## Structured TaskPacket

Model-visible tool input:

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
- không có `session_id` → START native session mới;
- có `session_id` → RESUME exact native session;
- cross-agent/repository resume bị từ chối;
- `hook_approval` là MCP resolver-owned value, **không phải model-visible input**.

### Closed-world context

Child không chia sẻ hidden conversation, hidden reasoning, workspace control context
hoặc sibling state của QiQi.

Nếu QiQi đã dùng một live/durable fact để chọn repository, scope, dependency,
constraint hoặc acceptance criterion, fact đó phải nằm trong `required_context`
kèm provenance. Child Knowledge MCP không thay required premise này.

Shared Knowledge MCP vẫn được child dùng independently để discover/enrich/verify
context khác khi repo policy yêu cầu.

## Native Result Handoff

### Settled / failed

Khi native final message tồn tại:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Agent tự chọn response structure; không fixed headings. QiQi đánh giá completion từ
TaskPacket + evidence và giữ gần nguyên văn response khi một repo/turn đã đủ rõ.

MCP capture `last_assistant_message` qua native Stop hook. Nó không dùng terminal
viewport/scrollback, pane capture hoặc undocumented transcript parsing. Response dài
hơn một screen vì vậy không bị cắt theo viewport.

### Blocked continuity

Ngay khi Herdr xác nhận native session identity, MCP persist ownership trước khi xử
lý blocked/result capture.

Nếu Herdr trả blocked trước khi native final response tồn tại:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

`agent_response=null` nghĩa là chưa có native final response; không phải report bị
transport cắt. QiQi giữ exact session ID để RESUME sau khi external blocker được
giải quyết và không invent blocker question từ screen/transcript.

Nếu Stop hook fail sau khi session identity đã được biết, MCP fail rõ và error ghi
session ID còn resumable; không silently fallback sang transport khác.

## Runtime state

MCP-owned runtime state:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

QiQi/child không đọc hoặc sửa database này. `.qiqi/state/` được gitignore.

`.qiqi/runs/` chỉ có thể tồn tại như **legacy ownership-import bridge** cho session
được tạo bởi architecture cũ. New turn không ghi result Markdown và không dùng runs
làm history/source of truth.

## Workspace ↔ Repository handoff

QiQi là broker duy nhất của live cross-repo evidence:

```text
repo A native response
→ QiQi reconcile
→ relevant fact/evidence + provenance trong repo B required_context
→ repo B
```

Repo B không tự mở repo A source/result/runtime state. Shared Knowledge MCP là
curated durable context, không phải mailbox cho in-flight result.

## Shared Knowledge lifecycle

Sau khi hiểu concern, agent áp dụng decision rule:

- **MUST read** khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** khi durable context không thể đổi hành động hợp lý.

Với substantive work có khả năng tạo/xác nhận reusable conclusion, agent review và
`knowledge_write(entries)`. Trivial/mechanical/report-only work được skip write.
Required review không candidate dùng `entries=[]`. Search existing concept trước
create/update để dedupe.

Shared knowledge không mạnh hơn current owner source/test. Khi conflict, live owner
evidence thắng cho task hiện tại; verified durable conclusion mới mới được persist.

## Herdr runtime và hook trust

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected integration `current`, tạo workspace tại exact Git root,
launch real interactive TUI, wait terminal state, lấy native session identity rồi
cleanup.

Trước khi launch child, qiqi_delegate yêu cầu operator approve native result hook qua
MCP elicitation. Decline/cancel phải dừng call trước child execution.

Native result capture sau approval là invocation-scoped:

- Claude: inline `--settings` với `Stop`/`StopFailure` command hook;
- Codex: MCP-owned native `Stop` hook. Vì dynamic command chứa private sink + nonce
  nên trust hash thay đổi theo turn; child invocation dùng hook-trust bypass **chỉ
  sau khi human approval của turn đó đã được accept**.

Hook sink là private temporary directory; helper ghi event atomic `0600`. Route args
không được sở hữu hook configuration.

## Verification

Static/unit checks:

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau đó **bắt buộc** chạy acceptance smoke trên installed Claude/Codex CLI thật cho
adapter family thực sự dùng. Unit test không thay thế native CLI smoke.

Smoke phải cover ít nhất:

1. human approval gate: decline không launch child; accept mới chạy, cho cả Codex và Claude;
2. START response Unicode dài vượt viewport vẫn giữ marker đầu/cuối;
3. exact-session RESUME và approval mới cho turn RESUME;
4. native hook capture fail-closed, không screen/transcript fallback;
5. blocked continuity khi môi trường có deterministic blocked fixture.

Chi tiết ở `docs/WORKSPACE_SETUP.md`.

## Setup

Cài Shared Knowledge MCP trước, mở fresh agent session, sau đó:

```bash
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Không coi workspace production-ready chỉ vì checker pass; human-approval + native
CLI smoke gate vẫn bắt buộc cho adapter thực sự dùng.
