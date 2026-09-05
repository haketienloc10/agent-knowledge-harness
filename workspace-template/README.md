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

`repos.yaml` là canonical repository registry cho workspace/repository identity, exact Git-root path, role, `required_for` và `depends_on`. QiQi dùng registry này để chọn repository và dependency wave. `depends_on` là orchestration precedence và phải là DAG; checker reject cycle.

`SYSTEM_MAP.md` không lặp repository registry. Nó chỉ giữ cross-repo semantic facts mà registry không trả lời được: contracts, ownership/data boundaries, non-trivial integration behavior, compatibility/deprecation/rollback và shared-infrastructure facts. Task chỉ cần repository/dependency basics không hydrate System Map.

## Work Item operational skill

`$work-item` là **user-scoped skill** được cài cùng Global Work Item MCP và được QiQi dùng cho canonical mutable task state. `AGENTS.md` chỉ giữ activation/authority/safety invariants; read/write/revision/reconciliation mechanics nằm trong `$work-item`.

Generic ticket/task không tự động trở thành Work Item. Khi user explicitly yêu cầu tạo/dùng Work Item hoặc canonical Work Item đã được identify, **QiQi** apply `$work-item` theo orchestration authority.

Repository child không cần Work Item ID/revision và không `work_item_get`/`work_item_update` để hiểu hoặc persist repo-local assignment. Work Item correlation nếu runtime/audit cần vẫn ở QiQi/runtime side, không render thành child task semantics.

## Execution model

```text
User / Work Item / Knowledge / System Map
                 ↓
                QiQi
      understand + reconcile + distill
                 ↓
     immutable semantic snapshot
                 ↓
            TaskPacket
                 ↓
          qiqi_delegate
                 ↓ Herdr START/RESUME exact Git root
            repo agent
                 ↓ discover current repo
                 ↓ implementation / investigation / design
                 ↓ allowed Knowledge/runtime evidence when policy permits
                 ↓ choose verification HOW
                 ↓ exact native final response
          qiqi_delegate
                 ↓ runtime lifecycle/session state
                QiQi
                 ↓ reconcile against latest canonical truth
                 ↓ decide semantic completion / next action
```

Task có Work Item và task không có Work Item dùng cùng child execution protocol. Work Item chỉ thay đổi QiQi-side orchestration/reconciliation, không thay TaskPacket comprehension path của child.

## TaskPacket

TaskPacket là **smallest sufficient repo-local problem contract** và là **immutable semantic snapshot** cho một delegated turn.

Required:

```text
objective
scope[]
acceptance_criteria[]
```

Optional, omit khi empty:

```text
out_of_scope[]
context.trusted_facts[] {fact, source}
context.claims_to_investigate[] {claim, source}
constraints[]
known_unknowns[]
```

Không còn child-facing `user_request`, Work Item ref/revision hoặc normal `verification` field. QiQi distill material semantics; child tự discover repo-local verification strategy.

`trusted_fact` là execution premise child MAY rely on; trusted-for-execution không nhất thiết là independently verified truth. `claim_to_investigate` là proposition child MUST NOT assume. `known_unknown` không được silently assume away.

### Task-semantic closed world

TaskPacket phải tự đủ về **task meaning**. Child không dùng Work Item, Shared Knowledge, sibling repo hoặc hidden QiQi state để reconstruct objective/scope/product decision/constraint/acceptance bị thiếu.

Điều này **không** cấm legitimate execution-time information. Child có thể dùng current repo, stable execution policy/environment, Shared Knowledge cho reusable implementation/domain knowledge và authorized runtime/log/API/DB/browser/infra evidence khi policy/task cho phép.

`smallest sufficient` được đánh giá bằng hai chiều:

- semantic completeness: child hiểu WHAT/boundary/premises/acceptance mà không cần hidden orchestration state;
- semantic minimality: datum task-specific chỉ ở packet nếu bỏ nó có thể làm hiểu sai assignment hoặc accept sai result.

Prompt/token size là regression metric phụ, không phải lý do truncate material semantics.

## Stale semantics

TaskPacket không mutate sau START. Nếu canonical state thay đổi, QiQi đánh giá materiality:

```text
non-material
→ cho child settle
→ reconcile result với latest truth

material
→ stale result MUST NOT become current truth
→ cancel / interrupt / resume / redelegate / reconcile tùy runtime capability
```

Mechanism không phải invariant; invariant là materially stale result không được promote thành current truth.

## Knowledge progressive disclosure

Ở QiQi layer, Knowledge có thể ảnh hưởng TaskPacket semantics. Ở child layer, Knowledge chỉ dùng cho reusable repo/domain implementation knowledge khi stable repo policy cho phép; **không dùng như fallback cho incomplete TaskPacket**.

```text
knowledge_search
→ thin decision cards
→ choose exact target
→ smallest sufficient exact read:
     knowledge_read | knowledge_read_metadata | knowledge_read_section
→ knowledge_write / knowledge_update khi authority/policy cho phép
```

Search card không phải full evidence và không chứa revision. Existing update target lấy exact whole-document revision từ exact read đủ semantic scope; metadata/section update không buộc caller hydrate/resend untouched whole content.

Stable knowledge section marker chỉ là optional semantic address trong cùng canonical Markdown document. Knowledge vẫn one concept = one document = one SHA-256 revision.

## Native result semantics

`qiqi_delegate` trả exact native final response. Runtime state `settled | failed | blocked` chỉ là execution lifecycle truth; **không phải semantic completion**.

Không thêm semantic status `completed | partial | blocked`. QiQi đọc native response, reconcile acceptance + latest Work Item/product truth rồi quyết định completion.

Blocked trước native final response giữ exact `session_id` và `agent_response=null` để RESUME; không terminal/viewport/transcript fallback.

## Greenfield planning

Trong repo requirement-only, child được tự chọn reversible technical decisions không materially đổi product semantics, external/public contract, security/compliance hoặc significant cost/operational envelope. Decision vượt boundary phải surface về QiQi/user thay vì invent product truth.

## Verification

```bash
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Sau static/unit check, chạy fresh-session smoke cho cả task có/không Work Item, missing-task-semantics blocker, legitimate child Knowledge usage, runtime/external evidence và stale-canonical-state reconciliation.
