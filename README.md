# Agent Knowledge Harness

Harness cho multi-repository QiQi workspace với các thành phần chính:

- `workspace-template/`: orchestration/control plane + `qiqi_delegate`;
- `repo-template/`: execution-agent policy cho từng Git root;
- `work-item-template/`: workspace-scoped filesystem-native Work Item lifecycle skill/templates;
- `knowledge-template/`: user-scoped Shared Knowledge MCP cho reusable durable knowledge;
- `migrations/`: upgrade definitions cho workspace/repo đã cài harness.

## Sources of truth

```text
workspace/work-items/  = current mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
.qiqi/state            = runtime/session truth
```

Work Item không còn là MCP/SQLite service. `qiqi_delegate` mount `<workspace>/work-items` vào supported child agents bằng shared directory runtime contract.

Work Item là current semantic state, không phải execution history. Multi-turn investigation/implementation rewrite living state; requirement changes rewrite effective current requirements rồi reconcile prior findings theo materiality.

## Unified workspace setup

Sau khi materialize/migrate workspace, recommended entrypoint là:

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace
```

Interactive installer cho chọn độc lập:

- QiQi coordinator: Claude Code / Codex / both;
- Herdr repository execution agent: Claude Code / Codex / both;
- default balanced route khi enable cả hai execution families.

Installer tuân theo current Work Item architecture: cài workspace-scoped `$work-item` skill cho selected coordinators, không recreate legacy Work Item MCP. Shared Knowledge MCP/skill được cài cho union của selected coordinator + execution clients. Claude coordinator dùng local-scope `qiqi_delegate`; nested Claude repository sessions nhận machine-local ancestor-instruction isolation.

Chi tiết: `docs/WORKSPACE_INSTALLER.md`.

## Work Item template

`$work-item` là workspace/QiQi lifecycle skill. Harness expose một skill duy nhất với internal phase references cho intake/investigation/planning/review; repo child chỉ đọc TaskPacket + mounted Work Item và không sở hữu canonical lifecycle.

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-workspace-skill.sh /path/to/workspace
```

Installer materialize cùng Work Item skill tree vào `<workspace>/.agents/skills/work-item` và `<workspace>/.claude/skills/work-item` theo default `--clients both`; unified setup truyền exact selected coordinator clients.

Operational protocol: `work-item-template/skills/work-item/SKILL.md`.

## Workspace migration

Với máy có legacy Work Item SQLite, cutover theo thứ tự:

1. export exact legacy DB theo `work-item-template/README.md` (nếu old installer dùng custom `--db-path`, truyền exact path bằng `--db`);
2. kiểm tra imported dossiers/archive rồi chạy `work-item-template/scripts/remove-legacy-user-mcp.sh` để gỡ registration cũ có xác minh ownership;
3. migrate workspace/repositories;
4. chạy unified workspace setup để cài/update selected workspace `$work-item` skill, Knowledge, client adapters và Herdr integrations;
5. mở fresh QiQi agent session từ workspace root.

```bash
bash scripts/migrate-workspace.sh /path/to/workspace --dry-run
bash scripts/migrate-workspace.sh /path/to/workspace --verify
bash scripts/setup-workspace.sh /path/to/workspace
```

`--verify` trên workspace thực kiểm canonical repo/dependency registry, exact Git roots, qiqi_delegate tests và Herdr integration readiness theo current workspace setup config khi có.

Historical migration files mô tả contract tại thời điểm áp dụng; migration mới supersede current runtime/policy nhưng không rewrite lịch sử.
