# Filesystem Work Item

Work Item là **current task dossier** dùng chung trong một QiQi workspace. Runtime mới không còn Work Item MCP/SQLite và không dùng Work Item như execution history.

Canonical task location:

```text
<workspace>/work-items
```

Canonical ID giữ dạng `source:external-id`, ví dụ `redmine:116655`, và MUST match:

```text
^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$
```

Filesystem directory key replace colon separator đầu tiên bằng `~`:

```text
redmine:116655 -> work-items/redmine~116655/
```

Toàn `work-items/` phải casefold-unique để portable qua filesystem case-insensitive. Existing dossier chỉ reuse khi `WORK_ITEM.md` có exact front-matter `id` khớp canonical ID và resolved path vẫn nằm dưới Work Items root.

Mỗi tracked task có thể materialize:

```text
work-items/<directory-key>/
├── WORK_ITEM.md
├── intake.md?
├── investigation.md?
├── plan.md?
├── review.md?
├── references/?
└── report.textile?
```

Không tạo mặc định `history/`, `turns/`, `executions/`, `checkpoints/` hay file theo turn. `references/` chỉ chứa task-specific source material/evidence cần tra cứu; lifecycle state vẫn nằm trong các living documents phía trên.

## Ownership boundary

```text
Workspace QiQi          = Work Item lifecycle + canonical writer
Repository child        = repo-local investigation/implementation/verification
TaskPacket              = current delegated assignment
Mounted Work Item       = read-only durable task context cho child
Repo source/test        = implementation truth
Knowledge MCP           = reusable durable truth
.qiqi/state             = runtime/session truth
```

`$work-item` là **workspace-scoped skill** cho QiQi parent. Repo child không cần và không sở hữu Work Item lifecycle; child đọc TaskPacket + mounted dossier rồi trả material evidence/conclusion về QiQi.

## One skill, internal phase protocols

Harness chỉ expose **một Agent Skill**:

```text
work-item-template/skills/work-item/
├── SKILL.md
├── phases/
│   ├── intake.md
│   ├── investigation.md
│   ├── planning.md
│   └── review.md
└── templates/
    ├── WORK_ITEM.md
    ├── intake.md
    ├── investigation.md
    ├── plan.md
    ├── review.md
    └── report.textile
```

Các phase file là internal progressive-disclosure references, không phải skill độc lập. `SKILL.md` chỉ đọc phase cần thiết just-in-time:

- intake: mandatory cho task mới/material requirement change;
- investigation: conditional khi target/ownership/boundary chưa rõ;
- planning: conditional khi approach/trade-off materially non-obvious;
- review: mandatory trước completion/reporting.

Gate vocabulary chung: `ready | needs_user_clarification | needs_discovery | blocked`.

Core rule: **clarify meaning, not mechanics**. Product/domain intent hoặc material acceptance cần user; factual repo/module/evidence unknown thì agent tự discover; normal reversible implementation choice thì agent tự quyết khi evidence đủ.

## Workspace-scoped installation

Từ harness checkout:

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-workspace-skill.sh /absolute/path/to/workspace
```

Installer yêu cầu workspace có `repos.yaml` và `identity.md`, rồi materialize cùng source skill tree vào:

```text
<workspace>/.agents/skills/work-item/   # Codex parent at workspace root
<workspace>/.claude/skills/work-item/   # Claude parent at workspace root
```

Installer **không** copy skill xuống repo con. Repo agent policy + TaskPacket + mounted Work Item mới là execution contract của child.

Historical harness releases từng cài `work-item` ở user/global roots (`~/.agents/skills`, `~/.codex/skills`, `~/.claude/skills`). Sau khi cả hai workspace targets cài thành công, installer chỉ xóa old copy có `.agent-knowledge-harness-managed`. Same-name global entry không có marker bị fail closed và không bị xóa, để tránh shadow/duplicate discovery ngoài ý muốn.

`install-user-skill.sh` chỉ còn là compatibility wrapper chuyển sang workspace installer; new setup nên gọi `install-workspace-skill.sh` trực tiếp.

Sau install/update, mở fresh QiQi session **từ workspace root** để refresh skill discovery.

## Current-state semantics

`WORK_ITEM.md` là current canonical task truth. `intake.md`, `investigation.md`, `plan.md`, `review.md`, `report.textile` là living lifecycle docs, merge/rewrite theo current meaning; không append execution chronology.

Requirement change rewrite effective requirement + increment revision; prior findings được reconcile theo materiality thay vì auto discard. Persist chỉ datum mà nếu bỏ đi có thể làm turn sau hiểu sai requirement, lặp material investigation, đi sai implementation, đánh giá sai acceptance hoặc report sai.

## Legacy SQLite cutover

Trước khi gỡ legacy `work_item` MCP registration, export dữ liệu cũ:

```bash
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Default source DB là `~/.local/share/agent-work-items/work-items.sqlite3` hoặc `WORK_ITEM_DB_PATH`. Nếu legacy installer dùng custom `--db-path`, truyền exact DB bằng `--db /absolute/path/to/work-items.sqlite3`.

Exporter lấy Work Item + artifact/section/chunk trong một SQLite read snapshot, preflight toàn bộ output, reject casefold-equivalent keys, materialize latest lifecycle artifacts và lưu protected raw backup dưới:

```text
<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/
```

Source SQLite không bị sửa/xóa. Imported dossier có thể có `legacy_reconciliation_required: true`; QiQi phải reconcile material legacy acceptance/provenance trước substantive implementation/completion/report rồi rewrite current state, increment revision và bỏ flag.

Sau export và inspection, remove legacy registration bằng:

```bash
bash scripts/remove-legacy-user-mcp.sh
```

Helper chỉ remove `work_item` khi registration còn trỏ tới legacy harness-managed wrapper; unrelated same-name registration bị reject.

## Lifecycle

```text
request
→ intake/canonicalize + mandatory intake gate
→ investigate (nếu cần; clarification gate chỉ khi boundary/target chưa rõ)
→ plan/decide (nếu cần; decision gate chỉ khi materially non-obvious)
→ implement/delegate
→ verify/review + mandatory acceptance gate
→ report
→ done
```

Flow được phép quay lại intake/investigation/planning khi evidence hoặc requirement đổi; không encode FSM cứng.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Operational protocol: `skills/work-item/SKILL.md`. Phase semantics: `skills/work-item/phases/*.md`.
