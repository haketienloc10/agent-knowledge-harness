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

## Work Item template

`$work-item` là workspace/QiQi lifecycle skill. Harness expose một skill duy nhất với internal phase references cho intake/investigation/planning/review; repo child chỉ đọc TaskPacket + mounted Work Item và không sở hữu canonical lifecycle.

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-workspace-skill.sh /path/to/workspace
```

Installer materialize cùng Work Item skill tree vào `<workspace>/.agents/skills/work-item` và `<workspace>/.claude/skills/work-item`; không copy skill xuống repo con.

Operational protocol: `work-item-template/skills/work-item/SKILL.md`.

## Workspace migration

Với máy có legacy Work Item SQLite, cutover theo thứ tự:

1. export exact legacy DB theo `work-item-template/README.md` (nếu old installer dùng custom `--db-path`, truyền exact path bằng `--db`);
2. kiểm tra imported dossiers/archive rồi chạy `work-item-template/scripts/remove-legacy-user-mcp.sh` để gỡ registration cũ có xác minh ownership;
3. migrate workspace/repositories;
4. cài/update workspace-scoped `$work-item` skill, cài Herdr Codex/Claude integrations và chạy workspace verification;
5. mở fresh QiQi agent session từ workspace root.

```bash
bash scripts/migrate-workspace.sh /path/to/workspace --dry-run
bash scripts/migrate-workspace.sh /path/to/workspace --verify
```

`--verify` trên workspace thực kiểm canonical repo/dependency registry, exact Git roots, qiqi_delegate tests và Herdr integration readiness.

Historical migration files mô tả contract tại thời điểm áp dụng; migration mới supersede current runtime/policy nhưng không rewrite lịch sử.
