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
.codex/config.toml
mcp/qiqi_delegate/
.qiqi/.gitignore
scripts/workspace-check.sh
docs/WORKSPACE_SETUP.md
```

Workspace không sở hữu task DB, Knowledge Store hoặc bản copy Work Item protocol.

## Registry và System Map

`repos.yaml` là canonical repository registry cho workspace/repository identity, exact
Git-root path, role, `required_for` và `depends_on`. QiQi dùng registry này để chọn
repository và dependency wave. `depends_on` biểu diễn orchestration precedence và phải
là directed acyclic graph; cycle không tạo được executable dependency wave và bị checker reject.

`SYSTEM_MAP.md` không lặp repository registry. Nó chỉ giữ cross-repo semantic facts mà
registry không trả lời được: contracts, ownership/data boundaries, non-trivial integration
behavior, compatibility/deprecation/rollback và shared-infrastructure facts. Task chỉ cần
repository/dependency basics không hydrate System Map.

## Work Item operational skill

`$work-item` là user-scoped skill được cài cùng Global Work Item MCP và dùng chung bởi
QiQi + repository execution agents. `AGENTS.md` chỉ giữ activation/authority/safety
invariants; read/write/revision/reconciliation/artifact mechanics nằm trong `$work-item`.

Generic ticket/task không tự động trở thành Work Item. Khi user explicitly yêu cầu tạo/
dùng Work Item hoặc canonical Work Item đã được identify, QiQi/child apply `$work-item`
theo role authority.

Không còn workspace-local `$ticket-work-item` entrypoint. Nếu muốn tạo task mới từ nội
dung paste, user chỉ cần explicitly yêu cầu QiQi tạo Work Item từ nội dung đó; `$work-item`
lo phần canonical get-or-create/reconciliation protocol.

## Execution model

```text
QiQi
  ↓ apply $work-item khi canonical Work Item được dùng
  ↓ work_item_get/create theo explicit Work Item intent
  ↓ repos.yaml → repository/dependency wave
  ↓ SYSTEM_MAP only khi cần cross-repo semantic fact ngoài registry
  ↓ knowledge_search → exact scoped knowledge read khi cần durable context
  ↓ Work Item + required external facts
  ↓ structured TaskPacket
qiqi_delegate
  ↓ Herdr START/RESUME exact Git root
repo agent
  ↓ apply $work-item khi TaskPacket identify Work Item
  ↓ repo-local work + verification
  ↓ canonical current-repo reconciliation
  ↓ knowledge review/mutation nếu reusable
  ↓ native final response
qiqi_delegate
  ↓ session/turn runtime state
QiQi
  ↓ read agent_response
  ↓ reread/reconcile Work Item theo $work-item
  ↓ decide next orchestration step
```

## Work Item lifecycle

Canonical IDs ví dụ `redmine:116655`. Work Item giữ effective requirements, questions, decisions, changes, repo state, blockers, handoffs, next actions, checkpoints và revision.

QiQi sở hữu global phase/status/completion. Child chỉ current-repo authority. Cross-repo work quay lại QiQi qua Work Item handoff + native response.

## Knowledge progressive disclosure

```text
knowledge_search
→ thin decision cards
→ choose exact target
→ smallest sufficient exact read:
     knowledge_read | knowledge_read_metadata | knowledge_read_section
→ knowledge_write / knowledge_update
```

Search card không phải full evidence và không chứa revision. Existing update target lấy exact whole-document revision từ exact read đủ semantic scope; metadata/section update không buộc caller hydrate/resend untouched whole content.

Stable `<!-- knowledge-section:<lowercase-kebab-id> -->` marker chỉ là optional semantic address trong cùng canonical Markdown document. Knowledge vẫn giữ one semantic concept = one document = one SHA-256 revision; không chunk store/per-section revision.

## TaskPacket

Khi task thuộc Work Item, `required_context` identify Work Item + revision. Child lấy current canonical state từ Work Item MCP theo `$work-item`. External fact ngoài Work Item mà QiQi dùng cho semantics vẫn phải inline với provenance/certainty.

## Runtime/session

`qiqi_delegate` chỉ giữ native session/turn ownership dưới `.qiqi/state/`. Native final response đi qua Stop hook; blocked state giữ exact session ID. Không dùng runtime DB làm semantic task state.

## Verification

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau static/unit check, rerun Knowledge user-scope installer sau public-tool change rồi chạy fresh-session smoke cho đủ 6 Knowledge tools, Work Item/$work-item và native CLI của agent family thực sự dùng.
