# Agent Knowledge Harness

Harness cho multi-repository QiQi workspace với ba lớp chính:

- `workspace-template/`: orchestration/control plane + `qiqi_delegate`;
- `repo-template/`: execution-agent policy cho từng Git root;
- `work-item-template/`: filesystem-native Work Item lifecycle skill/templates;
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

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-user-skill.sh
```

Operational protocol: `work-item-template/skills/work-item/SKILL.md`.

## Workspace migration

```bash
bash scripts/migrate-workspace.sh /path/to/workspace --dry-run
bash scripts/migrate-workspace.sh /path/to/workspace --verify
```

Historical migration files mô tả các contract cũ tại thời điểm chúng được áp dụng; migration mới supersede current runtime/policy nhưng không rewrite lịch sử.
