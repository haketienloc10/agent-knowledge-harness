# QiQi Multi-repository Workspace Template

Template này đặt tại root của local workspace chứa nhiều Git repository độc lập.
QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

Durable reusable knowledge **không nằm trong workspace template**. QiQi và execution
agents dùng cùng user-scoped Shared Knowledge MCP với progressive disclosure:

```text
knowledge_search
knowledge_read
knowledge_write
```

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
├── core.py                       # TaskPacket + hook identity + SQLite state
├── result_hook.py                # static native Stop-hook capture helper
├── server.py                     # Herdr execution boundary
├── pyproject.toml
└── tests/
.qiqi/
├── .gitignore                    # ignores runtime state + legacy runs
└── tasks/                        # optional workspace-local task audit
scripts/workspace-check.sh
docs/WORKSPACE_SETUP.md
```

Workspace cố ý không có `knowledge/` directory để tránh tạo truth store thứ hai cạnh
Shared Knowledge Store.

## Hai MCP độc lập

```text
qiqi_delegate
= repo execution / native session / native result handoff

knowledge
= reusable durable knowledge search / exact hydration / persistence
```

`.codex/config.toml` tại workspace chỉ đăng ký `qiqi_delegate`. Knowledge MCP được
đăng ký user/global scope để fresh QiQi session và Herdr-launched child agents ở các
repository khác nhau cùng thấy một service, independent CWD.

## Execution model

```text
QiQi
  ↓ understand user intent
  ↓ conditional knowledge_search nếu durable context có thể đổi orchestration
  ↓ hydrate 1–2 exact IDs bằng knowledge_read khi cần
  ↓ SYSTEM_MAP / reconciled live evidence
  ↓ structured TaskPacket
qiqi_delegate
  ↓ register private active-capture descriptor
  ↓ inject static QiQi result hook
  ↓ Herdr START/RESUME tại exact Git root
Execution agent
  ↓ repo-local investigation / implementation / verification
  ↓ conditional knowledge_search → knowledge_read → knowledge_write
  ↓ native final assistant response
static native Stop hook
  ↓ resolve per-turn sink/nonce from MCP state using adapter + cwd
  ↓ exact message + native session identity
qiqi_delegate
  ↓ validate nonce/adapter/session
  ↓ persist session/turn ownership in SQLite
  ↓ remove active-capture descriptor
QiQi
  ↓ read full agent_response
  ↓ forward gần nguyên văn hoặc reconcile khi cần
```

Không dùng Markdown result artifact làm semantic transport cho turn mới.

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
- không `session_id` → START native session mới;
- có `session_id` → RESUME exact native session;
- cross-agent/repository resume bị từ chối.

### Closed-world context

Child không chia sẻ hidden conversation, hidden reasoning, workspace control context
hoặc sibling state của QiQi.

Nếu QiQi đã dùng một live/durable fact để chọn repository, scope, dependency,
constraint hoặc acceptance criterion, fact đó phải nằm trong `required_context` kèm
provenance. Child Knowledge MCP không thay required premise này.

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

MCP capture `last_assistant_message` qua native Stop hook, không dùng terminal
viewport/scrollback, pane capture hoặc undocumented transcript parsing.

### Blocked continuity

Ngay khi Herdr xác nhận native session identity, MCP persist ownership trước khi xử
lý blocked/result capture. Nếu Herdr trả blocked trước native final response:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

`agent_response=null` nghĩa chưa có native final response. QiQi giữ exact session ID
để RESUME sau khi external blocker được giải quyết; không invent blocker question từ
screen/transcript.

Nếu Stop hook fail sau khi session identity đã biết, MCP fail rõ và error giữ session
ID còn resumable; không fallback sang transport khác.

## Static hook identity + dynamic capture state

Hook command QiQi là static: chỉ chứa Python executable, `result_hook.py`, adapter và
`.qiqi/state` root. Sink/nonce không xuất hiện trên child argv.

Trước mỗi delegation, MCP tạo private descriptor:

```text
.qiqi/state/active-captures/<sha256(adapter + repo-root)>.json
```

Descriptor giữ sink/nonce của turn và `expected_session_id` khi RESUME. Hook dùng
native `cwd` + `session_id` để resolve descriptor. Descriptor được xóa trong cleanup.
MCP-owned durable runtime state là:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

`.qiqi/runs/` chỉ là legacy ownership-import bridge; new turn không ghi result
Markdown và không dùng runs làm semantic history.

## Hook trust isolation

### Codex

QiQi inject session config cho exact static Stop hook và thêm `trusted_hash` chỉ cho
hook key đó. QiQi **không dùng `--dangerously-bypass-hook-trust`**, không trust-all và
không ghi persistent user hook trust. Unrelated user/project/plugin hooks giữ native
trust state.

### Claude

QiQi inject `--settings` chỉ với static `Stop`/`StopFailure` hook của result handoff;
không thay unrelated hook permission/trust state.

## Workspace ↔ Repository handoff

QiQi là broker duy nhất của live cross-repo evidence:

```text
repo A native response
→ QiQi reconcile
→ relevant fact/evidence + provenance trong repo B required_context
→ repo B
```

Repo B không tự mở repo A source/result/runtime state. Shared Knowledge MCP là curated
durable context, không phải mailbox cho in-flight result.

## Shared Knowledge lifecycle

Sau khi hiểu concern:

- **MUST search** khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- **MAY search** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP** khi durable context không thể đổi hành động hợp lý.

Retrieval là progressive:

```text
knowledge_search(keywords, context?, limit?)
→ bounded decision cards, không content/sources/revision/path
→ chọn 1–2 exact IDs
knowledge_read(ids)
→ full semantic content + routing + sources + revision
```

Search card chỉ dùng để chọn document. Search cố ý không trả revision để update phải
full-read existing knowledge trước. Không hydrate top-N chỉ vì search limit lớn.

Với substantive work có khả năng tạo/xác nhận reusable conclusion, agent review và
`knowledge_write(entries)`. Trivial/mechanical/report-only work được skip write.
Required review không candidate dùng `entries=[]`. Search existing concept trước
create/update để dedupe.

Shared knowledge không mạnh hơn current owner source/test. Khi conflict, live owner
evidence thắng cho task hiện tại; chỉ persist replacement conclusion sau verify.

## Herdr runtime

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected integration `current`, tạo workspace tại exact Git root, launch
real interactive TUI, wait terminal state, lấy native session identity rồi cleanup.
Route args không sở hữu hook configuration hoặc hook trust state.

## Verification

Static/unit checks:

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau đó **bắt buộc** acceptance smoke trên installed Claude/Codex CLI thật cho adapter
family thực sự dùng. Unit test không thay native CLI smoke.

Smoke phải cover ít nhất selective hook trust, START response dài vượt viewport,
exact-session RESUME, native capture fail-closed và blocked continuity khi môi trường
có deterministic fixture.

## Setup

Cài Shared Knowledge MCP trước, mở fresh agent session, xác nhận tool inventory có
đủ `knowledge_search`, `knowledge_read`, `knowledge_write`, sau đó:

```bash
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Không coi workspace production-ready chỉ vì checker pass; native CLI smoke gate vẫn
bắt buộc cho adapter thực sự dùng.
