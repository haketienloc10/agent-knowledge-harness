# Workspace setup

## Layout

```text
<workspace>/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── work-items/
├── instructions/
├── mcp/qiqi_delegate/
└── scripts/
```

`work-items/` là workspace-level current task resource. Không cài Global Work Item MCP và không tạo SQLite Work Item DB.

## Runtime

`scripts/qiqi-mcp-server.sh` resolve workspace root, `mkdir -p work-items`, export `QIQI_WORK_ITEMS_DIR` và start `qiqi_delegate`. Không cần shell ngoài export `QIQI_CLAUDE_ADDITIONAL_DIR` hay path tương đương.

`QIQI_WORK_ITEMS_DIR` là agent-neutral semantic env. Agent adapter tự map resource này sang native filesystem option (`--add-dir`).

## Work Item lifecycle

Cài/update `$work-item` skill từ harness:

```bash
cd work-item-template
bash scripts/install-user-skill.sh
```

Tracked task nằm tại `work-items/<id>/`. `WORK_ITEM.md` là current canonical state; lifecycle docs là living semantic state, không append-only history.

Requirement change:

1. rewrite effective current requirements;
2. increment revision;
3. reconcile prior investigation/plan/review với requirement mới;
4. giữ finding cũ nếu fact còn đúng, reinterpret khi implication đổi, revalidate/remove khi assumption đã supersede.

## Repo delegation

TaskPacket vẫn chứa objective/scope/acceptance đầy đủ. Với tracked task, QiQi truyền locator + revision qua `context.trusted_facts`; child được đọc mounted Work Item nhưng không mutate canonical dossier.

## Verification

```bash
bash scripts/workspace-check.sh
```
