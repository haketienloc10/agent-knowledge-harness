# Agent Knowledge Harness

Bộ khung vận hành QiQi trong multi-repository workspace với bốn nguồn truth độc lập:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Kiến trúc

```text
                         Shared Knowledge Store
                         Markdown + INDEX.md
                                ▲      │
                                │      ▼
                         Knowledge MCP (user scope)
                                ▲
                                │ reusable truth
                                │
Người dùng → QiQi workspace ────┼───────────────┐
              │                 │               │
              │                 ▼               │
              │        Global Work Item MCP     │
              │          SQLite (user scope)    │
              │                 ▲               │
              │                 │ task truth    │
              │ TaskPacket      │               │ native final response
              ▼                 │               │
        qiqi_delegate MCP ──────┴───────────────┘
              │                                 ▲
              │ Herdr START / RESUME            │
              ▼                                 │
       independent Git repos ───────────────────┘
                repo source/test truth
```

QiQi và repo execution agents cùng đọc một canonical Work Item. Agent con chỉ làm
phần thuộc Git root hiện tại; cross-repo remaining work/handoff quay lại QiQi để
điều phối repository khác.

## `workspace-template/`

QiQi control plane tại workspace root:

- `repos.yaml` registry exact Git roots;
- `SYSTEM_MAP.md` live topology/ownership/dependency;
- structured TaskPacket cho mỗi delegation;
- Global Work Item lifecycle/orchestration policy;
- model/runtime routing;
- synchronous `qiqi_delegate` START/RESUME;
- native final-response handoff qua Stop hook;
- MCP-owned SQLite session ownership dưới `.qiqi/state/`;
- dependency waves, evidence reuse và user reporting.

Workspace **không sở hữu task store hoặc durable knowledge store**. `.qiqi/tasks/`
không còn là task source of truth. `.qiqi/runs/` chỉ có thể tồn tại như legacy
migration source cho native session ownership cũ; turn mới không dùng Markdown
artifact làm semantic transport/history.

## `repo-template/`

Policy tối thiểu cho execution agent tại mỗi Git root:

- architecture + verification routing;
- Git-root/sibling-repo boundaries;
- đọc canonical Work Item khi TaskPacket identify product task;
- chỉ update repo-local evidence/state + material blocker/question/handoff mà agent
  thực sự xác lập;
- conditional Shared Knowledge MCP read/write lifecycle;
- cross-repo remaining work handoff về QiQi;
- native final assistant response là semantic handoff, không fixed headings.

## `work-item-template/`

Repository-independent mutable product-task subsystem:

```text
work-item-template/
├── README.md
├── mcp/work_item/
│   ├── core.py
│   ├── server.py
│   ├── pyproject.toml
│   └── tests/
└── scripts/
    ├── install-user-mcp.sh
    ├── work-item-mcp-server.sh
    └── work-item-template-check.sh
```

MVP expose bốn tools:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
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

Mục tiêu là giúp task product kéo dài qua investigation, planning, implementation,
unit test, IT, UAT, fix bug và Q&A có continuity xuyên session/repository mà không
bắt người dùng hoặc QiQi kể lại history.

### Snapshot và material history

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
= snapshot hiện tại để tiếp tục ngay

questions/decisions/changes/checkpoints
= material history giải thích tại sao snapshot hiện tại hình thành
```

Không lưu working transcript hoặc hidden reasoning.

### Questions, decisions và requirement changes

Open question dùng cho ambiguity chưa thể tự chốt. Khi user/customer Q&A trả lời:

```text
question resolved
→ decision active
→ current_requirements reconcile nếu semantics đổi
→ changes[] nếu requirement/scope thực sự đổi
```

Decision cũ bị đổi sau này không bị xóa; mark `superseded` + `superseded_by` để phân
biệt implementation sai với requirement đổi sau đó.

### Cross-repo handoff

Handoff nằm trong chính canonical Work Item:

```text
backend agent
→ Work Item: backend evidence + handoff backend -> frontend
→ QiQi reconcile
→ delegate frontend
→ frontend agent đọc cùng Work Item
```

Không có repo-local task store và không có handoff store thứ hai.

### Optimistic concurrency

Mọi update dùng exact `expected_revision`:

```text
QiQi đọc revision 12
backend đọc revision 12
backend update -> revision 13
QiQi update revision 12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

SQLite dùng WAL + `BEGIN IMMEDIATE`; two-writer test xác nhận hai writer từ cùng
revision không thể cùng commit.

Arrays trong `work_item_update` replace nguyên tử; caller phải reread/reconcile full
array trước update. Nested objects merge theo JSON merge-patch semantics.

MVP cố ý chưa có workflow DSL, event sourcing, RBAC, notification, UI, Redmine sync
hoặc automatic phase transition. QiQi vẫn quyết định product workflow.

## `knowledge-template/`

Repository-independent reusable knowledge subsystem:

```text
knowledge-template/
├── README.md
├── store/
│   ├── INDEX.md
│   ├── global/
│   ├── systems/
│   ├── repos/
│   └── domains/
├── mcp/knowledge/
│   ├── contracts.py
│   ├── core.py
│   ├── server.py
│   ├── pyproject.toml
│   └── tests/
├── scripts/
│   ├── install-user-mcp.sh
│   ├── knowledge-mcp-server.sh
│   └── knowledge.py
└── skills/knowledge-distill/SKILL.md
```

Store có thể nằm trong repo riêng/path khác; MCP chỉ dùng explicit
`KNOWLEDGE_STORE_ROOT`, không suy luận từ CWD.

## Structured input, native output

`qiqi_delegate` cố ý làm input chặt và output linh hoạt.

### Input: TaskPacket

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

Khi delegation thuộc product Work Item, QiQi truyền **canonical Work Item identity +
revision** trong `required_context`. Child gọi `work_item_get` để lấy state mới nhất;
QiQi không copy toàn bộ Work Item document vào TaskPacket.

Fact external/live/durable không nằm trong canonical Work Item mà QiQi đã dùng để
quyết định semantics vẫn phải nằm trong `required_context` kèm provenance +
certainty.

Child không chia sẻ hidden conversation/reasoning/workspace state của QiQi và không
mở sibling source/result/runtime state.

### Output: native final response

MCP không ép execution agent ghi Markdown result schema. Native Stop hook chuyển full
`last_assistant_message` về MCP, không scrape terminal viewport/scrollback.

Settled success:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled",
  "agent_response": "<exact native final assistant message>"
}
```

Nếu Herdr xác nhận blocked trước native final response, `qiqi_delegate` preserve
native session ownership và trả `state: blocked`, `agent_response: null`. Không fake
semantic response từ terminal screen/transcript.

## Ba loại context

### Product-task context

Canonical Work Item là current task truth:

```text
current requirement
open question / resolved decision
requirement change
repo progress / verification
blocker / handoff / next action
```

QiQi và child query cùng MCP trực tiếp.

### Live implementation evidence

Current repo source/test và native execution result là owner truth cho implementation.
Child không mở sibling repository. Cross-repo execution vẫn do QiQi điều phối.

### Durable shared knowledge

Reusable, non-trivial, evidence-backed conclusion được persist qua Knowledge MCP.
Task-specific mutable state không tự động trở thành Knowledge.

Nếu shared knowledge mâu thuẫn current owner source/test, live source/test thắng cho
task hiện tại và verified durable conclusion mới được update khi phù hợp.

## Knowledge API

MVP Knowledge MCP expose:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Caller hiểu task rồi quyết định có cần durable context hay không:

- MUST read khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- MAY read khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- SKIP cho mechanical/exact local/status-only work nơi durable context không thể đổi
  action;
- substantive work có khả năng tạo/xác nhận reusable conclusion phải review/write;
- required review không candidate dùng `entries=[]`;
- create/update phải search existing concept để dedupe.

Agent không tạo knowledge file trực tiếp. Knowledge MCP sở hữu identity/path/index,
locking và revision.

## Language

Knowledge không có field `language`:

```text
canonical_name + routing metadata
→ canonical terminology, thường English

aliases
→ multilingual / legacy / acronym / project terms

content
→ Vietnamese / English / mixed tùy ý
```

Work Item text cũng có thể dùng ngôn ngữ phù hợp product/task; canonical ID không phụ
thuộc ngôn ngữ.

## Human maintenance của Knowledge

Human được phép tạo/sửa detail Markdown trực tiếp theo schema trong
`knowledge-template/README.md`.

Sau direct edit:

```bash
python3 knowledge-template/scripts/knowledge.py check --root /path/to/store
python3 knowledge-template/scripts/knowledge.py reindex --root /path/to/store
python3 knowledge-template/scripts/knowledge.py check --root /path/to/store
```

Work Item SQLite không có human-edit-file workflow trong MVP; mutate qua MCP để giữ
revision/atomicity.

## Cài Global Work Item MCP

Work Item MCP được cài user/global scope để QiQi và Herdr-launched child agents cùng
thấy một canonical task database:

```bash
cd work-item-template
bash scripts/install-user-mcp.sh
```

Default database:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Có thể override:

```bash
bash scripts/install-user-mcp.sh --db-path /path/to/work-items.sqlite3
```

Installer tạo stable wrapper và đăng ký MCP tên `work_item` cho Codex/Claude CLI có
sẵn. Existing registration cùng tên trỏ runtime khác sẽ làm installer fail thay vì
overwrite.

## Cài Knowledge MCP

```bash
cd knowledge-template
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Installer đăng ký MCP tên `knowledge` user/global scope. Existing registration cùng
tên không bị ghi đè.

Mở fresh agent session sau installation rồi smoke-test cả `work_item_get/list` và
`knowledge_read`.

## Cài workspace

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Project-scoped `.codex/config.toml` của workspace chỉ đăng ký `qiqi_delegate`.
`work_item` và `knowledge` là user-scoped services, không duplicate vào project
config.

Sau static/unit checker, chạy fresh-session acceptance smoke trên installed
Claude/Codex CLI thực tế cho adapter đang dùng.

## Cài repo template

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repo>/
cd /path/to/multi-repo/<repo>
bash scripts/repo-check.sh
```

Repo agent đọc canonical Work Item khi TaskPacket identify task, nhưng vẫn không được
sửa sibling repository hoặc tự điều phối repo khác.

## Verification Work Item template

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
```

Core tests cover create/get/list, questions/decisions/changes, nested repo merge,
stale revision, concurrent writers, immutable metadata và semantic handoff
validation.

Rollout acceptance smoke cần xác nhận fresh QiQi + fresh repo child session nhìn cùng
Work Item database.

## Migrate workspace đã tồn tại

Từ checkout của `agent-knowledge-harness`:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/multi-repo
bash scripts/migrate-workspace.sh /path/to/multi-repo
bash scripts/migrate-workspace.sh --status /path/to/multi-repo
```

Migration core nằm trong `scripts/migrate_workspace.py`. Definitions là JSON dưới
`migrations/`, pin exact `from_ref` / `to_ref` và dùng strategy `replace`, `merge`,
`delete`, `manual_review` theo artifact ownership.

Existing migration history vẫn áp dụng cho architecture trước Work Item MCP. Một
migration riêng cần được thêm khi feature này sẵn sàng merge để:

- remove legacy workspace `.qiqi/tasks/` artifacts;
- update workspace/repo agent policies;
- giữ user/global Work Item MCP installation là explicit operator step, không ghi
  user config từ workspace migration.

## Thiết kế cố ý

- Global Work Item MCP là canonical task truth duy nhất; không phân tán repo-local
  task state.
- QiQi là orchestration/synchronization broker, không phải memory bus.
- Repo agent đọc cùng task state nhưng chỉ thực thi current Git root.
- Cross-repo remaining work được persist thành Work Item handoff và QiQi điều phối.
- Knowledge Store không phụ thuộc current workspace/repo.
- Task-specific Q&A/change/blocker không tự động trở thành reusable knowledge.
- Repo source/test vẫn là implementation truth.
- qiqi_delegate SQLite chỉ giữ runtime/session ownership; không giữ semantic task
  state.
- qiqi_delegate không dùng terminal viewport/transcript để vận chuyển semantic result.
