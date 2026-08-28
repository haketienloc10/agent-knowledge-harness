# QiQi Multi-repository Workspace Template

Template đặt tại root của local workspace chứa nhiều Git repository độc lập. QiQi là Chief of Staff; repo-local work đi qua `delegate_repo_task`.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

`work_item` và `knowledge` là user-scoped services, không nằm trong workspace. Project `.codex/config.toml` chỉ đăng ký `qiqi_delegate`.

## Thành phần

```text
AGENTS.md
identity.md
repos.yaml
SYSTEM_MAP.md
instructions/agent-routing.yaml
instructions/model-routing.md
.agents/skills/ticket-work-item/SKILL.md
.codex/config.toml
mcp/qiqi_delegate/
.qiqi/.gitignore
scripts/workspace-check.sh
docs/WORKSPACE_SETUP.md
```

Workspace không sở hữu task DB hoặc Knowledge Store.

## Ticket Work Item skill

Khi người dùng chủ động muốn biến một ticket thật thành canonical Work Item, gọi explicit:

```text
$ticket-work-item
<paste ticket>
```

hoặc truyền file ticket local:

```text
$ticket-work-item path/to/ticket.md
```

Skill này là explicit entry point, không được auto-apply chỉ vì prompt có Redmine/Jira/GitHub issue, bug report hoặc incident. File path được truyền là user-provided ticket source; QiQi đọc đúng file đó, giữ path làm provenance và không scan sibling files nếu người dùng không yêu cầu.

## Execution model

```text
QiQi
  ↓ work_item_get/create nếu product task
  ↓ knowledge_search → exact knowledge_read khi cần durable context
  ↓ SYSTEM_MAP + Work Item + required external facts
  ↓ structured TaskPacket
qiqi_delegate
  ↓ Herdr START/RESUME exact Git root
repo agent
  ↓ work_item_get
  ↓ repo-local work + verification
  ↓ work_item_update current-repo evidence/handoff/checkpoint
  ↓ knowledge review/write nếu reusable
  ↓ native final response
qiqi_delegate
  ↓ session/turn runtime state
QiQi
  ↓ read agent_response
  ↓ work_item_get latest
  ↓ reconcile next orchestration step
```

## Work Item lifecycle

Canonical IDs ví dụ `redmine:116655`. Work Item giữ effective requirements, questions, decisions, changes, repo state, blockers, handoffs, next actions, checkpoints và revision.

QiQi sở hữu global phase/status/completion. Child chỉ current-repo authority. Cross-repo work quay lại QiQi qua Work Item handoff + native response.

## Knowledge progressive disclosure

```text
knowledge_search
→ thin decision cards
→ choose 1–2 IDs
→ knowledge_read
→ full semantic content/sources/revision
```

Search card không phải full evidence và không chứa revision. Update existing knowledge phải full-read target trước.

## TaskPacket

Khi task thuộc Work Item, `required_context` identify Work Item + revision. Child lấy current canonical state từ Work Item MCP. External fact ngoài Work Item mà QiQi dùng cho semantics vẫn phải inline với provenance/certainty.

## Runtime/session

`qiqi_delegate` chỉ giữ native session/turn ownership dưới `.qiqi/state/`. Native final response đi qua Stop hook; blocked state giữ exact session ID. Không dùng runtime DB làm semantic task state.

## Verification

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau static/unit check, chạy fresh-session smoke cho Work Item/Knowledge và native CLI smoke cho agent family thực sự dùng.
