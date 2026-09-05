# Agent Knowledge Harness

Bộ khung vận hành QiQi trong multi-repository workspace với bốn nguồn truth độc lập:

```text
Global Work Item MCP   = mutable product-task truth (QiQi side)
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Kiến trúc

```text
User / Work Item / Shared Knowledge / System Map
                     ↓
                    QiQi
          reconcile + distill semantics
                     ↓
          immutable TaskPacket snapshot
                     ↓
              qiqi_delegate MCP
                     ↓ Herdr START / RESUME
              independent Git repo
                     ↓
             execution child agent
                     ↓
        exact native semantic response
                     ↓
              qiqi_delegate MCP
                     ↓ runtime lifecycle/session state
                    QiQi
                     ↓
        reconcile latest canonical truth
```

**Work Item chỉ thuộc QiQi/orchestration side.** Repository child không cần Work Item ID/revision và không `work_item_get`/`work_item_update` để hiểu hoặc hoàn thành repo-local assignment.

## Thành phần

- `workspace-template/`: QiQi orchestration/control plane.
- `repo-template/`: execution-agent policy cho từng Git root.
- `work-item-template/`: user-scoped Global Work Item MCP + QiQi-side `$work-item` protocol.
- `knowledge-template/`: user-scoped progressive Shared Knowledge MCP + store.
- `migrations/`: upgrade definitions cho workspace/repo đã cài harness.

## TaskPacket contract

`qiqi_delegate` nhận structured TaskPacket là **smallest sufficient repo-local problem contract** và là **immutable semantic snapshot cho một delegated turn**.

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

Không còn child-facing:

```text
user_request
Work Item id/revision
normal verification command
QiQi orchestration bookkeeping
```

QiQi **translate, not forward**: original wording/history có thể bỏ, nhưng material semantics có thể đổi objective/scope/constraint/acceptance/premise/unknown phải survive distillation.

`acceptance_criteria` định nghĩa **WHAT must be demonstrated**. Child discover **HOW** từ current repo/stable policy và report actual verification/evidence. Exact method/command chỉ được giữ khi method itself là user/product/system requirement.

### Context semantics

```text
trusted_fact
→ child MAY rely on it as an execution premise
→ MVP shape: {fact, source}
→ trusted-for-execution != independently verified truth

claim_to_investigate
→ child MUST NOT assume it
→ establish / contradict / mark unresolved khi nằm trong scope

known_unknown
→ child MUST NOT silently assume it away
→ không bắt buộc resolve nếu scope/acceptance không yêu cầu
```

Một proposition không được vừa trusted premise vừa claim cần verify.

### Task-semantic closed world

Self-sufficient áp dụng cho **task meaning**, không phải mọi execution information.

Child MUST NOT dùng Work Item, Shared Knowledge, sibling repository hoặc hidden QiQi state để reconstruct objective/scope/product decision/constraint/acceptance bị thiếu.

Child MAY dùng current repo, stable execution policy/environment, Shared Knowledge cho reusable repo/domain implementation knowledge và authorized runtime/log/API/DB/browser/infra evidence khi task/policy cho phép.

`smallest sufficient` được đánh giá bằng:

- **completeness**: context-naive child hiểu WHAT/boundary/premises/acceptance không cần hidden orchestration state;
- **minimality**: datum task-specific chỉ ở packet nếu bỏ nó có thể làm hiểu sai assignment hoặc accept sai result.

Token/character count chỉ là safety/performance metric phụ.

## Immutable snapshot và stale semantics

TaskPacket không mutate sau START. Nếu canonical state đổi trong khi child đang chạy, QiQi sở hữu stale detection/materiality/reconciliation.

```text
non-material change
→ child may settle
→ QiQi reconcile against latest truth

material change
→ stale result MUST NOT become current truth
→ cancel / interrupt / resume / redelegate / reconcile
  tùy runtime capability
```

Normative invariant là stale result không được promote thành current truth; interrupt không phải mechanism bắt buộc.

## Native result semantics

`qiqi_delegate` trả exact native final assistant response qua native Stop hook. Không dùng fixed Markdown result schema, terminal viewport hoặc transcript parser làm semantic transport.

Runtime state:

```text
settled | failed | blocked
```

chỉ mô tả execution lifecycle. Nó **không phải semantic completion truth**. Không thêm child-authored `completed | partial | blocked` envelope; QiQi đọc native response và quyết định semantic completion trong reconciliation.

Blocked trước native final response giữ exact `session_id` và `agent_response=null` để RESUME.

## Global Work Item MCP

MVP tools:

```text
work_item_get(id)
work_item_history_read(id, collection, status?, repository?, cursor?, limit?)
work_item_list(status?, repository?, limit?)
work_item_create(...)
work_item_update(id, expected_revision, mutation)
```

Work Item là canonical mutable product-task state của QiQi. `work_item_get` trả bounded current-state projection; accumulated history đọc đúng collection qua `work_item_history_read` khi provenance material.

`work_item_update` dùng:

```text
WorkItemMutation
  state       = bounded current-state patch
  operations  = grouped typed semantic mutations
```

Groups:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

Không có `{op,value}` envelope hoặc historical full-array replacement. Tất cả groups commit all-or-nothing dưới one exact whole Work Item revision; stale writer conflict và server không auto-rebase.

### `$work-item` skill

`$work-item` là user-scoped **QiQi/orchestration-side** operational protocol. Apply khi canonical Work Item đã identify/selected, user explicitly yêu cầu tạo/dùng Work Item, hoặc trước QiQi `work_item_*` call.

Generic ticket/task không tự động trở thành Work Item. Repository child không apply `$work-item` như TaskPacket execution prerequisite.

## Shared Knowledge MCP

Public API:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_read_metadata(ids)
knowledge_read_section(id, section_id)
knowledge_write(entries)
knowledge_update(id, expected_revision, changes)
```

Progressive disclosure:

```text
search thin decision cards
→ choose exact target
→ exact-read smallest sufficient scope
→ whole/partial mutation khi cần
```

Ở QiQi layer, Knowledge có thể ảnh hưởng TaskPacket semantics và material premise phải được distill vào packet. Ở child layer, Knowledge chỉ là legitimate implementation/domain knowledge khi stable repo policy cho phép; **không phải fallback cho incomplete TaskPacket**.

Current owner source/test thắng stale reusable Knowledge cho implementation truth.

## Greenfield authority

Trong repo requirement-only, child MAY tự chọn reversible technical decision không materially đổi:

- observable product semantics;
- public/external contract;
- security/compliance semantics;
- significant cost/operational envelope.

Decision vượt boundary phải surface về QiQi/user thay vì invent product truth.

## Cài Global Work Item MCP

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-user-mcp.sh
```

Default DB:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

## Cài/kiểm tra Knowledge MCP

```bash
cd knowledge-template
bash scripts/knowledge-template-check.sh
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Sau public MCP/skill change, rerun installer từ checkout mới rồi mở fresh session để discover schema mới.

## Workspace mới

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Project `.codex/config.toml` chỉ đăng ký `qiqi_delegate`; `work_item`, `$work-item` và `knowledge` là user-scope capabilities.

## Workspace đã cài harness

Không rsync đè template. Dùng migration:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

TaskPacket 0.2.x là coordinated public schema change. Sau migration phải mở fresh QiQi/child session để load policy/tool schema mới.

## Acceptance smoke

Sau migration/cài đặt, xác nhận:

1. Same repo-local assignment có/không Work Item tạo child-facing semantics tương đương.
2. Child không cần Work Item dereference.
3. Missing task semantics không được recover từ Work Item/Knowledge/sibling state.
4. Empty optional TaskPacket sections không render boilerplate.
5. Child có thể dùng allowed Shared Knowledge cho reusable implementation concern đã discover.
6. Authorized runtime/external evidence không bị cấm bởi self-sufficiency rule.
7. Material canonical-state change không làm stale result trở thành current truth.
8. Native hook/RESUME pass cho agent family thực sự dùng.

## Thiết kế cố ý

- Work Item MCP là mutable task truth duy nhất và thuộc QiQi side.
- TaskPacket là child-facing semantic snapshot, không phải Work Item delta/reference.
- Knowledge MCP giữ reusable durable truth, không task-specific mutable state.
- Repo source/test là implementation truth.
- qiqi_delegate SQLite chỉ giữ runtime/session truth.
- QiQi là orchestration/synchronization + semantic reconciliation broker.
